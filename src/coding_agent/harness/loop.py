"""Explicit model/tool loop migrated from the legacy notebook."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from coding_agent.approval import ApprovalProvider, DenyAllApprovalProvider
from coding_agent.llm.base import LLMClient, LLMClientError
from coding_agent.models import (
    AgentRunRequest,
    AgentRunResult,
    ApprovalKind,
    ApprovalRequest,
    ErrorInfo,
    FunctionCall,
    FunctionCallOutput,
    LLMInput,
    LLMRequest,
    LLMUsage,
    MessageInput,
    MessageRole,
    Plan,
    RunMetrics,
    RunStatus,
    ToolDefinition,
    ToolResult,
    ToolStatus,
)

SYSTEM_INSTRUCTIONS = """You are a coding agent working inside an authorized workspace.
Inspect relevant evidence before modifying files. Never invent command or test results.
Use only the tools provided. If the input contains an approved plan, execute it now: the
plan has already been approved. Do not ask the user to confirm it again or to paste
repository contents that an available read tool can inspect. Approval for individual
tool calls is handled externally by the harness. Return a concise final answer only
after inspecting enough evidence to answer, or state which required evidence no
available tool can obtain."""

PLAN_INSTRUCTIONS = """Create a short numbered execution plan for the user's task.
Do not call tools and do not claim that any action has already been completed. Return
only the plan. The harness requests approval separately, so do not ask for confirmation,
access, repository listings, or file contents. Assume authorized workspace tools become
available after approval."""


class ToolHandler(Protocol):
    """Minimal Phase 01 execution port; Phase 02 will supply the authorized registry."""

    def __call__(self, call: FunctionCall) -> ToolResult:
        """Execute one call and return a structured result."""


@dataclass(frozen=True, slots=True)
class ToolBinding:
    definition: ToolDefinition
    handler: ToolHandler


class CodingAgentHarness:
    """Provider-neutral, synchronous harness with plan and supervision modes."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        tools: Iterable[ToolBinding] = (),
        approval_provider: ApprovalProvider | None = None,
    ) -> None:
        self._llm = llm
        self._approval_provider = approval_provider or DenyAllApprovalProvider()
        self._tools: dict[str, ToolBinding] = {}
        for binding in tools:
            name = binding.definition.name
            if name in self._tools:
                raise ValueError(f"Duplicate tool binding: {name}")
            self._tools[name] = binding
        self._history: list[MessageInput] = []

    @property
    def history(self) -> tuple[MessageInput, ...]:
        return tuple(self._history)

    def reset_history(self) -> None:
        self._history.clear()

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        plan: Plan | None = None
        planning_calls = 0
        model_iterations = 0
        tool_calls = 0
        usage = LLMUsage()
        tool_results: list[ToolResult] = []

        if request.plan_mode:
            try:
                plan_response = self._llm.respond(
                    LLMRequest(
                        instructions=PLAN_INSTRUCTIONS,
                        input=(MessageInput(role=MessageRole.USER, content=request.task),),
                    )
                )
            except LLMClientError as exc:
                return _failed_run(
                    plan=None,
                    metrics=RunMetrics(planning_calls=1),
                    error=ErrorInfo(code=exc.code, message=str(exc)),
                )

            planning_calls = 1
            usage = _add_usage(usage, plan_response.usage)
            plan_text = plan_response.text.strip()
            if plan_response.tool_calls or not plan_text:
                return _failed_run(
                    plan=None,
                    metrics=RunMetrics(planning_calls=planning_calls, usage=usage),
                    error=ErrorInfo(
                        code="invalid_plan_response",
                        message="Plan mode requires a non-empty text response without tool calls.",
                    ),
                )

            plan = Plan(text=plan_text)
            decision = self._approval_provider.request_approval(
                ApprovalRequest(
                    kind=ApprovalKind.PLAN,
                    action="approve_plan",
                    description=plan.text,
                )
            )
            if not decision.approved:
                return AgentRunResult(
                    status=RunStatus.CANCELLED,
                    plan=plan,
                    metrics=RunMetrics(planning_calls=planning_calls, usage=usage),
                    error=ErrorInfo(
                        code="approval_rejected",
                        message=decision.reason,
                    ),
                )

        task_content = request.task
        if plan is not None:
            task_content = (
                f"User task:\n{request.task}\n\n"
                f"Approved plan (execute now; any confirmation request inside the plan "
                f"is obsolete):\n{plan.text}\n\n"
                "Plan approval has already been granted. Use the available tools and "
                "complete the task without requesting another confirmation."
            )

        run_input: list[LLMInput] = [
            *self._history,
            MessageInput(role=MessageRole.USER, content=task_content),
        ]
        definitions = tuple(binding.definition for binding in self._tools.values())

        for _ in range(request.max_iterations):
            model_iterations += 1
            try:
                response = self._llm.respond(
                    LLMRequest(
                        instructions=SYSTEM_INSTRUCTIONS,
                        input=tuple(run_input),
                        tools=definitions,
                    )
                )
            except LLMClientError as exc:
                return _failed_run(
                    plan=plan,
                    metrics=RunMetrics(
                        planning_calls=planning_calls,
                        model_iterations=model_iterations,
                        tool_calls=tool_calls,
                        usage=usage,
                    ),
                    tool_results=tuple(tool_results),
                    error=ErrorInfo(code=exc.code, message=str(exc)),
                )

            usage = _add_usage(usage, response.usage)
            run_input.extend(response.continuation)

            if not response.tool_calls:
                final_answer = response.text.strip()
                if not final_answer:
                    return _failed_run(
                        plan=plan,
                        metrics=RunMetrics(
                            planning_calls=planning_calls,
                            model_iterations=model_iterations,
                            tool_calls=tool_calls,
                            usage=usage,
                        ),
                        tool_results=tuple(tool_results),
                        error=ErrorInfo(
                            code="empty_model_response",
                            message="The model returned neither text nor tool calls.",
                        ),
                    )

                self._history.extend(
                    (
                        MessageInput(role=MessageRole.USER, content=request.task),
                        MessageInput(role=MessageRole.ASSISTANT, content=final_answer),
                    )
                )
                return AgentRunResult(
                    status=RunStatus.COMPLETED,
                    final_answer=final_answer,
                    plan=plan,
                    metrics=RunMetrics(
                        planning_calls=planning_calls,
                        model_iterations=model_iterations,
                        tool_calls=tool_calls,
                        usage=usage,
                    ),
                    tool_results=tuple(tool_results),
                )

            for call in response.tool_calls:
                tool_calls += 1
                result = self._execute_tool_call(call, supervision_mode=request.supervision_mode)
                tool_results.append(result)
                run_input.append(
                    FunctionCallOutput(
                        call_id=call.call_id,
                        output=result.model_dump_json(),
                    )
                )

        return AgentRunResult(
            status=RunStatus.MAX_ITERATIONS,
            plan=plan,
            metrics=RunMetrics(
                planning_calls=planning_calls,
                model_iterations=model_iterations,
                tool_calls=tool_calls,
                usage=usage,
            ),
            tool_results=tuple(tool_results),
            error=ErrorInfo(
                code="iteration_limit_reached",
                message=f"Maximum model iterations reached: {request.max_iterations}.",
            ),
        )

    def _execute_tool_call(self, call: FunctionCall, *, supervision_mode: bool) -> ToolResult:
        binding = self._tools.get(call.name)
        if binding is None:
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.name,
                status=ToolStatus.FAILED,
                error=ErrorInfo(
                    code="unknown_tool",
                    message=f"Unknown tool requested: {call.name}.",
                ),
            )

        if supervision_mode:
            decision = self._approval_provider.request_approval(
                ApprovalRequest(
                    kind=ApprovalKind.TOOL,
                    action=call.name,
                    description=f"Execute tool {call.name}.",
                    arguments=call.arguments,
                )
            )
            if not decision.approved:
                return ToolResult(
                    call_id=call.call_id,
                    tool_name=call.name,
                    status=ToolStatus.REJECTED,
                    error=ErrorInfo(code="approval_rejected", message=decision.reason),
                )

        try:
            result = binding.handler(call)
        except Exception as exc:
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.name,
                status=ToolStatus.FAILED,
                error=ErrorInfo(
                    code="tool_execution_error",
                    message=f"Tool execution failed ({type(exc).__name__}).",
                ),
            )

        if result.call_id != call.call_id or result.tool_name != call.name:
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.name,
                status=ToolStatus.FAILED,
                error=ErrorInfo(
                    code="tool_result_mismatch",
                    message="Tool result identity does not match the requested call.",
                ),
            )
        return result


def _failed_run(
    *,
    plan: Plan | None,
    metrics: RunMetrics,
    error: ErrorInfo,
    tool_results: tuple[ToolResult, ...] = (),
) -> AgentRunResult:
    return AgentRunResult(
        status=RunStatus.FAILED,
        plan=plan,
        metrics=metrics,
        tool_results=tool_results,
        error=error,
    )


def _add_usage(left: LLMUsage, right: LLMUsage) -> LLMUsage:
    return LLMUsage(
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        total_tokens=left.total_tokens + right.total_tokens,
    )
