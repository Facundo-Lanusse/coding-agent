"""Provider-neutral observation models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ObservationKind(StrEnum):
    TASK = "task"
    SPAN = "span"
    AGENT = "agent"
    GENERATION = "generation"
    TOOL = "tool"
    RETRIEVER = "retriever"
    EVENT = "event"


@dataclass(slots=True)
class ObservationRecord:
    """In-memory test record with explicit parentage."""

    observation_id: str
    parent_id: str | None
    name: str
    kind: ObservationKind
    input: object | None = None
    output: object | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    error: object | None = None
    started_ns: int = 0
    ended_ns: int | None = None
