"""Opt-in smoke test for a real Langfuse project."""

from __future__ import annotations

import os

import pytest

from coding_agent.config import ObservabilityConfig
from coding_agent.observability import NoOpTracer, ObservationKind, create_tracer

pytestmark = pytest.mark.langfuse_integration


@pytest.mark.skipif(
    not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")),
    reason="LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required",
)
def test_real_langfuse_trace_can_be_flushed() -> None:
    pytest.importorskip("langfuse", reason="optional Langfuse SDK is not installed")
    config = ObservabilityConfig(
        provider="langfuse",
        enabled=True,
        redact_sensitive_data=True,
        capture_content=False,
        max_payload_chars=2_000,
    )
    tracer = create_tracer(config)
    assert not isinstance(tracer, NoOpTracer)

    with tracer.observe(
        "coding-agent.integration-smoke",
        kind=ObservationKind.TASK,
        input={"content": "disabled by test configuration"},
        metadata={"test": "langfuse_integration"},
    ) as observation:
        observation.update(output={"status": "completed"})
    tracer.flush()

