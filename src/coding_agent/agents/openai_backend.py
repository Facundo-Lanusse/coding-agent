"""Real provider-neutral tool loop used by all five OpenAI-backed roles."""

from __future__ import annotations

import difflib
import hashlib
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from coding_agent.agents.base import AgentContext, ScopedToolbox, ToolAccessError
from coding_agent.context import NoProgressDetector, NoProgressReport, NoProgressSignal
from coding_agent.llm.base import LLMClient
from coding_agent.models import (
    ErrorInfo,
    FunctionCall,
    FunctionCallOutput,
    LLMInput,
    LLMRequest,
    MessageInput,
    MessageRole,
    PolicyOutcome,
    ToolDefinition,
    ToolResult,
    ToolStatus,
)
from coding_agent.observability import Tracer
from coding_agent.state import (
    AgentName,
    AgentResult,
    AgentResultStatus,
    ApprovalRecord,
    CheckResult,
    Decision,
    Evidence,
    EvidenceSource,
    FileChange,
    FileOperation,
    ToolInvocationRecord,
)
from coding_agent.state.models import utc_now

_SUBMIT_TOOL = "submit_agent_result"
_MAX_EVIDENCE_CHARS = 4_000


class AgentBackendError(Exception):
    code = "agent_backend_error"


class LLMCallBudgetError(AgentBackendError):
    code = "llm_call_budget_exhausted"


class SubmissionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    NO_EVIDENCE = "no_evidence"
    REJECTED = "rejected"


class AgentSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: SubmissionStatus
    summary: str = Field(min_length=1, max_length=4_000)
    observations: tuple[str, ...] = ()
    decision_reason: str | None = None
    criteria_met: bool | None = None


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
        submission_definition = _submission_tool()
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
            response = self._llm.respond(
                LLMRequest(
                    instructions=_instructions(
                        agent,
                        responsibility,
                        maximum_turns=self._max_iterations,
                    ),
                    input=tuple(run_input),
                    tools=(submission_definition,)
                    if iteration == self._max_iterations
                    else definitions,
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
                call for call in response.tool_calls if call.name == _SUBMIT_TOOL
            )
            work_calls = tuple(
                call for call in response.tool_calls if call.name != _SUBMIT_TOOL
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
                            output=_invalid_arguments_result(
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
                return _build_result(
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
                    result = _invalid_arguments_result(call, error)
                    run_input.append(
                        FunctionCallOutput(call_id=call.call_id, output=result.model_dump_json())
                    )
                    invocations.append(_invocation(agent, call, result))
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
                result = _execute(tools, call)
                detector.record_tool(call.name, call.arguments)
                run_input.append(
                    FunctionCallOutput(call_id=call.call_id, output=result.model_dump_json())
                )
                invocations.append(_invocation(agent, call, result))
                approvals.extend(_approvals(result))
                if result.error is not None:
                    errors.append(result.error)
                new_evidence = _tool_evidence(agent, call, result)
                evidence.extend(new_evidence)
                change = _file_change(agent, call, result, read_contents)
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
                command = _command(call)
                if command is not None:
                    commands.append(command)
                    if agent is AgentName.TESTER:
                        checks.append(_check(command, result))
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


def _submission_tool() -> ToolDefinition:
    return ToolDefinition(
        name=_SUBMIT_TOOL,
        description="Submit the structured final result for the current specialist role.",
        parameters={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": [item.value for item in SubmissionStatus],
                },
                "summary": {"type": "string"},
                "observations": {"type": "array", "items": {"type": "string"}},
                "decision_reason": {"type": ["string", "null"]},
                "criteria_met": {"type": ["boolean", "null"]},
            },
            "required": [
                "status",
                "summary",
                "observations",
                "decision_reason",
                "criteria_met",
            ],
            "additionalProperties": False,
        },
        strict=True,
    )


def _instructions(
    agent: AgentName,
    responsibility: str,
    *,
    maximum_turns: int,
) -> str:
    role_rules: Mapping[AgentName, str] = {
        AgentName.EXPLORER: (
            "List only focused project paths, then read independent relevant files in parallel. "
            "Use at most four work-tool calls in one response. Ignore virtual environments, "
            "caches and generated metadata. Base every architecture statement on tool output."
        ),
        AgentName.RESEARCHER: (
            "Use the RAG/web evidence already supplied in context. Web is only a fallback tool. "
            "If that evidence is sufficient, submit immediately without another search. Never "
            "relabel an inference as a source. Current repository evidence overrides historical "
            "memory when they conflict. Your role succeeds when evidence is sufficient to guide "
            "implementation; do not block because implementation or tests are still pending in "
            "downstream roles."
        ),
        AgentName.IMPLEMENTER: (
            "Apply only the requested minimal change. Read a file before replacing it. "
            "Batch independent reads or writes in parallel. For analysis-only tasks, do not write."
        ),
        AgentName.TESTER: (
            "Run one focused allowlisted check, then submit. For pytest call run_command "
            "with a direct argv such as ['pytest', '-q']. Never use /usr/bin/env, bash, "
            "sh, -c or -lc wrappers: the command tool already executes argv directly in "
            "the fixed workspace. Never claim success unless run_command succeeded."
        ),
        AgentName.REVIEWER: (
            "Use the diff and checks already present in context; inspect at most once if needed, "
            "then submit. Set criteria_met true only when every acceptance criterion is supported "
            "by evidence and passing checks."
        ),
        AgentName.MAIN: "Coordinate only.",
    }
    return (
        f"You are the {agent.value} specialist in an explicit five-agent coding workflow. "
        f"Responsibility: {responsibility}\n{role_rules[agent]}\n"
        f"You have at most {maximum_turns} model turns, including the final structured submission. "
        "Reserve the final turn for submit_agent_result. "
        "Use only the provided tools. Tool policy and approvals are enforced externally. "
        "Do not ask the user to paste files that tools can read. Keep actions minimal. "
        "When finished, call submit_agent_result exactly once and alone; do not return plain text."
    )


def _execute(tools: ScopedToolbox, call: FunctionCall) -> ToolResult:
    try:
        return tools.execute(call)
    except ToolAccessError as exc:
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status=ToolStatus.FAILED,
            error=ErrorInfo(code=exc.code, message=str(exc)),
        )


def _invalid_arguments_result(call: FunctionCall, error: ErrorInfo) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        tool_name=call.name,
        status=ToolStatus.FAILED,
        error=error,
    )


def _build_result(
    *,
    agent: AgentName,
    submission: AgentSubmission,
    context: AgentContext,
    evidence: tuple[Evidence, ...],
    invocations: tuple[ToolInvocationRecord, ...],
    files_read: tuple[Path, ...],
    file_changes: tuple[FileChange, ...],
    commands: tuple[tuple[str, ...], ...],
    checks: tuple[CheckResult, ...],
    approvals: tuple[ApprovalRecord, ...],
    errors: tuple[ErrorInfo, ...],
) -> AgentResult:
    status = AgentResultStatus(submission.status.value)
    all_evidence = _unique_evidence((*context.evidence, *evidence))
    if agent is AgentName.RESEARCHER and status is AgentResultStatus.SUCCEEDED and not all_evidence:
        status = AgentResultStatus.NO_EVIDENCE
    if (
        agent is AgentName.TESTER
        and status is AgentResultStatus.SUCCEEDED
        and (not checks or not all(check.passed for check in checks))
    ):
        status = AgentResultStatus.FAILED
    criteria_met = submission.criteria_met if agent is AgentName.REVIEWER else None
    if (
        agent is AgentName.REVIEWER
        and status is AgentResultStatus.SUCCEEDED
        and criteria_met is not True
    ):
        status = AgentResultStatus.REJECTED
    decisions: tuple[Decision, ...] = ()
    if submission.decision_reason:
        decisions = (
            Decision(
                decision_id=f"{context.task_id}:{agent.value}:{_digest(submission.decision_reason)[:12]}",
                kind=f"{agent.value}_decision",
                actor=agent,
                reason=submission.decision_reason,
                evidence_ids=tuple(item.evidence_id for item in all_evidence),
            ),
        )
    return AgentResult(
        agent=agent,
        status=status,
        summary=submission.summary,
        evidence=all_evidence,
        tool_invocations=invocations,
        files_read=files_read,
        file_changes=file_changes,
        commands=commands,
        checks=checks,
        approvals=approvals,
        errors=errors,
        observations=submission.observations,
        decisions=decisions,
        criteria_met=criteria_met,
    )


def _tool_evidence(
    agent: AgentName,
    call: FunctionCall,
    result: ToolResult,
) -> tuple[Evidence, ...]:
    if result.status is not ToolStatus.EXECUTED:
        return ()
    source = (
        EvidenceSource.REPOSITORY
        if call.name in {"read_file", "list_files", "search_files", "repository_status"}
        else EvidenceSource.WEB
        if call.name == "web_search"
        else EvidenceSource.TOOL_OUTPUT
    )
    reference = (
        _string_argument(call.arguments, "path")
        or _string_argument(call.arguments, "query")
        or call.name
    )
    content = result.output.strip() or f"{call.name} executed successfully."
    identifier = _digest(
        f"{agent.value}:{call.name}:{reference}:{_digest(content)}"
    )
    return (
        Evidence(
            evidence_id=f"tool-{identifier}",
            source=source,
            reference=reference,
            content=content[:_MAX_EVIDENCE_CHARS],
            confidence=1.0,
        ),
    )


def _invocation(agent: AgentName, call: FunctionCall, result: ToolResult) -> ToolInvocationRecord:
    return ToolInvocationRecord(
        call_id=call.call_id,
        tool_name=call.name,
        actor=agent,
        arguments=result.policy.arguments if result.policy is not None else {},
        policy_outcome=result.policy.outcome if result.policy is not None else None,
        status=result.status,
        exit_code=_exit_code(result),
        output_digest=_digest(result.output),
        output_truncated=bool(result.metadata.get("truncated", False)),
        ended_at=utc_now(),
    )


def _approvals(result: ToolResult) -> tuple[ApprovalRecord, ...]:
    policy = result.policy
    if policy is None or policy.outcome is not PolicyOutcome.REQUIRES_APPROVAL:
        return ()
    return (
        ApprovalRecord(
            approval_id=policy.fingerprint,
            action=result.tool_name,
            approved=policy.approval_granted,
            reason=policy.reason,
            decided_at=utc_now() if policy.approval_granted is not None else None,
        ),
    )


def _file_change(
    agent: AgentName,
    call: FunctionCall,
    result: ToolResult,
    read_contents: Mapping[str, str],
) -> FileChange | None:
    if call.name != "write_file" or result.status is not ToolStatus.EXECUTED:
        return None
    path = _string_argument(call.arguments, "path")
    content = _string_argument(call.arguments, "content")
    if path is None or content is None:
        return None
    before = read_contents.get(path)
    diff = None
    if before is not None:
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
    return FileChange(
        path=Path(path),
        operation=FileOperation.MODIFIED if before is not None else FileOperation.CREATED,
        actor=agent,
        before_digest=_digest(before) if before is not None else None,
        after_digest=_digest(content),
        diff=diff,
        authorized=result.policy is not None
        and result.policy.outcome in {PolicyOutcome.ALLOWED, PolicyOutcome.REQUIRES_APPROVAL},
    )


def _command(call: FunctionCall) -> tuple[str, ...] | None:
    if call.name != "run_command":
        return None
    value = call.arguments.get("argv")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return tuple(value)


def _check(command: tuple[str, ...], result: ToolResult) -> CheckResult:
    exit_code = _exit_code(result)
    return CheckResult(
        name=" ".join(command[:3]),
        passed=result.status is ToolStatus.EXECUTED and exit_code in {None, 0},
        command=command,
        exit_code=exit_code,
        output_digest=_digest(result.output),
    )


def _exit_code(result: ToolResult) -> int | None:
    value = result.metadata.get("exit_code")
    return value if isinstance(value, int) else None


def _string_argument(arguments: Mapping[str, object], name: str) -> str | None:
    value = arguments.get(name)
    return value if isinstance(value, str) and value else None


def _unique_evidence(evidence: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
    return tuple({item.evidence_id: item for item in evidence}.values())


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
