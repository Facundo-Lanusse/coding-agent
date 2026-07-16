"""Optional Langfuse v4 adapter with failure isolation."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from contextlib import AbstractContextManager, suppress
from importlib import import_module
from types import TracebackType
from typing import Literal, Protocol, Self, cast

from coding_agent.config import ObservabilityConfig
from coding_agent.observability.base import Tracer
from coding_agent.observability.models import ObservationKind
from coding_agent.observability.noop import NoOpTracer
from coding_agent.observability.sanitizer import Sanitizer


class LangfuseObservationHandle(Protocol):
    def update(self, **kwargs: object) -> object: ...


class LangfuseClient(Protocol):
    def start_as_current_observation(
        self, **kwargs: object
    ) -> AbstractContextManager[LangfuseObservationHandle]: ...

    def flush(self) -> object: ...


_KIND_MAP: Mapping[ObservationKind, str] = {
    ObservationKind.TASK: "chain",
    ObservationKind.SPAN: "span",
    ObservationKind.AGENT: "agent",
    ObservationKind.GENERATION: "generation",
    ObservationKind.TOOL: "tool",
    ObservationKind.RETRIEVER: "retriever",
    ObservationKind.EVENT: "event",
}


class LangfuseTracer:
    """Maps project observations to the current Langfuse observation API."""

    def __init__(
        self,
        client: LangfuseClient,
        sanitizer: Sanitizer,
        *,
        trace_id: str | None = None,
    ) -> None:
        self._client = client
        self._sanitizer = sanitizer
        self._trace_id = trace_id
        self._root_claimed = False

    @property
    def trace_id(self) -> str | None:
        return self._trace_id

    def claim_trace_context(self) -> dict[str, str] | None:
        if self._root_claimed or self._trace_id is None:
            return None
        self._root_claimed = True
        return {"trace_id": self._trace_id}

    def observe(
        self,
        name: str,
        *,
        kind: ObservationKind = ObservationKind.SPAN,
        input: object | None = None,
        metadata: dict[str, object] | None = None,
    ) -> LangfuseObservation:
        return LangfuseObservation(
            tracer=self,
            client=self._client,
            sanitizer=self._sanitizer,
            name=name,
            kind=kind,
            input=input,
            metadata=metadata or {},
        )

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception:
            return None


class LangfuseObservation:
    """Context manager that never lets telemetry failures affect domain work."""

    def __init__(
        self,
        *,
        tracer: LangfuseTracer,
        client: LangfuseClient,
        sanitizer: Sanitizer,
        name: str,
        kind: ObservationKind,
        input: object | None,
        metadata: dict[str, object],
    ) -> None:
        self._tracer = tracer
        self._client = client
        self._sanitizer = sanitizer
        self._name = name
        self._kind = kind
        self._input = input
        self._metadata = metadata
        self._manager: AbstractContextManager[LangfuseObservationHandle] | None = None
        self._remote: LangfuseObservationHandle | None = None

    def __enter__(self) -> Self:
        try:
            sanitized_metadata = self._sanitizer.sanitize(self._metadata)
            metadata = sanitized_metadata if isinstance(sanitized_metadata, dict) else {}
            arguments: dict[str, object] = {
                "name": self._name,
                "as_type": _KIND_MAP[self._kind],
                "input": self._sanitizer.content(self._input),
                "metadata": metadata,
            }
            trace_context = self._tracer.claim_trace_context()
            if trace_context is not None:
                arguments["trace_context"] = trace_context
            model = metadata.get("model")
            if self._kind is ObservationKind.GENERATION and isinstance(model, str):
                arguments["model"] = model
            self._manager = self._client.start_as_current_observation(**arguments)
            self._remote = self._manager.__enter__()
            remote_trace_id = getattr(self._remote, "trace_id", None)
            if isinstance(remote_trace_id, str) and remote_trace_id:
                self._tracer._trace_id = remote_trace_id
        except Exception:
            self._manager = None
            self._remote = None
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        if exc is not None:
            self.update(error=str(exc), metadata={"error_type": type(exc).__name__})
        if self._manager is not None:
            with suppress(Exception):
                self._manager.__exit__(exc_type, exc, traceback)
        return False

    def update(
        self,
        *,
        output: object | None = None,
        metadata: dict[str, object] | None = None,
        error: object | None = None,
    ) -> None:
        if self._remote is None:
            return
        payload: dict[str, object] = {}
        if output is not None:
            payload["output"] = self._sanitizer.content(output)
        if metadata:
            sanitized = self._sanitizer.sanitize(metadata)
            safe_metadata = sanitized if isinstance(sanitized, dict) else {}
            payload["metadata"] = safe_metadata
            if self._kind is ObservationKind.GENERATION:
                usage = _usage_details(safe_metadata)
                if usage:
                    payload["usage_details"] = usage
                cost = safe_metadata.get("cost")
                if isinstance(cost, int | float) and cost >= 0:
                    payload["cost_details"] = {"total": float(cost)}
        if error is not None:
            payload.update(
                {
                    "level": "ERROR",
                    "status_message": self._sanitizer.content(error),
                }
            )
        try:
            self._remote.update(**payload)
        except Exception:
            return


def create_tracer(
    config: ObservabilityConfig,
    *,
    environment: Mapping[str, str] | None = None,
    client: LangfuseClient | None = None,
    trace_seed: str | None = None,
) -> Tracer:
    """Return no-op unless telemetry is enabled and usable."""

    env = os.environ if environment is None else environment
    if not config.enabled:
        return NoOpTracer()
    if client is None and not _credentials_present(env):
        return NoOpTracer()
    sanitizer = Sanitizer(
        max_payload_chars=config.max_payload_chars,
        capture_content=config.capture_content,
        environment=env,
    )
    if client is None:
        try:
            module = import_module("langfuse")
            get_client = module.get_client
        except (ImportError, AttributeError):
            return NoOpTracer()
        try:
            client = cast(LangfuseClient, get_client())
        except Exception:
            return NoOpTracer()
    trace_id = _trace_id(client, trace_seed) if trace_seed is not None else None
    return LangfuseTracer(client, sanitizer, trace_id=trace_id)


def _credentials_present(environment: Mapping[str, str]) -> bool:
    return bool(environment.get("LANGFUSE_PUBLIC_KEY") and environment.get("LANGFUSE_SECRET_KEY"))


def _trace_id(client: LangfuseClient, seed: str) -> str:
    create = getattr(client, "create_trace_id", None)
    if callable(create):
        try:
            value = create(seed=seed)
            if isinstance(value, str) and len(value) == 32:
                return value
        except Exception:
            pass
    return hashlib.sha256(seed.encode()).hexdigest()[:32]


def _usage_details(metadata: Mapping[str, object]) -> dict[str, int]:
    pairs = {
        "input": metadata.get("input_tokens"),
        "output": metadata.get("output_tokens"),
        "total": metadata.get("total_tokens"),
    }
    return {
        key: value
        for key, value in pairs.items()
        if isinstance(value, int) and value >= 0
    }
