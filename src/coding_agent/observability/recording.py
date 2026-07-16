"""Deterministic in-memory tracer for tests and local inspection."""

from __future__ import annotations

import time
from contextvars import ContextVar, Token
from types import TracebackType
from typing import Literal, Self

from coding_agent.observability.models import ObservationKind, ObservationRecord
from coding_agent.observability.sanitizer import Sanitizer


class RecordingTracer:
    def __init__(self, sanitizer: Sanitizer | None = None) -> None:
        self.sanitizer = sanitizer or Sanitizer(environment={})
        self.records: list[ObservationRecord] = []
        self._current: ContextVar[str | None] = ContextVar("recording_parent", default=None)

    @property
    def trace_id(self) -> str:
        return "recording-trace"

    def observe(
        self,
        name: str,
        *,
        kind: ObservationKind = ObservationKind.SPAN,
        input: object | None = None,
        metadata: dict[str, object] | None = None,
    ) -> RecordingObservation:
        record = ObservationRecord(
            observation_id=f"observation-{len(self.records) + 1}",
            parent_id=self._current.get(),
            name=name,
            kind=kind,
            input=self.sanitizer.content(input),
            metadata=_dict(self.sanitizer.sanitize(metadata or {})),
            started_ns=time.perf_counter_ns(),
        )
        self.records.append(record)
        return RecordingObservation(self, record)

    def flush(self) -> None:
        return None


class RecordingObservation:
    def __init__(self, tracer: RecordingTracer, record: ObservationRecord) -> None:
        self._tracer = tracer
        self._record = record
        self._token: Token[str | None] | None = None

    def __enter__(self) -> Self:
        self._token = self._tracer._current.set(self._record.observation_id)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        self._record.ended_ns = time.perf_counter_ns()
        self._record.metadata.setdefault(
            "latency_ms", (self._record.ended_ns - self._record.started_ns) / 1_000_000
        )
        if exc is not None:
            self._record.error = self._tracer.sanitizer.content(str(exc))
        if self._token is not None:
            self._tracer._current.reset(self._token)
        return False

    def update(
        self,
        *,
        output: object | None = None,
        metadata: dict[str, object] | None = None,
        error: object | None = None,
    ) -> None:
        if output is not None:
            self._record.output = self._tracer.sanitizer.content(output)
        if metadata:
            self._record.metadata.update(_dict(self._tracer.sanitizer.sanitize(metadata)))
        if error is not None:
            self._record.error = self._tracer.sanitizer.content(error)


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {"value": value}
