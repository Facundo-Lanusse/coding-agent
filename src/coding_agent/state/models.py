"""Immutable domain models for one coordinated coding task."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import Field, model_validator

from coding_agent.models import ErrorInfo, FrozenModel, PolicyOutcome, ToolStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class TaskStatus(StrEnum):
    RECEIVED = "received"
    PLANNING = "planning"
    EXPLORING = "exploring"
    RESEARCHING = "researching"
    IMPLEMENTING = "implementing"
    TESTING = "testing"
    REVIEWING = "reviewing"
    WAITING_APPROVAL = "waiting_approval"
    REPLANNING = "replanning"
    BLOCKED = "blocked"
    FAILED = "failed"
    STOPPED_NO_EVIDENCE = "stopped_no_evidence"
    COMPLETED = "completed"


class AgentName(StrEnum):
    MAIN = "main"
    EXPLORER = "explorer"
    RESEARCHER = "researcher"
    IMPLEMENTER = "implementer"
    TESTER = "tester"
    REVIEWER = "reviewer"


class AgentResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    WAITING_APPROVAL = "waiting_approval"
    REJECTED = "rejected"
    NO_EVIDENCE = "no_evidence"


class EvidenceSource(StrEnum):
    REPOSITORY = "repository"
    MEMORY = "memory"
    RAG = "rag"
    WEB = "web"
    TOOL_OUTPUT = "tool_output"
    INFERENCE = "inference"


class FileOperation(StrEnum):
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"


class TaskRequest(FrozenModel):
    task_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    original_request: str = Field(min_length=1)
    workspace: Path
    acceptance_criteria: tuple[str, ...] = ()
    require_plan_approval: bool = False
    max_replans: int = Field(default=1, ge=0, le=20)
    created_at: datetime = Field(default_factory=utc_now)


class Evidence(FrozenModel):
    evidence_id: str = Field(min_length=1)
    source: EvidenceSource
    reference: str = Field(min_length=1)
    content: str = Field(min_length=1)
    locator: str | None = None
    claims: tuple[str, ...] = ()
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    supports: tuple[str, ...] = ()
    observed_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def inference_has_support(self) -> Evidence:
        if self.source is EvidenceSource.INFERENCE and not self.supports:
            raise ValueError("inference evidence must identify supporting evidence")
        return self


class ToolInvocationRecord(FrozenModel):
    call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    actor: AgentName
    arguments: dict[str, object] = Field(default_factory=dict)
    policy_outcome: PolicyOutcome | None = None
    status: ToolStatus
    exit_code: int | None = None
    output_digest: str | None = None
    output_truncated: bool = False
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None


class FileChange(FrozenModel):
    path: Path
    operation: FileOperation
    actor: AgentName
    before_digest: str | None = None
    after_digest: str | None = None
    diff: str | None = None
    authorized: bool = False


class Decision(FrozenModel):
    decision_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    actor: AgentName
    reason: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    made_at: datetime = Field(default_factory=utc_now)


class ApprovalRecord(FrozenModel):
    approval_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    approved: bool | None = None
    reason: str | None = None
    requested_at: datetime = Field(default_factory=utc_now)
    decided_at: datetime | None = None


class PendingApproval(FrozenModel):
    approval_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    description: str = Field(min_length=1)
    resume_status: TaskStatus


class TaskEvent(FrozenModel):
    sequence: int = Field(ge=1)
    revision: int = Field(ge=1)
    event_type: str = Field(min_length=1)
    actor: AgentName
    from_status: TaskStatus
    to_status: TaskStatus
    payload: dict[str, object] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)


class CheckResult(FrozenModel):
    name: str = Field(min_length=1)
    passed: bool
    command: tuple[str, ...] = ()
    exit_code: int | None = None
    output_digest: str | None = None


class AgentResult(FrozenModel):
    agent: AgentName
    status: AgentResultStatus
    summary: str = Field(min_length=1)
    evidence: tuple[Evidence, ...] = ()
    tool_invocations: tuple[ToolInvocationRecord, ...] = ()
    files_read: tuple[Path, ...] = ()
    file_changes: tuple[FileChange, ...] = ()
    commands: tuple[tuple[str, ...], ...] = ()
    approvals: tuple[ApprovalRecord, ...] = ()
    errors: tuple[ErrorInfo, ...] = ()
    observations: tuple[str, ...] = ()
    decisions: tuple[Decision, ...] = ()
    checks: tuple[CheckResult, ...] = ()
    criteria_met: bool | None = None
    pending_approval: PendingApproval | None = None

    @model_validator(mode="after")
    def validate_control_result(self) -> AgentResult:
        if self.status is AgentResultStatus.WAITING_APPROVAL and self.pending_approval is None:
            raise ValueError("waiting results require a pending approval")
        if (
            self.agent is AgentName.TESTER
            and self.status is AgentResultStatus.SUCCEEDED
            and (not self.checks or not all(check.passed for check in self.checks))
        ):
            raise ValueError("a successful tester result requires passing checks")
        if (
            self.agent is AgentName.REVIEWER
            and self.status is AgentResultStatus.SUCCEEDED
            and self.criteria_met is not True
        ):
            raise ValueError("a successful reviewer result requires criteria_met=true")
        return self


class EvidenceGroup(FrozenModel):
    source: EvidenceSource
    items: tuple[Evidence, ...] = ()


class TaskFinalResult(FrozenModel):
    summary: str = Field(min_length=1)
    evidence: tuple[EvidenceGroup, ...]
    reviewer_accepted: bool


class TaskState(FrozenModel):
    request: TaskRequest
    normalized_objective: str = ""
    plan: tuple[str, ...] = ()
    plan_version: int = Field(default=0, ge=0)
    status: TaskStatus = TaskStatus.RECEIVED
    current_phase: TaskStatus = TaskStatus.RECEIVED
    agent_results: tuple[AgentResult, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    sources_consulted: tuple[EvidenceSource, ...] = ()
    files_read: tuple[Path, ...] = ()
    files_modified: tuple[FileChange, ...] = ()
    tool_invocations: tuple[ToolInvocationRecord, ...] = ()
    commands: tuple[tuple[str, ...], ...] = ()
    approvals: tuple[ApprovalRecord, ...] = ()
    errors: tuple[ErrorInfo, ...] = ()
    observations: tuple[str, ...] = ()
    decisions: tuple[Decision, ...] = ()
    iterations: int = Field(default=0, ge=0)
    replan_count: int = Field(default=0, ge=0)
    pending_approval: PendingApproval | None = None
    events: tuple[TaskEvent, ...] = ()
    revision: int = Field(default=0, ge=0)
    final_result: TaskFinalResult | None = None
