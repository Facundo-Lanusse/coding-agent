"""OpenAI Responses API adapter.

The adapter converts SDK objects into project-owned models. The harness only
depends on :class:`LLMClient` and can therefore use deterministic fakes.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Protocol, cast

from coding_agent.llm.base import (
    LLMConfigurationError,
    LLMProviderError,
    LLMResponseError,
)
from coding_agent.models import (
    FunctionCall,
    FunctionCallOutput,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    MessageInput,
    ProviderInput,
    ToolDefinition,
)


class ResponsesResource(Protocol):
    def create(self, **kwargs: object) -> object:
        """Create one response."""


class OpenAICompatibleClient(Protocol):
    @property
    def responses(self) -> ResponsesResource:
        """Expose the Responses API resource."""


class OpenAIResponsesClient:
    """Synchronous OpenAI adapter using ``client.responses.create`` directly."""

    def __init__(
        self,
        *,
        model: str,
        max_output_tokens: int,
        store_responses: bool,
        api_key: str | None = None,
        client: OpenAICompatibleClient | None = None,
    ) -> None:
        if not model.strip():
            raise LLMConfigurationError("OpenAI model must not be empty.")
        if max_output_tokens <= 0:
            raise LLMConfigurationError("OpenAI max_output_tokens must be positive.")

        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise LLMConfigurationError(
                    "The OpenAI SDK is required to use the real adapter."
                ) from exc

            sdk_client = OpenAI(api_key=api_key) if api_key is not None else OpenAI()
            client = cast(OpenAICompatibleClient, sdk_client)

        self._client = client
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._store_responses = store_responses

    def respond(self, request: LLMRequest) -> LLMResponse:
        payload: dict[str, object] = {
            "model": self._model,
            "instructions": request.instructions,
            "input": [self._serialize_input(item) for item in request.input],
            "max_output_tokens": self._max_output_tokens,
            "store": self._store_responses,
        }
        if request.tools:
            payload["tools"] = [self._serialize_tool(tool) for tool in request.tools]

        try:
            raw_response = self._client.responses.create(**payload)
        except Exception as exc:
            raise LLMProviderError(_provider_error_message(exc)) from exc

        return self._parse_response(raw_response)

    @staticmethod
    def _serialize_input(item: MessageInput | FunctionCallOutput | ProviderInput) -> object:
        if isinstance(item, MessageInput):
            return {"role": item.role.value, "content": item.content}
        if isinstance(item, FunctionCallOutput):
            return {
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": item.output,
            }
        return item.data

    @staticmethod
    def _serialize_tool(tool: ToolDefinition) -> dict[str, object]:
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "strict": tool.strict,
        }

    @staticmethod
    def _parse_response(raw_response: object) -> LLMResponse:
        output = getattr(raw_response, "output", ())
        if not isinstance(output, Sequence) or isinstance(output, str | bytes):
            raise LLMResponseError("OpenAI response output must be a sequence.")

        continuation: list[ProviderInput] = []
        tool_calls: list[FunctionCall] = []
        for raw_item in output:
            item = _object_to_dict(raw_item)
            continuation.append(ProviderInput(data=item))
            if item.get("type") != "function_call":
                continue

            call_id = _required_string(item, "call_id")
            name = _required_string(item, "name")
            arguments, arguments_error = _parse_arguments(item.get("arguments"))
            tool_calls.append(
                FunctionCall(
                    call_id=call_id,
                    name=name,
                    arguments=arguments,
                    arguments_error=arguments_error,
                )
            )

        usage_object = getattr(raw_response, "usage", None)
        usage = LLMUsage(
            input_tokens=_integer_attribute(usage_object, "input_tokens"),
            output_tokens=_integer_attribute(usage_object, "output_tokens"),
            total_tokens=_integer_attribute(usage_object, "total_tokens"),
        )
        return LLMResponse(
            response_id=_optional_string_attribute(raw_response, "id"),
            model=_optional_string_attribute(raw_response, "model"),
            text=_optional_string_attribute(raw_response, "output_text") or "",
            tool_calls=tuple(tool_calls),
            continuation=tuple(continuation),
            usage=usage,
        )


def _object_to_dict(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise LLMResponseError("OpenAI response item keys must be strings.")
            result[key] = item
        return result

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        raw: object = to_dict()
        return _object_to_dict(raw)

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        raw = model_dump(mode="json")
        return _object_to_dict(raw)

    raise LLMResponseError(f"Unsupported OpenAI response item type: {type(value).__name__}.")


def _required_string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise LLMResponseError(f"OpenAI function call is missing a valid {key}.")
    return value


def _parse_arguments(value: object) -> tuple[dict[str, object], str | None]:
    if isinstance(value, str):
        try:
            parsed: object = json.loads(value)
        except json.JSONDecodeError:
            return {}, "OpenAI function call arguments are not valid JSON."
    else:
        parsed = value

    if not isinstance(parsed, dict):
        return {}, "OpenAI function call arguments must be a JSON object."

    arguments: dict[str, object] = {}
    for key, item in parsed.items():
        if not isinstance(key, str):
            raise LLMResponseError("OpenAI function argument keys must be strings.")
        arguments[key] = item
    return arguments, None


def _optional_string_attribute(value: object, name: str) -> str | None:
    attribute = getattr(value, name, None)
    return attribute if isinstance(attribute, str) else None


def _integer_attribute(value: object, name: str) -> int:
    attribute = getattr(value, name, 0)
    return attribute if isinstance(attribute, int) and attribute >= 0 else 0


_SECRET_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_-]{8,}\b"),
)
_MAX_PROVIDER_ERROR_CHARS = 500


def _provider_error_message(exc: Exception) -> str:
    prefix = f"OpenAI Responses API request failed ({type(exc).__name__})."
    detail = " ".join(str(exc).split())
    for pattern in _SECRET_PATTERNS:
        detail = pattern.sub("[REDACTED]", detail)
    if not detail:
        return prefix
    return f"{prefix} {detail[:_MAX_PROVIDER_ERROR_CHARS]}"
