"""Provider-neutral LLM boundary."""

from __future__ import annotations

from typing import Protocol

from coding_agent.models import LLMRequest, LLMResponse


class LLMClientError(Exception):
    """Base exception for explicit LLM adapter failures."""

    code = "llm_client_error"


class LLMConfigurationError(LLMClientError):
    code = "llm_configuration_error"


class LLMProviderError(LLMClientError):
    code = "llm_provider_error"


class LLMResponseError(LLMClientError):
    code = "llm_response_error"


class LLMClient(Protocol):
    """Synchronous client contract used by the explicit harness."""

    def respond(self, request: LLMRequest) -> LLMResponse:
        """Return one provider-neutral model response."""
