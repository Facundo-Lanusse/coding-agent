"""Zero-dependency tracing fallback."""

from __future__ import annotations

from types import TracebackType
from typing import Literal, Self

from coding_agent.observability.models import ObservationKind


class NoOpObservation:
    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        return False

    def update(
        self,
        *,
        output: object | None = None,
        metadata: dict[str, object] | None = None,
        error: object | None = None,
    ) -> None:
        del output, metadata, error


class NoOpTracer:
    """Accept every observation call and perform no external work."""

    @property
    def trace_id(self) -> str | None:
        return None

    def observe(
        self,
        name: str,
        *,
        kind: ObservationKind = ObservationKind.SPAN,
        input: object | None = None,
        metadata: dict[str, object] | None = None,
    ) -> NoOpObservation:
        del name, kind, input, metadata
        return NoOpObservation()

    def flush(self) -> None:
        return None
