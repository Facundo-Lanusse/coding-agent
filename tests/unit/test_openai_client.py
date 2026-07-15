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
    assert "function" not in serialized_tools[0]


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
