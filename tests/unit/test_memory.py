from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from coding_agent.memory import (
    MemoryCategory,
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
    MemorySourceType,
    SQLiteMemoryRepository,
)


def record(
    record_id: str,
    *,
    project_id: str = "project-a",
    category: MemoryCategory = MemoryCategory.ARCHITECTURE,
    content: str = "FastAPI routes are registered in app/main.py.",
    stale_after: datetime | None = None,
) -> MemoryRecord:
    now = datetime(2026, 7, 14, tzinfo=UTC)
    return MemoryRecord(
        id=record_id,
        project_id=project_id,
        category=category,
        kind=MemoryKind.OBSERVATION,
        content=content,
        source_type=MemorySourceType.REPOSITORY,
        source_reference="app/main.py:1",
        confidence=0.9,
        session_id="session-1",
        created_at=now,
        updated_at=now,
        last_verified_at=now,
        stale_after=stale_after,
        metadata={"digest": "abc123"},
    )


def test_memory_persists_after_repository_is_closed_and_reopened(tmp_path: Path) -> None:
    database = tmp_path / "memory.sqlite3"
    first = SQLiteMemoryRepository(database)
    first.save(record("architecture-1"))
    first.close()

    second = SQLiteMemoryRepository(database)
    restored = second.get(project_id="project-a", record_id="architecture-1")
    second.close()

    assert restored is not None
    assert restored.content == "FastAPI routes are registered in app/main.py."
    assert restored.metadata == {"digest": "abc123"}


def test_memory_is_strictly_separated_by_project_id(tmp_path: Path) -> None:
    repository = SQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    repository.save(record("shared-id", project_id="project-a"))
    repository.save(
        record(
            "shared-id",
            project_id="project-b",
            content="Project B uses an application factory.",
        )
    )

    assert repository.get(project_id="project-a", record_id="shared-id") is not None
    project_b = repository.get(project_id="project-b", record_id="shared-id")
    assert project_b is not None
    assert project_b.content == "Project B uses an application factory."
    repository.close()


def test_stale_memory_is_marked_and_excluded_by_default(tmp_path: Path) -> None:
    now = datetime(2026, 7, 14, tzinfo=UTC)
    repository = SQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    repository.save(record("old", stale_after=now + timedelta(days=1)))
    invalidated = repository.mark_stale(
        project_id="project-a",
        record_id="old",
        at=now,
    )

    fresh_only = repository.search(
        MemoryQuery(project_id="project-a", text="FastAPI routes"),
        now=now,
    )
    with_stale = repository.search(
        MemoryQuery(
            project_id="project-a",
            text="FastAPI routes",
            include_stale=True,
        ),
        now=now,
    )

    assert invalidated.is_stale(now=now)
    assert fresh_only == ()
    assert len(with_stale) == 1
    assert with_stale[0].stale
    repository.close()


def test_retrieval_filters_category_and_ranks_relevance(tmp_path: Path) -> None:
    repository = SQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    repository.save(record("routes"))
    repository.save(
        record(
            "database",
            content="The service stores audit events in SQLite.",
        )
    )
    repository.save(
        record(
            "command",
            category=MemoryCategory.USEFUL_COMMAND,
            content="Run pytest tests/unit for checks.",
        )
    )

    results = repository.search(
        MemoryQuery(
            project_id="project-a",
            text="FastAPI routes",
            categories=(MemoryCategory.ARCHITECTURE,),
        )
    )

    assert [item.record.id for item in results] == ["routes"]
    assert results[0].relevance > 0.5
    repository.close()


def test_inference_cannot_be_saved_without_supporting_sources() -> None:
    with pytest.raises(ValidationError, match=r"metadata\.supports"):
        MemoryRecord(
            id="inference-1",
            project_id="project-a",
            category=MemoryCategory.DECISION,
            kind=MemoryKind.INFERENCE,
            content="The route likely needs a cache.",
            source_type=MemorySourceType.INFERENCE,
            source_reference="agent inference",
            confidence=0.4,
            session_id="session-1",
        )


def test_model_inference_cannot_be_mislabeled_as_observation() -> None:
    with pytest.raises(ValidationError, match="classified consistently"):
        MemoryRecord(
            id="mislabeled-1",
            project_id="project-a",
            category=MemoryCategory.ARCHITECTURE,
            kind=MemoryKind.OBSERVATION,
            content="The project probably uses a hidden cache.",
            source_type=MemorySourceType.INFERENCE,
            source_reference="model output",
            confidence=0.3,
            session_id="session-1",
        )
