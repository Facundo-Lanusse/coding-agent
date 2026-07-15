"""Agent contracts, context slices, and capability-scoped tool access."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from pydantic import Field

from coding_agent.harness.loop import ToolBinding
from coding_agent.models import ErrorInfo, FrozenModel, FunctionCall, ToolResult
from coding_agent.state import (
    AgentName,
    AgentResult,
    CheckResult,
    Evidence,
    FileChange,
    TaskRequest,
)
from coding_agent.tools.base import ToolRole


class AgentContractError(Exception):
    code = "agent_contract_error"


class ToolAccessError(Exception):
    code = "tool_not_assigned"


class PriorAgentSummary(FrozenModel):
    agent: AgentName
    summary: str = Field(min_length=1)


class AgentContext(FrozenModel):
    """Purpose-built slice; never exposes the mutable/shared TaskState object."""

    task_id: str = Field(min_length=1)
    original_request: str = Field(min_length=1)
    normalized_objective: str = Field(min_length=1)
    plan: tuple[str, ...]
    acceptance_criteria: tuple[str, ...] = ()
    prior_results: tuple[PriorAgentSummary, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    relevant_files: tuple[str, ...] = ()
    file_changes: tuple[FileChange, ...] = ()
    checks: tuple[CheckResult, ...] = ()
    observations: tuple[str, ...] = ()
    errors: tuple[ErrorInfo, ...] = ()


class ScopedToolbox:
    """Closed capability set supplied to one agent for one execution."""

    def __init__(self, bindings: Iterable[ToolBinding], *, allowed_names: frozenset[str]) -> None:
        self._bindings: dict[str, ToolBinding] = {}
        for binding in bindings:
            name = binding.definition.name
            if name in allowed_names:
                self._bindings[name] = binding

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._bindings)

    @property
    def definitions(self) -> tuple[object, ...]:
        return tuple(binding.definition for binding in self._bindings.values())

    def execute(self, call: FunctionCall) -> ToolResult:
        binding = self._bindings.get(call.name)
        if binding is None:
            raise ToolAccessError(f"Tool {call.name!r} is not assigned to this agent.")
        return binding.handler(call)


class AgentBackend(Protocol):
    """Phase 03 execution port; tests inject deterministic implementations."""

    def run(
        self,
        *,
        agent: AgentName,
        responsibility: str,
        context: AgentContext,
        tools: ScopedToolbox,
    ) -> AgentResult:
        """Produce one structured role result without mutating shared state."""


class Agent(Protocol):
    name: AgentName
    role: ToolRole

    @property
    def tool_names(self) -> frozenset[str]: ...

    def run(self, context: AgentContext) -> AgentResult: ...


class BaseAgent:
    """Common enforcement around role-specific agent implementations."""

    name: AgentName
    role: ToolRole
    responsibility: str
    allowed_tool_names: frozenset[str]

    def __init__(self, backend: AgentBackend, *, tools: Iterable[ToolBinding] = ()) -> None:
        self._backend = backend
        self._tools = ScopedToolbox(tools, allowed_names=self.allowed_tool_names)

    @property
    def tool_names(self) -> frozenset[str]:
        return self._tools.names

    def run(self, context: AgentContext) -> AgentResult:
        result = self._backend.run(
            agent=self.name,
            responsibility=self.responsibility,
            context=context,
            tools=self._tools,
        )
        if result.agent is not self.name:
            raise AgentContractError(
                f"{self.name.value} backend returned a result for {result.agent.value}."
            )
        self.validate_result(result)
        return result

    def validate_result(self, result: AgentResult) -> None:
        """Allow concrete agents to enforce role-specific result contracts."""


def request_context(request: TaskRequest, objective: str, plan: tuple[str, ...]) -> AgentContext:
    return AgentContext(
        task_id=request.task_id,
        original_request=request.original_request,
        normalized_objective=objective,
        plan=plan,
        acceptance_criteria=request.acceptance_criteria,
    )
