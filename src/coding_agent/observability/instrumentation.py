"""Composable tracing wrappers for external/domain ports."""

from __future__ import annotations

import time
from collections.abc import Callable

from coding_agent.llm.base import LLMClient
from coding_agent.models import LLMRequest, LLMResponse
from coding_agent.observability.base import Tracer
from coding_agent.observability.models import ObservationKind

CostEstimator = Callable[[str, int, int], float]


class TracedLLMClient:
    """LLM decorator that records generations without coupling an SDK adapter."""

    def __init__(
        self,
        client: LLMClient,
        tracer: Tracer,
        *,
        configured_model: str | None = None,
        cost_estimator: CostEstimator | None = None,
    ) -> None:
        self._client = client
        self._tracer = tracer
        self._configured_model = configured_model
        self._cost_estimator = cost_estimator

    def respond(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        with self._tracer.observe(
            "llm.response",
            kind=ObservationKind.GENERATION,
            input={"instructions": request.instructions, "input": request.input},
            metadata={
                "model": self._configured_model,
                "tool_names": [tool.name for tool in request.tools],
            },
        ) as observation:
            try:
                response = self._client.respond(request)
            except Exception as exc:
                observation.update(
                    error=str(exc),
                    metadata={"latency_ms": (time.perf_counter() - started) * 1000},
                )
                raise
            model = response.model or self._configured_model
            metadata: dict[str, object] = {
                "model": model,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.total_tokens,
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
            if model is not None and self._cost_estimator is not None:
                metadata["cost"] = self._cost_estimator(
                    model,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )
                metadata["cost_source"] = "estimated"
            observation.update(
                output={"text": response.text, "tool_calls": response.tool_calls},
                metadata=metadata,
            )
            return response
