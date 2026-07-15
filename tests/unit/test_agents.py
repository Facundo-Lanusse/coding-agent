from collections.abc import Iterable

import pytest

from coding_agent.agents import (
    AgentBackend,
    AgentContext,
    ExplorerAgent,
    ImplementerAgent,
    ResearcherAgent,
    ReviewerAgent,
    ScopedToolbox,
    ToolAccessError,
)
from coding_agent.agents import (
    TesterAgent as CodingTesterAgent,
)
from coding_agent.harness.loop import ToolBinding
from coding_agent.models import FunctionCall, ToolDefinition, ToolResult, ToolStatus
from coding_agent.state import AgentName, AgentResult, AgentResultStatus, CheckResult


class SuccessBackend(AgentBackend):
    def run(
        self,
        *,
        agent: AgentName,
        responsibility: str,
        context: AgentContext,
        tools: ScopedToolbox,
    ) -> AgentResult:
        del responsibility, context, tools
        checks = (
            (CheckResult(name="pytest", passed=True, command=("pytest",)),)
            if agent is AgentName.TESTER
            else ()
        )
        return AgentResult(
            agent=agent,
            status=AgentResultStatus.SUCCEEDED,
            summary=f"{agent.value} complete",
            checks=checks,
            criteria_met=True if agent is AgentName.REVIEWER else None,
        )


class UnauthorizedBackend(AgentBackend):
    def run(
        self,
        *,
        agent: AgentName,
        responsibility: str,
        context: AgentContext,
        tools: ScopedToolbox,
    ) -> AgentResult:
        del agent, responsibility, context
        tools.execute(FunctionCall(call_id="call-1", name="write_file", arguments={}))
        raise AssertionError("unreachable")


def binding(name: str, calls: list[str]) -> ToolBinding:
    def handler(call: FunctionCall) -> ToolResult:
        calls.append(call.name)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status=ToolStatus.EXECUTED,
        )

    return ToolBinding(
        definition=ToolDefinition(name=name, description=f"Fake {name}", parameters={}),
        handler=handler,
    )


def all_bindings(calls: list[str]) -> Iterable[ToolBinding]:
    names = {
        "read_file",
        "write_file",
        "list_files",
        "run_command",
        "search_files",
        "repository_status",
        "web_search",
    }
    return tuple(binding(name, calls) for name in names)


def context() -> AgentContext:
    return AgentContext(
        task_id="task-1",
        original_request="Inspect and change the API",
        normalized_objective="Inspect and change the API",
        plan=("Inspect", "Change", "Test"),
    )


def test_specialists_receive_different_tool_capabilities() -> None:
    calls: list[str] = []
    bindings = all_bindings(calls)
    backend = SuccessBackend()

    agents = (
        ExplorerAgent(backend, tools=bindings),
        ResearcherAgent(backend, tools=bindings),
        ImplementerAgent(backend, tools=bindings),
        CodingTesterAgent(backend, tools=bindings),
        ReviewerAgent(backend, tools=bindings),
    )

    capabilities = {agent.name: agent.tool_names for agent in agents}
    assert "write_file" in capabilities[AgentName.IMPLEMENTER]
    assert "write_file" not in capabilities[AgentName.EXPLORER]
    assert capabilities[AgentName.RESEARCHER] == frozenset({"web_search"})
    assert "run_command" in capabilities[AgentName.TESTER]
    assert "run_command" not in capabilities[AgentName.REVIEWER]


def test_agent_cannot_execute_a_tool_not_assigned_to_it() -> None:
    calls: list[str] = []
    explorer = ExplorerAgent(UnauthorizedBackend(), tools=all_bindings(calls))

    with pytest.raises(ToolAccessError, match="not assigned"):
        explorer.run(context())

    assert calls == []
