"""Real provider-neutral tool loop used by all five OpenAI-backed roles."""

from __future__ import annotations

from pathlib import Path

from coding_agent.agents.base import AgentContext, ScopedToolbox
from coding_agent.agents.openai_support import (
    SUBMIT_TOOL,
    AgentSubmission,
    _digest,
    _string_argument,
    build_agent_result,
    execute_tool,
    file_change,
    invalid_arguments_result,
    invocation,
    role_instructions,
    submission_tool,
    tool_evidence,
)
from coding_agent.agents.openai_support import (
    approvals as result_approvals,
)
from coding_agent.agents.openai_support import (
    check as build_check,
)
from coding_agent.agents.openai_support import (
    command as parse_command,
)
from coding_agent.context import NoProgressDetector, NoProgressReport, NoProgressSignal
from coding_agent.llm.base import LLMClient
from coding_agent.models import (
    ErrorInfo,
    FunctionCallOutput,
    LLMInput,
    LLMRequest,
    MessageInput,
    MessageRole,
    ToolStatus,
)
from coding_agent.observability import Tracer
from coding_agent.state import (
    AgentName,
    AgentResult,
    AgentResultStatus,
    ApprovalRecord,
    CheckResult,
    Evidence,
    FileChange,
    ToolInvocationRecord,
)


class AgentBackendError(Exception):
    code = "agent_backend_error"


class LLMCallBudgetError(AgentBackendError):
    code = "llm_call_budget_exhausted"


class LLMCallBudget:
    """Hard cap shared by the five sequential roles."""

    def __init__(self, maximum: int) -> None:
        if maximum < 5:
            raise ValueError("A five-agent run requires a budget of at least five LLM calls.")
        self.maximum = maximum
        self.used = 0

    def consume(self, agent: AgentName) -> None:
        if self.used >= self.maximum:
            raise LLMCallBudgetError(
                f"LLM call budget exhausted at {self.used}/{self.maximum} before {agent.value}."
            )
        self.used += 1


class OpenAIAgentBackend:
    """Run one explicit Responses-style function loop per specialized role."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        call_budget: LLMCallBudget,
        max_iterations_per_agent: int = 4,
        max_identical_actions: int = 2,
        max_identical_failures: int = 2,
        tracer: Tracer | None = None,
    ) -> None:
        if max_iterations_per_agent < 1:
            raise ValueError("max_iterations_per_agent must be positive.")
        self._llm = llm
        self._budget = call_budget
        self._max_iterations = max_iterations_per_agent
        self._detectors: dict[AgentName, NoProgressDetector] = {
            agent: NoProgressDetector(
                max_identical_actions=max_identical_actions,
                max_identical_errors=max_identical_failures,
                tracer=tracer,
            )
            for agent in AgentName
            if agent is not AgentName.MAIN
        }
        self._signals: list[NoProgressSignal] = []

    @property
    def llm_calls(self) -> int:
        return self._budget.used

    @property
    def no_progress_signals(self) -> tuple[NoProgressSignal, ...]:
        return tuple(self._signals)

    def run(
        self,
        *,
        agent: AgentName,
        responsibility: str,
        context: AgentContext,
        tools: ScopedToolbox,
    ) -> AgentResult:
        detector = self._detectors[agent]
        evidence: list[Evidence] = []
        invocations: list[ToolInvocationRecord] = []
        files_read: list[Path] = []
        file_changes: list[FileChange] = []
        commands: list[tuple[str, ...]] = []
        checks: list[CheckResult] = []
        approvals: list[ApprovalRecord] = []
        errors: list[ErrorInfo] = []
        read_contents: dict[str, str] = {}
        run_input: list[LLMInput] = [
            MessageInput(
                role=MessageRole.USER,
                content=context.model_dump_json(indent=2),
            )
        ]
        submission_definition = submission_tool()
        definitions = (*tools.definitions, submission_definition)

        for iteration in range(1, self._max_iterations + 1):
            try:
                self._budget.consume(agent)
            except LLMCallBudgetError as exc:
                return AgentResult(
                    agent=agent,
                    status=AgentResultStatus.BLOCKED,
                    summary=str(exc),
                    evidence=tuple(evidence),
                    tool_invocations=tuple(invocations),
                    files_read=tuple(dict.fromkeys(files_read)),
                    file_changes=tuple(file_changes),
                    commands=tuple(commands),
                    checks=tuple(checks),
                    approvals=tuple(approvals),
                    errors=(*errors, ErrorInfo(code=exc.code, message=str(exc))),
                )
            available_definitions = definitions
            if agent is AgentName.IMPLEMENTER and iteration > 2:
                available_definitions = tuple(
                    definition
                    for definition in definitions
                    if definition.name in {"write_file", SUBMIT_TOOL}
                )
            response = self._llm.respond(
                LLMRequest(
                    instructions=role_instructions(
                        agent,
                        responsibility,
                        maximum_turns=self._max_iterations,
                    ),
                    input=tuple(run_input),
                    tools=(submission_definition,)
                    if iteration == self._max_iterations
                    else available_definitions,
                )
            )
            run_input.extend(response.continuation)
            if not response.tool_calls:
                run_input.append(
                    MessageInput(
                        role=MessageRole.USER,
                        content=(
                            "Finish this role now by calling submit_agent_result. "
                            "Do not return plain text."
                        ),
                    )
                )
                continue

            submit_calls = tuple(
                call for call in response.tool_calls if call.name == SUBMIT_TOOL
            )
            work_calls = tuple(
                call for call in response.tool_calls if call.name != SUBMIT_TOOL
            )
            if submit_calls and not work_calls:
                if submit_calls[-1].arguments_error is not None:
                    error = ErrorInfo(
                        code="invalid_tool_arguments",
                        message=submit_calls[-1].arguments_error,
                        retryable=True,
                    )
                    errors.append(error)
                    run_input.append(
                        FunctionCallOutput(
                            call_id=submit_calls[-1].call_id,
                            output=invalid_arguments_result(
                                submit_calls[-1], error
                            ).model_dump_json(),
                        )
                    )
                    continue
                try:
                    submission = AgentSubmission.model_validate(submit_calls[-1].arguments)
                except Exception as exc:
                    run_input.append(
                        FunctionCallOutput(
                            call_id=submit_calls[-1].call_id,
                            output=f"Invalid structured result ({type(exc).__name__}); retry.",
                        )
                    )
                    continue
                return build_agent_result(
                    agent=agent,
                    submission=submission,
                    context=context,
                    evidence=tuple(evidence),
                    invocations=tuple(invocations),
                    files_read=tuple(dict.fromkeys(files_read)),
                    file_changes=tuple(file_changes),
                    commands=tuple(commands),
                    checks=tuple(checks),
                    approvals=tuple(approvals),
                    errors=tuple(errors),
                )

            for submit in submit_calls:
                run_input.append(
                    FunctionCallOutput(
                        call_id=submit.call_id,
                        output="Complete outstanding tool calls, then submit alone.",
                    )
                )
            for call in work_calls:
                if call.arguments_error is not None:
                    error = ErrorInfo(
                        code="invalid_tool_arguments",
                        message=call.arguments_error,
                        retryable=True,
                    )
                    result = invalid_arguments_result(call, error)
                    run_input.append(
                        FunctionCallOutput(call_id=call.call_id, output=result.model_dump_json())
                    )
                    invocations.append(invocation(agent, call, result))
                    errors.append(error)
                    continue
                signal = detector.before_tool(call.name, call.arguments)
                if signal is not None:
                    return self._no_progress_result(
                        agent,
                        signal,
                        evidence=evidence,
                        invocations=invocations,
                        files_read=files_read,
                        file_changes=file_changes,
                        commands=commands,
                        checks=checks,
                        approvals=approvals,
                        errors=errors,
                    )
                result = execute_tool(tools, call)
                detector.record_tool(call.name, call.arguments)
                run_input.append(
                    FunctionCallOutput(call_id=call.call_id, output=result.model_dump_json())
                )
                invocations.append(invocation(agent, call, result))
                approvals.extend(result_approvals(result))
                if result.error is not None:
                    errors.append(result.error)
                new_evidence = tool_evidence(agent, call, result)
                evidence.extend(new_evidence)
                change = file_change(agent, call, result, read_contents)
                if change is not None:
                    file_changes.append(change)
                if call.name == "read_file" and result.status is ToolStatus.EXECUTED:
                    path = _string_argument(call.arguments, "path")
                    if path is not None:
                        files_read.append(Path(path))
                        read_contents[path] = result.output
                        reread = detector.record_file_read(
                            path,
                            content_digest=_digest(result.output),
                        )
                        if reread is not None:
                            return self._no_progress_result(
                                agent,
                                reread,
                                evidence=evidence,
                                invocations=invocations,
                                files_read=files_read,
                                file_changes=file_changes,
                                commands=commands,
                                checks=checks,
                                approvals=approvals,
                                errors=errors,
                            )
                command = parse_command(call)
                if command is not None:
                    commands.append(command)
                    if agent is AgentName.TESTER:
                        checks.append(build_check(command, result))
                    if result.error is not None:
                        repeated = detector.record_command_error(
                            command,
                            code=result.error.code,
                            message=result.error.message,
                        )
                        if repeated is not None:
                            return self._no_progress_result(
                                agent,
                                repeated,
                                evidence=evidence,
                                invocations=invocations,
                                files_read=files_read,
                                file_changes=file_changes,
                                commands=commands,
                                checks=checks,
                                approvals=approvals,
                                errors=errors,
                            )
                detector.note_progress(
                    evidence_ids=tuple(item.evidence_id for item in new_evidence),
                    change_ids=((str(change.path),) if change is not None else ()),
                )

            if agent is AgentName.IMPLEMENTER and iteration == 2 and not file_changes:
                run_input.append(
                    MessageInput(
                        role=MessageRole.USER,
                        content=(
                            "Inspection limit reached. Apply the required edits now with "
                            "write_file; do not defer them to Reviewer or CI."
                        ),
                    )
                )

            if iteration == self._max_iterations - 1:
                run_input.append(
                    MessageInput(
                        role=MessageRole.USER,
                        content=(
                            "Only one model turn remains for this role. Do not call another "
                            "work tool; submit the best evidence-backed result now with "
                            "submit_agent_result."
                        ),
                    )
                )

            exhausted = detector.record_iteration(iteration, maximum=self._max_iterations)
            if exhausted is not None:
                return self._no_progress_result(
                    agent,
                    exhausted,
                    evidence=evidence,
                    invocations=invocations,
                    files_read=files_read,
                    file_changes=file_changes,
                    commands=commands,
                    checks=checks,
                    approvals=approvals,
                    errors=errors,
                )

        return AgentResult(
            agent=agent,
            status=AgentResultStatus.FAILED,
            summary=f"{agent.value} exhausted its model-iteration budget.",
            evidence=tuple(evidence),
            tool_invocations=tuple(invocations),
            files_read=tuple(dict.fromkeys(files_read)),
            file_changes=tuple(file_changes),
            commands=tuple(commands),
            checks=tuple(checks),
            approvals=tuple(approvals),
            errors=(*errors, ErrorInfo(code="iteration_limit", message="Role loop exhausted.")),
        )

    def _no_progress_result(
        self,
        agent: AgentName,
        signal: NoProgressSignal,
        *,
        evidence: list[Evidence],
        invocations: list[ToolInvocationRecord],
        files_read: list[Path],
        file_changes: list[FileChange],
        commands: list[tuple[str, ...]],
        checks: list[CheckResult],
        approvals: list[ApprovalRecord],
        errors: list[ErrorInfo],
    ) -> AgentResult:
        self._signals.append(signal)
        report = NoProgressReport.from_signal(signal)
        status = (
            AgentResultStatus.FAILED
            if agent in {AgentName.TESTER, AgentName.REVIEWER}
            else AgentResultStatus.BLOCKED
        )
        return AgentResult(
            agent=agent,
            status=status,
            summary=report.render(),
            evidence=tuple(evidence),
            tool_invocations=tuple(invocations),
            files_read=tuple(dict.fromkeys(files_read)),
            file_changes=tuple(file_changes),
            commands=tuple(commands),
            checks=tuple(checks),
            approvals=tuple(approvals),
            errors=(
                *errors,
                ErrorInfo(code=f"no_progress_{signal.reason.value}", message=signal.explanation),
            ),
            observations=(report.render(),),
            criteria_met=False if agent is AgentName.REVIEWER else None,
        )
