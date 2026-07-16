from __future__ import annotations

from collections.abc import Sequence

from coding_agent.harness import CodingAgentHarness, ToolBinding
from coding_agent.models import (
    AgentRunRequest,
    ApprovalDecision,
    ApprovalRequest,
    FunctionCall,
    FunctionCallOutput,
    LLMRequest,
    LLMResponse,
    MessageInput,
    Plan,
    ProviderInput,
    RunStatus,
    ToolDefinition,
    ToolResult,
    ToolStatus,
)


class FakeLLM:
    def __init__(self, responses: Sequence[LLMResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[LLMRequest] = []

    def respond(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("FakeLLM received an unexpected request")
        return self._responses.pop(0)


class RecordingApprovalProvider:
    def __init__(self, approved: bool) -> None:
        self.approved = approved
        self.requests: list[ApprovalRequest] = []

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        self.requests.append(request)
        return ApprovalDecision(
            approved=self.approved,
            reason="approved in test" if self.approved else "rejected in test",
        )


class RecordingTool:
    def __init__(self) -> None:
        self.calls: list[FunctionCall] = []

    def __call__(self, call: FunctionCall) -> ToolResult:
        self.calls.append(call)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status=ToolStatus.EXECUTED,
            output=f"echo:{call.arguments['value']}",
        )


ECHO_DEFINITION = ToolDefinition(
    name="echo",
    description="Echo a value for a deterministic harness test.",
    parameters={
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    },
)


def _tool_response(call_id: str) -> LLMResponse:
    call_data: dict[str, object] = {
        "type": "function_call",
        "call_id": call_id,
        "name": "echo",
        "arguments": '{"value": "hello"}',
    }
    return LLMResponse(
        tool_calls=(FunctionCall(call_id=call_id, name="echo", arguments={"value": "hello"}),),
        continuation=(ProviderInput(data=call_data),),
    )


def test_harness_returns_final_answer_without_tools() -> None:
    llm = FakeLLM((LLMResponse(text="Task complete."),))
    harness = CodingAgentHarness(llm)

    result = harness.run(
        AgentRunRequest(task="Explain the project", plan_mode=False, supervision_mode=False)
    )

    assert result.status is RunStatus.COMPLETED
    assert result.final_answer == "Task complete."
    assert result.metrics.model_iterations == 1
    assert result.metrics.tool_calls == 0
    assert len(harness.history) == 2


def test_harness_executes_fake_tool_and_returns_result_to_model() -> None:
    llm = FakeLLM((_tool_response("call-1"), LLMResponse(text="Echo completed.")))
    tool = RecordingTool()
    harness = CodingAgentHarness(
        llm,
        tools=(ToolBinding(definition=ECHO_DEFINITION, handler=tool),),
    )

    result = harness.run(
        AgentRunRequest(task="Echo hello", plan_mode=False, supervision_mode=False)
    )

    assert result.status is RunStatus.COMPLETED
    assert result.metrics.model_iterations == 2
    assert result.metrics.tool_calls == 1
    assert result.tool_results[0].status is ToolStatus.EXECUTED
    assert len(tool.calls) == 1
    assert any(isinstance(item, FunctionCallOutput) for item in llm.requests[1].input)


def test_harness_stops_at_iteration_limit() -> None:
    llm = FakeLLM((_tool_response("call-1"), _tool_response("call-2")))
    tool = RecordingTool()
    harness = CodingAgentHarness(
        llm,
        tools=(ToolBinding(definition=ECHO_DEFINITION, handler=tool),),
    )

    result = harness.run(
        AgentRunRequest(
            task="Keep echoing",
            plan_mode=False,
            supervision_mode=False,
            max_iterations=2,
        )
    )

    assert result.status is RunStatus.MAX_ITERATIONS
    assert result.metrics.model_iterations == 2
    assert result.metrics.tool_calls == 2
    assert result.error is not None
    assert result.error.code == "iteration_limit_reached"


def test_rejected_plan_cancels_before_execution_loop() -> None:
    llm = FakeLLM((LLMResponse(text="1. Inspect\n2. Implement\n3. Test"),))
    approval = RecordingApprovalProvider(approved=False)
    harness = CodingAgentHarness(llm, approval_provider=approval)

    result = harness.run(AgentRunRequest(task="Make a change", plan_mode=True))

    assert result.status is RunStatus.CANCELLED
    assert result.plan == Plan(text="1. Inspect\n2. Implement\n3. Test")
    assert result.metrics.planning_calls == 1
    assert result.metrics.model_iterations == 0
    assert result.error is not None
    assert result.error.code == "approval_rejected"
    assert len(approval.requests) == 1


def test_approved_plan_executes_without_requesting_confirmation_again() -> None:
    llm = FakeLLM(
        (
            LLMResponse(text="1. Inspect files.\n\nConfirm that I should proceed."),
            LLMResponse(text="Repository evidence inspected."),
        )
    )
    approval = RecordingApprovalProvider(approved=True)
    harness = CodingAgentHarness(llm, approval_provider=approval)

    result = harness.run(
        AgentRunRequest(
            task="Analyze the repository",
            plan_mode=True,
            supervision_mode=False,
        )
    )

    assert result.status is RunStatus.COMPLETED
    assert result.final_answer == "Repository evidence inspected."
    assert len(approval.requests) == 1
    assert "do not ask for confirmation" in llm.requests[0].instructions.lower()
    assert "plan has already been approved" in llm.requests[1].instructions.lower()
    execution_input = llm.requests[1].input[-1]
    assert isinstance(execution_input, MessageInput)
    assert "approval has already been granted" in execution_input.content.lower()
    assert "confirmation request inside the plan is obsolete" in execution_input.content


def test_supervision_rejection_does_not_execute_tool() -> None:
    llm = FakeLLM((_tool_response("call-1"), LLMResponse(text="Action was rejected.")))
    approval = RecordingApprovalProvider(approved=False)
    tool = RecordingTool()
    harness = CodingAgentHarness(
        llm,
        tools=(ToolBinding(definition=ECHO_DEFINITION, handler=tool),),
        approval_provider=approval,
    )

    result = harness.run(AgentRunRequest(task="Echo hello", plan_mode=False, supervision_mode=True))

    assert result.status is RunStatus.COMPLETED
    assert result.tool_results[0].status is ToolStatus.REJECTED
    assert not tool.calls
