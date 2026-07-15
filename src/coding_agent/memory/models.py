"""Typed project-memory records with provenance and freshness."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field, model_validator

from coding_agent.models import FrozenModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class MemoryCategory(StrEnum):
    ARCHITECTURE = "architecture"
    IMPORTANT_FILE = "important_file"
    DEPENDENCY = "dependency"
    USEFUL_COMMAND = "useful_command"
    CONVENTION = "convention"
    DECISION = "decision"
    INVESTIGATED_BUG = "investigated_bug"
    CHECK_RESULT = "check_result"
    SESSION_SUMMARY = "session_summary"


class MemoryKind(StrEnum):
    OBSERVATION = "observation"
    DECISION = "decision"
    INFERENCE = "inference"
    SESSION_SUMMARY = "session_summary"


class MemorySourceType(StrEnum):
    REPOSITORY = "repository"
    TOOL_OUTPUT = "tool_output"
    USER = "user"
    WEB = "web"
    MEMORY_IMPORT = "memory_import"
    INFERENCE = "inference"


class MemoryRecord(FrozenModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category: MemoryCategory
    kind: MemoryKind
    content: str = Field(min_length=1)
    source_type: MemorySourceType
    source_reference: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    session_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_verified_at: datetime | None = None
    stale_after: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    invalidated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_provenance(self) -> MemoryRecord:
        if (self.kind is MemoryKind.INFERENCE) != (self.source_type is MemorySourceType.INFERENCE):
            raise ValueError("inference source and kind must be classified consistently")
        if self.kind is MemoryKind.INFERENCE:
            supports = self.metadata.get("supports")
            if not isinstance(supports, list) or not supports:
                raise ValueError("inference memory requires non-empty metadata.supports")
        try:
            json.dumps(self.metadata, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("memory metadata must be JSON serializable") from exc
        return self

    def is_stale(self, *, now: datetime | None = None) -> bool:
        reference = now or utc_now()
        return self.invalidated_at is not None or (
            self.stale_after is not None and reference >= self.stale_after
        )


class MemoryQuery(FrozenModel):
    project_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    categories: tuple[MemoryCategory, ...] = ()
    kinds: tuple[MemoryKind, ...] = ()
    include_stale: bool = False
    limit: int = Field(default=10, ge=1, le=100)


class MemorySearchResult(FrozenModel):
    record: MemoryRecord
    relevance: float = Field(ge=0.0, le=1.0)
    stale: bool
