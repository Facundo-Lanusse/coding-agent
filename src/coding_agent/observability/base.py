"""Safe provider-neutral tracing contracts."""

from __future__ import annotations

from types import TracebackType
from typing import Literal, Protocol, Self

from coding_agent.observability.models import ObservationKind


class Observation(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]: ...

    def update(
        self,
        *,
        output: object | None = None,
        metadata: dict[str, object] | None = None,
        error: object | None = None,
    ) -> None: ...


class Tracer(Protocol):
    def observe(
        self,
        name: str,
        *,
        kind: ObservationKind = ObservationKind.SPAN,
        input: object | None = None,
        metadata: dict[str, object] | None = None,
    ) -> Observation: ...

    def flush(self) -> None: ...
