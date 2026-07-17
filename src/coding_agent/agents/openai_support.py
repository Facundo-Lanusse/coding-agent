"""Structured submission, evidence, and tool-result mapping for OpenAI roles."""

from __future__ import annotations

import difflib
import hashlib
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from coding_agent.agents.base import AgentContext, ScopedToolbox, ToolAccessError
from coding_agent.models import (
    ErrorInfo,
    FunctionCall,
    PolicyOutcome,
    ToolDefinition,
    ToolResult,
    ToolStatus,
)
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

SUBMIT_TOOL = "submit_agent_result"
_MAX_EVIDENCE_CHARS = 4_000


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


def submission_tool() -> ToolDefinition:
    return ToolDefinition(
        name=SUBMIT_TOOL,
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


def role_instructions(
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


def execute_tool(tools: ScopedToolbox, call: FunctionCall) -> ToolResult:
    try:
        return tools.execute(call)
    except ToolAccessError as exc:
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status=ToolStatus.FAILED,
            error=ErrorInfo(code=exc.code, message=str(exc)),
        )


def invalid_arguments_result(call: FunctionCall, error: ErrorInfo) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        tool_name=call.name,
        status=ToolStatus.FAILED,
        error=error,
    )


def build_agent_result(
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
                decision_id=(
                    f"{context.task_id}:{agent.value}:"
                    f"{_digest(submission.decision_reason)[:12]}"
                ),
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


def tool_evidence(
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
    identifier = _digest(f"{agent.value}:{call.name}:{reference}:{_digest(content)}")
    return (
        Evidence(
            evidence_id=f"tool-{identifier}",
            source=source,
            reference=reference,
            content=content[:_MAX_EVIDENCE_CHARS],
            confidence=1.0,
        ),
    )


def invocation(agent: AgentName, call: FunctionCall, result: ToolResult) -> ToolInvocationRecord:
    return ToolInvocationRecord(
        call_id=call.call_id,
        tool_name=call.name,
        actor=agent,
        arguments=result.policy.arguments if result.policy is not None else {},
        policy_outcome=result.policy.outcome if result.policy is not None else None,
        status=result.status,
        exit_code=exit_code(result),
        output_digest=_digest(result.output),
        output_truncated=bool(result.metadata.get("truncated", False)),
        ended_at=utc_now(),
    )


def approvals(result: ToolResult) -> tuple[ApprovalRecord, ...]:
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


def file_change(
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


def command(call: FunctionCall) -> tuple[str, ...] | None:
    if call.name != "run_command":
        return None
    value = call.arguments.get("argv")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return tuple(value)


def check(command_value: tuple[str, ...], result: ToolResult) -> CheckResult:
    code = exit_code(result)
    return CheckResult(
        name=" ".join(command_value[:3]),
        passed=result.status is ToolStatus.EXECUTED and code in {None, 0},
        command=command_value,
        exit_code=code,
        output_digest=_digest(result.output),
    )


def exit_code(result: ToolResult) -> int | None:
    value = result.metadata.get("exit_code")
    return value if isinstance(value, int) else None


def _string_argument(arguments: Mapping[str, object], name: str) -> str | None:
    value = arguments.get(name)
    return value if isinstance(value, str) and value else None


def _unique_evidence(evidence: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
    return tuple({item.evidence_id: item for item in evidence}.values())


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
