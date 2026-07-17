from __future__ import annotations

from collections import deque

from coding_agent.agents import AgentContext, LLMCallBudget, OpenAIAgentBackend, ScopedToolbox
from coding_agent.harness import ToolBinding
from coding_agent.models import (
    FunctionCall,
    FunctionCallOutput,
    LLMRequest,
    LLMResponse,
    ToolDefinition,
    ToolResult,
    ToolStatus,
)
from coding_agent.state import AgentName, AgentResultStatus, EvidenceSource


class SequenceLLM:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = deque(responses)
        self.requests: list[LLMRequest] = []

    def respond(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return self.responses.popleft()


def _context() -> AgentContext:
    return AgentContext(
        task_id="real-backend-test",
        original_request="Inspect the FastAPI app",
        normalized_objective="Inspect the FastAPI app",
        plan=("Inspect",),
    )


def _read_binding() -> ToolBinding:
    return ToolBinding(
        definition=ToolDefinition(
            name="read_file",
            description="Read one file.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        ),
        handler=lambda call: ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status=ToolStatus.EXECUTED,
            output="from fastapi import FastAPI\napp = FastAPI()\n",
        ),
    )


def _submit_call(*, criteria_met: bool | None = None) -> FunctionCall:
    return FunctionCall(
        call_id="submit-1",
        name="submit_agent_result",
        arguments={
            "status": "succeeded",
            "summary": "Repository evidence inspected.",
            "observations": ["FastAPI entry point found."],
            "decision_reason": "Use the inspected entry point as evidence.",
            "criteria_met": criteria_met,
        },
    )


def test_openai_backend_executes_tools_and_returns_structured_evidence() -> None:
    llm = SequenceLLM(
        [
            LLMResponse(
                tool_calls=(
                    FunctionCall(
                        call_id="read-1",
                        name="read_file",
                        arguments={"path": "app/main.py"},
                    ),
                )
            ),
            LLMResponse(tool_calls=(_submit_call(),)),
        ]
    )
    backend = OpenAIAgentBackend(llm, call_budget=LLMCallBudget(5))
    tools = ScopedToolbox((_read_binding(),), allowed_names=frozenset({"read_file"}))

    result = backend.run(
        agent=AgentName.EXPLORER,
        responsibility="Inspect the repository.",
        context=_context(),
        tools=tools,
    )

    assert result.status is AgentResultStatus.SUCCEEDED
    assert result.files_read[0].as_posix() == "app/main.py"
    assert result.evidence[0].source is EvidenceSource.REPOSITORY
    assert result.tool_invocations[0].tool_name == "read_file"
    assert result.decisions[0].evidence_ids == (result.evidence[0].evidence_id,)
    assert backend.llm_calls == 2
    assert "submit_agent_result" in {
        tool.name for tool in llm.requests[0].tools
    }


def test_successful_tester_submission_without_real_check_is_rejected() -> None:
    llm = SequenceLLM([LLMResponse(tool_calls=(_submit_call(),))])
    backend = OpenAIAgentBackend(llm, call_budget=LLMCallBudget(5))

    result = backend.run(
        agent=AgentName.TESTER,
        responsibility="Run checks.",
        context=_context(),
        tools=ScopedToolbox((), allowed_names=frozenset()),
    )

    assert result.status is AgentResultStatus.FAILED
    assert result.checks == ()


def test_shared_llm_budget_stops_before_unbounded_provider_calls() -> None:
    llm = SequenceLLM([LLMResponse(text="plain text") for _ in range(5)])
    budget = LLMCallBudget(5)
    backend = OpenAIAgentBackend(
        llm,
        call_budget=budget,
        max_iterations_per_agent=6,
    )

    result = backend.run(
        agent=AgentName.EXPLORER,
        responsibility="Inspect.",
        context=_context(),
        tools=ScopedToolbox((), allowed_names=frozenset()),
    )

    assert result.status is AgentResultStatus.BLOCKED
    assert backend.llm_calls == 5
    assert result.errors[-1].code == "llm_call_budget_exhausted"


def test_backend_warns_to_reserve_last_turn_for_structured_submission() -> None:
    llm = SequenceLLM(
        [
            LLMResponse(
                tool_calls=(
                    FunctionCall(
                        call_id="read-1",
                        name="read_file",
                        arguments={"path": "app/main.py"},
                    ),
                )
            ),
            LLMResponse(tool_calls=(_submit_call(),)),
        ]
    )
    backend = OpenAIAgentBackend(
        llm,
        call_budget=LLMCallBudget(5),
        max_iterations_per_agent=2,
    )

    result = backend.run(
        agent=AgentName.EXPLORER,
        responsibility="Inspect.",
        context=_context(),
        tools=ScopedToolbox((_read_binding(),), allowed_names=frozenset({"read_file"})),
    )

    assert result.status is AgentResultStatus.SUCCEEDED
    assert "Only one model turn remains" in str(llm.requests[1].input[-1])
    assert "at most 2 model turns" in llm.requests[0].instructions
    assert {tool.name for tool in llm.requests[0].tools} == {
        "read_file",
        "submit_agent_result",
    }
    assert tuple(tool.name for tool in llm.requests[1].tools) == (
        "submit_agent_result",
    )


def test_backend_returns_malformed_call_error_to_model_without_executing_tool() -> None:
    executions: list[FunctionCall] = []

    def forbidden_handler(call: FunctionCall) -> ToolResult:
        executions.append(call)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status=ToolStatus.EXECUTED,
            output="must not execute",
        )

    binding = ToolBinding(
        definition=_read_binding().definition,
        handler=forbidden_handler,
    )
    llm = SequenceLLM(
        [
            LLMResponse(
                tool_calls=(
                    FunctionCall(
                        call_id="malformed-1",
                        name="read_file",
                        arguments={},
                        arguments_error="OpenAI function call arguments are not valid JSON.",
                    ),
                )
            ),
            LLMResponse(tool_calls=(_submit_call(),)),
        ]
    )
    backend = OpenAIAgentBackend(llm, call_budget=LLMCallBudget(5))

    result = backend.run(
        agent=AgentName.EXPLORER,
        responsibility="Inspect.",
        context=_context(),
        tools=ScopedToolbox((binding,), allowed_names=frozenset({"read_file"})),
    )

    assert result.status is AgentResultStatus.SUCCEEDED
    assert executions == []
    assert result.errors[-1].code == "invalid_tool_arguments"
    assert result.tool_invocations[-1].status is ToolStatus.FAILED
    recovery = llm.requests[1].input[-1]
    assert isinstance(recovery, FunctionCallOutput)
    assert recovery.call_id == "malformed-1"
    assert "invalid_tool_arguments" in recovery.output
    assert "at most four work-tool calls" in llm.requests[0].instructions


def test_researcher_contract_does_not_require_downstream_tests() -> None:
    llm = SequenceLLM([LLMResponse(tool_calls=(_submit_call(),))])
    backend = OpenAIAgentBackend(llm, call_budget=LLMCallBudget(5))

    backend.run(
        agent=AgentName.RESEARCHER,
        responsibility="Retrieve technical evidence.",
        context=_context(),
        tools=ScopedToolbox((), allowed_names=frozenset()),
    )

    instructions = llm.requests[0].instructions
    assert "Current repository evidence overrides historical memory" in instructions
    assert "hand that evidence to Implementer, not Reviewer or CI" in instructions
    assert "do not block because implementation or tests are still pending" in instructions


def test_implementer_contract_owns_edits_and_preserves_submission_turn() -> None:
    llm = SequenceLLM([LLMResponse(tool_calls=(_submit_call(),))])
    backend = OpenAIAgentBackend(
        llm,
        call_budget=LLMCallBudget(5),
        max_iterations_per_agent=4,
    )

    backend.run(
        agent=AgentName.IMPLEMENTER,
        responsibility="Implement the requested endpoint.",
        context=_context(),
        tools=ScopedToolbox((), allowed_names=frozenset()),
    )

    instructions = llm.requests[0].instructions
    assert "This role owns repository edits" in instructions
    assert "use no more than two turns for inspection" in instructions
    assert "at most six short observations" in instructions


def test_tester_contract_requires_direct_argv_without_shell_wrapper() -> None:
    llm = SequenceLLM([LLMResponse(tool_calls=(_submit_call(criteria_met=True),))])
    backend = OpenAIAgentBackend(llm, call_budget=LLMCallBudget(5))

    backend.run(
        agent=AgentName.TESTER,
        responsibility="Run the focused test suite.",
        context=_context(),
        tools=ScopedToolbox((), allowed_names=frozenset()),
    )

    instructions = llm.requests[0].instructions
    assert "['pytest', '-q']" in instructions
    assert "Never use /usr/bin/env, bash, sh, -c or -lc wrappers" in instructions
