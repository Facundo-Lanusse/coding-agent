"""Persistent local SQLite vector store with collection versioning."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

from coding_agent.rag.models import (
    ChunkMetadata,
    CollectionSpec,
    DocumentChunk,
    EmbeddedChunk,
    RAGSourceType,
    RetrievalHit,
    UpsertReport,
)


class VectorStoreError(Exception):
    code = "vector_store_error"


class VectorStore(Protocol):
    def ensure_collection(self, spec: CollectionSpec) -> None: ...

    def upsert(self, spec: CollectionSpec, chunks: Sequence[EmbeddedChunk]) -> UpsertReport: ...

    def query(
        self,
        spec: CollectionSpec,
        vector: Sequence[float],
        *,
        top_k: int,
        minimum_score: float,
    ) -> tuple[RetrievalHit, ...]: ...

    def close(self) -> None: ...


class SQLiteVectorStore:
    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> SQLiteVectorStore:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def ensure_collection(self, spec: CollectionSpec) -> None:
        row = self._connection.execute(
            "SELECT embedding_model, dimension FROM vector_collections WHERE name=? AND version=?",
            (spec.name, spec.version),
        ).fetchone()
        if row is not None:
            incompatible = (
                str(row["embedding_model"]) != spec.embedding_model
                or int(row["dimension"]) != spec.dimension
            )
            if incompatible:
                raise VectorStoreError("Collection embedding configuration is incompatible.")
            return
        with self._connection:
            self._connection.execute(
                "INSERT INTO vector_collections"
                "(name, version, embedding_model, dimension) VALUES(?,?,?,?)",
                (spec.name, spec.version, spec.embedding_model, spec.dimension),
            )

    def upsert(self, spec: CollectionSpec, chunks: Sequence[EmbeddedChunk]) -> UpsertReport:
        self.ensure_collection(spec)
        inserted = 0
        skipped = 0
        with self._connection:
            for item in chunks:
                if len(item.embedding) != spec.dimension:
                    raise VectorStoreError("Chunk embedding dimension is incompatible.")
                metadata = item.chunk.metadata
                cursor = self._connection.execute(
                    """
                    INSERT OR IGNORE INTO vector_chunks(
                        collection_name, collection_version, chunk_id, text, token_count,
                        embedding_json, source_id, source_type, path_or_url, title,
                        section, ecosystem, source_version, chunk_index, checksum,
                        ingested_at, content_type
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        spec.name,
                        spec.version,
                        item.chunk.chunk_id,
                        item.chunk.text,
                        item.chunk.token_count,
                        json.dumps(item.embedding, separators=(",", ":")),
                        metadata.source_id,
                        metadata.source_type.value,
                        metadata.path_or_url,
                        metadata.title,
                        metadata.section,
                        metadata.ecosystem,
                        metadata.version,
                        metadata.chunk_index,
                        metadata.checksum,
                        metadata.ingested_at.isoformat(),
                        metadata.content_type,
                    ),
                )
                if cursor.rowcount == 1:
                    inserted += 1
                else:
                    skipped += 1
        return UpsertReport(inserted=inserted, skipped_duplicates=skipped)

    def query(
        self,
        spec: CollectionSpec,
        vector: Sequence[float],
        *,
        top_k: int,
        minimum_score: float,
    ) -> tuple[RetrievalHit, ...]:
        self.ensure_collection(spec)
        if len(vector) != spec.dimension:
            raise VectorStoreError("Query embedding dimension is incompatible.")
        rows = self._connection.execute(
            "SELECT * FROM vector_chunks WHERE collection_name=? AND collection_version=?",
            (spec.name, spec.version),
        ).fetchall()
        hits: list[RetrievalHit] = []
        for row in rows:
            stored = tuple(float(value) for value in json.loads(str(row["embedding_json"])))
            score = _cosine(vector, stored)
            if score >= minimum_score:
                hits.append(RetrievalHit(chunk=_row_chunk(row), score=score))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return tuple(hits[:top_k])

    def count(self, spec: CollectionSpec) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS count FROM vector_chunks "
            "WHERE collection_name=? AND collection_version=?",
            (spec.name, spec.version),
        ).fetchone()
        return 0 if row is None else int(row["count"])

    def _migrate(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS vector_collections(
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    dimension INTEGER NOT NULL,
                    PRIMARY KEY(name, version)
                );
                CREATE TABLE IF NOT EXISTS vector_chunks(
                    collection_name TEXT NOT NULL,
                    collection_version TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    embedding_json TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    path_or_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    section TEXT NOT NULL,
                    ecosystem TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    checksum TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    PRIMARY KEY(
                        collection_name, collection_version, source_id, checksum, chunk_index
                    ),
                    FOREIGN KEY(collection_name, collection_version)
                        REFERENCES vector_collections(name, version)
                );
                """
            )


def _row_chunk(row: sqlite3.Row) -> DocumentChunk:
    metadata = ChunkMetadata(
        source_id=str(row["source_id"]),
        source_type=RAGSourceType(str(row["source_type"])),
        path_or_url=str(row["path_or_url"]),
        title=str(row["title"]),
        section=str(row["section"]),
        ecosystem=str(row["ecosystem"]),
        version=str(row["source_version"]),
        chunk_index=int(row["chunk_index"]),
        checksum=str(row["checksum"]),
        ingested_at=datetime.fromisoformat(str(row["ingested_at"])),
        content_type=str(row["content_type"]),
    )
    return DocumentChunk(
        chunk_id=str(row["chunk_id"]),
        text=str(row["text"]),
        token_count=int(row["token_count"]),
        metadata=metadata,
    )


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise VectorStoreError("Stored embedding dimension is invalid.")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return 0.0 if left_norm == 0.0 or right_norm == 0.0 else dot / (left_norm * right_norm)
