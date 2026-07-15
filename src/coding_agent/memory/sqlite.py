"""SQLite implementation of project-scoped persistent memory."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from coding_agent.memory.models import (
    MemoryCategory,
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
    MemorySourceType,
    utc_now,
)
from coding_agent.observability import NoOpTracer, Tracer

_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_./-]+")


class MemoryRepositoryError(Exception):
    code = "memory_repository_error"


class MemoryRecordNotFoundError(MemoryRepositoryError):
    code = "memory_record_not_found"


class SQLiteMemoryRepository:
    """Transactional stdlib SQLite store with schema versioning."""

    def __init__(self, database_path: str | Path, *, tracer: Tracer | None = None) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._tracer = tracer or NoOpTracer()
        self._migrate()

    @property
    def database_path(self) -> Path:
        return self._path

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> SQLiteMemoryRepository:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def save(self, record: MemoryRecord) -> MemoryRecord:
        with self._tracer.observe(
            "memory.persist",
            input={
                "project_id": record.project_id,
                "session_id": record.session_id,
                "category": record.category.value,
                "source": record.source_reference,
            },
        ) as observation:
            stored = self._save(record)
            observation.update(output={"record_id": stored.id})
            return stored

    def _save(self, record: MemoryRecord) -> MemoryRecord:
        values = _record_values(record)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO project_memory (
                    id, project_id, category, kind, content, source_type,
                    source_reference, confidence, session_id, created_at,
                    updated_at, last_verified_at, stale_after, metadata_json,
                    invalidated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, id) DO UPDATE SET
                    category = excluded.category,
                    kind = excluded.kind,
                    content = excluded.content,
                    source_type = excluded.source_type,
                    source_reference = excluded.source_reference,
                    confidence = excluded.confidence,
                    session_id = excluded.session_id,
                    updated_at = excluded.updated_at,
                    last_verified_at = excluded.last_verified_at,
                    stale_after = excluded.stale_after,
                    metadata_json = excluded.metadata_json,
                    invalidated_at = excluded.invalidated_at
                """,
                values,
            )
        stored = self.get(project_id=record.project_id, record_id=record.id)
        if stored is None:
            raise MemoryRepositoryError("Saved memory could not be read back.")
        return stored

    def get(self, *, project_id: str, record_id: str) -> MemoryRecord | None:
        with self._tracer.observe(
            "memory.load",
            input={"project_id": project_id, "record_id": record_id},
        ) as observation:
            row = self._connection.execute(
                "SELECT * FROM project_memory WHERE project_id = ? AND id = ?",
                (project_id, record_id),
            ).fetchone()
            result = None if row is None else _row_to_record(row)
            observation.update(output={"found": result is not None})
            return result

    def search(
        self,
        query: MemoryQuery,
        *,
        now: datetime | None = None,
    ) -> tuple[MemorySearchResult, ...]:
        with self._tracer.observe(
            "memory.load",
            input={
                "project_id": query.project_id,
                "categories": query.categories,
                "query": query.text,
            },
        ) as observation:
            results = self._search(query, now=now)
            observation.update(
                output={
                    "count": len(results),
                    "record_ids": [result.record.id for result in results],
                }
            )
            return results

    def _search(
        self,
        query: MemoryQuery,
        *,
        now: datetime | None = None,
    ) -> tuple[MemorySearchResult, ...]:
        clauses = ["project_id = ?"]
        parameters: list[object] = [query.project_id]
        if query.categories:
            placeholders = ",".join("?" for _ in query.categories)
            clauses.append(f"category IN ({placeholders})")
            parameters.extend(category.value for category in query.categories)
        if query.kinds:
            placeholders = ",".join("?" for _ in query.kinds)
            clauses.append(f"kind IN ({placeholders})")
            parameters.extend(kind.value for kind in query.kinds)
        rows = self._connection.execute(
            f"SELECT * FROM project_memory WHERE {' AND '.join(clauses)}",
            parameters,
        ).fetchall()
        timestamp = now or utc_now()
        query_tokens = _tokens(query.text)
        results: list[MemorySearchResult] = []
        for row in rows:
            record = _row_to_record(row)
            stale = record.is_stale(now=timestamp)
            if stale and not query.include_stale:
                continue
            relevance = _relevance(query_tokens, record)
            if relevance == 0.0:
                continue
            results.append(MemorySearchResult(record=record, relevance=relevance, stale=stale))
        results.sort(
            key=lambda item: (item.relevance, item.record.updated_at),
            reverse=True,
        )
        return tuple(results[: query.limit])

    def mark_stale(
        self,
        *,
        project_id: str,
        record_id: str,
        at: datetime | None = None,
    ) -> MemoryRecord:
        timestamp = at or utc_now()
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE project_memory
                SET invalidated_at = ?, stale_after = ?, updated_at = ?
                WHERE project_id = ? AND id = ?
                """,
                (_iso(timestamp), _iso(timestamp), _iso(timestamp), project_id, record_id),
            )
        if cursor.rowcount != 1:
            raise MemoryRecordNotFoundError(f"Memory record not found: {record_id}.")
        record = self.get(project_id=project_id, record_id=record_id)
        if record is None:
            raise MemoryRepositoryError("Invalidated memory could not be read back.")
        return record

    def verify(
        self,
        *,
        project_id: str,
        record_id: str,
        verified_at: datetime,
        stale_after: datetime | None,
    ) -> MemoryRecord:
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE project_memory
                SET last_verified_at = ?, stale_after = ?, invalidated_at = NULL,
                    updated_at = ?
                WHERE project_id = ? AND id = ?
                """,
                (
                    _iso(verified_at),
                    _iso(stale_after),
                    _iso(verified_at),
                    project_id,
                    record_id,
                ),
            )
        if cursor.rowcount != 1:
            raise MemoryRecordNotFoundError(f"Memory record not found: {record_id}.")
        record = self.get(project_id=project_id, record_id=record_id)
        if record is None:
            raise MemoryRepositoryError("Verified memory could not be read back.")
        return record

    def _migrate(self) -> None:
        with self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
            )
            version = self._connection.execute(
                "SELECT version FROM schema_version LIMIT 1"
            ).fetchone()
            if version is None:
                self._connection.execute("INSERT INTO schema_version(version) VALUES (0)")
                current = 0
            else:
                current = int(version["version"])
            if current < 1:
                self._connection.execute(
                    """
                    CREATE TABLE project_memory (
                        id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        category TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        content TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        source_reference TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        session_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        last_verified_at TEXT,
                        stale_after TEXT,
                        metadata_json TEXT NOT NULL,
                        invalidated_at TEXT,
                        PRIMARY KEY (project_id, id)
                    )
                    """
                )
                self._connection.execute(
                    "CREATE INDEX idx_memory_project_category "
                    "ON project_memory(project_id, category)"
                )
                self._connection.execute("UPDATE schema_version SET version = 1")


def _record_values(record: MemoryRecord) -> tuple[object, ...]:
    return (
        record.id,
        record.project_id,
        record.category.value,
        record.kind.value,
        record.content,
        record.source_type.value,
        record.source_reference,
        record.confidence,
        record.session_id,
        _iso(record.created_at),
        _iso(record.updated_at),
        _iso(record.last_verified_at),
        _iso(record.stale_after),
        json.dumps(record.metadata, sort_keys=True, separators=(",", ":")),
        _iso(record.invalidated_at),
    )


def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
    metadata = json.loads(str(row["metadata_json"]))
    if not isinstance(metadata, dict):
        raise MemoryRepositoryError("Stored memory metadata is not an object.")
    return MemoryRecord(
        id=str(row["id"]),
        project_id=str(row["project_id"]),
        category=MemoryCategory(str(row["category"])),
        kind=MemoryKind(str(row["kind"])),
        content=str(row["content"]),
        source_type=MemorySourceType(str(row["source_type"])),
        source_reference=str(row["source_reference"]),
        confidence=float(row["confidence"]),
        session_id=str(row["session_id"]),
        created_at=_datetime(row["created_at"]),
        updated_at=_datetime(row["updated_at"]),
        last_verified_at=_optional_datetime(row["last_verified_at"]),
        stale_after=_optional_datetime(row["stale_after"]),
        metadata=metadata,
        invalidated_at=_optional_datetime(row["invalidated_at"]),
    )


def _tokens(value: str) -> frozenset[str]:
    return frozenset(token.casefold() for token in _TOKEN_PATTERN.findall(value))


def _relevance(query_tokens: frozenset[str], record: MemoryRecord) -> float:
    searchable = _tokens(f"{record.category.value} {record.content} {record.source_reference}")
    if not query_tokens:
        return 0.0
    overlap = len(query_tokens.intersection(searchable)) / len(query_tokens)
    return min(1.0, overlap * record.confidence)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _datetime(value: object) -> datetime:
    return datetime.fromisoformat(str(value))


def _optional_datetime(value: object) -> datetime | None:
    return None if value is None else _datetime(value)
