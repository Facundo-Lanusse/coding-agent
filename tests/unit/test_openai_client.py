from __future__ import annotations

from types import SimpleNamespace

import pytest

from coding_agent.llm import LLMProviderError, OpenAIResponsesClient
from coding_agent.models import (
    FunctionCallOutput,
    LLMRequest,
    MessageInput,
    MessageRole,
    ToolDefinition,
)


class FakeResponseItem:
    def __init__(self, data: dict[str, object]) -> None:
        self._data = data

    def to_dict(self) -> dict[str, object]:
        return self._data


class FakeResponsesResource:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class FakeSDKClient:
    def __init__(self, response: object) -> None:
        self.responses = FakeResponsesResource(response)


class FailingResponsesResource:
    def create(self, **kwargs: object) -> object:
        raise RuntimeError("provider unavailable")


class FailingSDKClient:
    responses = FailingResponsesResource()


class SensitiveFailingResponsesResource:
    def create(self, **kwargs: object) -> object:
        raise RuntimeError(
            "Invalid schema for function. Authorization: Bearer sk-test-secret-value"
        )


class SensitiveFailingSDKClient:
    responses = SensitiveFailingResponsesResource()


def test_openai_adapter_uses_responses_api_and_maps_function_call() -> None:
    raw_response = SimpleNamespace(
        id="response-1",
        model="configured-model",
        output_text="",
        output=[
            FakeResponseItem(
                {
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "echo",
                    "arguments": '{"value": "hello"}',
                }
            )
        ],
        usage=SimpleNamespace(input_tokens=10, output_tokens=4, total_tokens=14),
    )
    sdk = FakeSDKClient(raw_response)
    adapter = OpenAIResponsesClient(
        model="configured-model",
        max_output_tokens=500,
        store_responses=False,
        client=sdk,
    )
    tool = ToolDefinition(
        name="echo",
        description="Echo a value.",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )

    response = adapter.respond(
        LLMRequest(
            instructions="Use tools when needed.",
            input=(
                MessageInput(role=MessageRole.USER, content="Echo hello"),
                FunctionCallOutput(call_id="prior-call", output="prior output"),
            ),
            tools=(tool,),
        )
    )

    assert response.response_id == "response-1"
    assert response.tool_calls[0].arguments == {"value": "hello"}
    assert response.usage.total_tokens == 14
    assert len(response.continuation) == 1

    request_payload = sdk.responses.calls[0]
    assert request_payload["model"] == "configured-model"
    assert request_payload["store"] is False
    serialized_tools = request_payload["tools"]
    assert isinstance(serialized_tools, list)
    assert serialized_tools[0]["type"] == "function"
    assert serialized_tools[0]["name"] == "echo"
    assert serialized_tools[0]["strict"] is True
    assert "function" not in serialized_tools[0]


def test_openai_adapter_preserves_malformed_function_call_for_recovery() -> None:
    raw_response = SimpleNamespace(
        id="response-malformed-call",
        model="configured-model",
        output_text="",
        output=[
            FakeResponseItem(
                {
                    "type": "function_call",
                    "call_id": "call-malformed",
                    "name": "read_file",
                    "arguments": '{"path": "app/main.py"',
                }
            )
        ],
        usage=SimpleNamespace(input_tokens=10, output_tokens=4, total_tokens=14),
    )
    adapter = OpenAIResponsesClient(
        model="configured-model",
        max_output_tokens=500,
        store_responses=False,
        client=FakeSDKClient(raw_response),
    )

    response = adapter.respond(
        LLMRequest(
            instructions="Use tools when needed.",
            input=(MessageInput(role=MessageRole.USER, content="Inspect the app"),),
        )
    )

    assert response.tool_calls[0].call_id == "call-malformed"
    assert response.tool_calls[0].arguments == {}
    assert response.tool_calls[0].arguments_error == (
        "OpenAI function call arguments are not valid JSON."
    )
    assert response.continuation[0].data["call_id"] == "call-malformed"


def test_openai_adapter_wraps_provider_error_without_real_api_call() -> None:
    adapter = OpenAIResponsesClient(
        model="configured-model",
        max_output_tokens=500,
        store_responses=False,
        client=FailingSDKClient(),
    )

    with pytest.raises(LLMProviderError, match="RuntimeError"):
        adapter.respond(
            LLMRequest(
                instructions="Return text.",
                input=(MessageInput(role=MessageRole.USER, content="Hello"),),
            )
        )


def test_openai_adapter_reports_sanitized_provider_detail() -> None:
    adapter = OpenAIResponsesClient(
        model="configured-model",
        max_output_tokens=500,
        store_responses=False,
        client=SensitiveFailingSDKClient(),
    )

    with pytest.raises(LLMProviderError) as captured:
        adapter.respond(
            LLMRequest(
                instructions="Return text.",
                input=(MessageInput(role=MessageRole.USER, content="Hello"),),
            )
        )

    message = str(captured.value)
    assert "Invalid schema for function" in message
    assert "sk-test-secret-value" not in message
    assert "Bearer [REDACTED]" not in message
    assert "[REDACTED]" in message
