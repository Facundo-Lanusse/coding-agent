from __future__ import annotations

from collections import deque
from pathlib import Path

from coding_agent.agents import AgentContext
from coding_agent.models import ApprovalDecision, ErrorInfo, PolicyOutcome, ToolStatus
from coding_agent.orchestrator import MainAgent
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
    TaskRequest,
    TaskStatus,
    ToolInvocationRecord,
)
from coding_agent.tools.base import ToolRole


class FakeAgent:
    def __init__(self, name: AgentName, results: list[AgentResult], order: list[AgentName]) -> None:
        self.name = name
        self.role = ToolRole(name.value)
        self._results = deque(results)
        self._order = order
        self.contexts: list[AgentContext] = []

    @property
    def tool_names(self) -> frozenset[str]:
        return frozenset()

    def run(self, context: AgentContext) -> AgentResult:
        self._order.append(self.name)
        self.contexts.append(context)
        return self._results.popleft()


def task(*, approval: bool = False, max_replans: int = 1) -> TaskRequest:
    return TaskRequest(
        task_id="task-03",
        project_id="demo-api",
        session_id="session-03",
        original_request="  Add   a health endpoint  ",
        workspace=Path("/workspace"),
        acceptance_criteria=("GET /health returns 200",),
        require_plan_approval=approval,
        max_replans=max_replans,
    )


def success_result(name: AgentName) -> AgentResult:
    if name is AgentName.EXPLORER:
        return AgentResult(
            agent=name,
            status=AgentResultStatus.SUCCEEDED,
            summary="FastAPI app found in app/main.py.",
            evidence=(
                Evidence(
                    evidence_id="repo-1",
                    source=EvidenceSource.REPOSITORY,
                    reference="app/main.py",
                    locator="app/main.py:1",
                    content="FastAPI application entry point.",
                ),
            ),
            files_read=(Path("app/main.py"),),
            observations=("Routes are declared in the application module.",),
        )
    if name is AgentName.RESEARCHER:
        return AgentResult(
            agent=name,
            status=AgentResultStatus.SUCCEEDED,
            summary="FastAPI response evidence retrieved.",
            evidence=(
                Evidence(
                    evidence_id="web-1",
                    source=EvidenceSource.WEB,
                    reference="FastAPI official documentation",
                    content="Path operations may return dictionaries.",
                ),
            ),
        )
    if name is AgentName.IMPLEMENTER:
        return AgentResult(
            agent=name,
            status=AgentResultStatus.SUCCEEDED,
            summary="Health route implemented.",
            evidence=(
                Evidence(
                    evidence_id="inference-1",
                    source=EvidenceSource.INFERENCE,
                    reference="implementation decision",
                    content="A dictionary response meets the criterion.",
                    supports=("repo-1", "web-1"),
                ),
            ),
            file_changes=(
                FileChange(
                    path=Path("app/main.py"),
                    operation=FileOperation.MODIFIED,
                    actor=name,
                    before_digest="before",
                    after_digest="after",
                    authorized=True,
                ),
            ),
            decisions=(
                Decision(
                    decision_id="decision-1",
                    kind="implementation",
                    actor=name,
                    reason="Smallest change satisfying the endpoint criterion.",
                    evidence_ids=("repo-1", "web-1"),
                ),
            ),
        )
    if name is AgentName.TESTER:
        return AgentResult(
            agent=name,
            status=AgentResultStatus.SUCCEEDED,
            summary="Targeted test passed.",
            checks=(
                CheckResult(
                    name="health test",
                    passed=True,
                    command=("pytest", "tests/test_health.py"),
                    exit_code=0,
                ),
            ),
            commands=(("pytest", "tests/test_health.py"),),
            tool_invocations=(
                ToolInvocationRecord(
                    call_id="check-1",
                    tool_name="run_command",
                    actor=name,
                    arguments={"argv": ["pytest", "tests/test_health.py"]},
                    policy_outcome=PolicyOutcome.ALLOWED,
                    status=ToolStatus.EXECUTED,
                    exit_code=0,
                ),
            ),
            approvals=(
                ApprovalRecord(
                    approval_id="existing-approval",
                    action="apply_change",
                    approved=True,
                    reason="Pre-authorized test fixture.",
                ),
            ),
        )
    return AgentResult(
        agent=name,
        status=AgentResultStatus.SUCCEEDED,
        summary="Diff and criteria accepted.",
        criteria_met=True,
    )


def agents(
    overrides: dict[AgentName, list[AgentResult]] | None = None,
) -> tuple[dict[AgentName, FakeAgent], list[AgentName]]:
    order: list[AgentName] = []
    supplied = overrides or {}
    mapping = {
        name: FakeAgent(name, supplied.get(name, [success_result(name)]), order)
        for name in (
            AgentName.EXPLORER,
            AgentName.RESEARCHER,
            AgentName.IMPLEMENTER,
            AgentName.TESTER,
            AgentName.REVIEWER,
        )
    }
    return mapping, order


def test_complete_flow_orders_agents_and_accumulates_shared_state() -> None:
    mapping, order = agents()

    state = MainAgent(mapping).run(task())

    assert state.status is TaskStatus.COMPLETED
    assert order == [
        AgentName.EXPLORER,
        AgentName.RESEARCHER,
        AgentName.IMPLEMENTER,
        AgentName.TESTER,
        AgentName.REVIEWER,
    ]
    assert state.normalized_objective == "Add a health endpoint"
    assert len(state.agent_results) == 5
    assert state.sources_consulted == (
        EvidenceSource.REPOSITORY,
        EvidenceSource.WEB,
        EvidenceSource.INFERENCE,
    )
    assert state.files_read == (Path("app/main.py"),)
    assert state.files_modified[0].authorized
    assert state.commands == (("pytest", "tests/test_health.py"),)
    assert state.approvals[0].approved
    assert state.observations
    assert state.decisions
    assert state.iterations == 5
    assert state.final_result is not None
    assert [group.source for group in state.final_result.evidence] == list(EvidenceSource)
    assert state.final_result.reviewer_accepted
    assert [event.to_status for event in state.events] == [
        TaskStatus.PLANNING,
        TaskStatus.EXPLORING,
        TaskStatus.RESEARCHING,
        TaskStatus.IMPLEMENTING,
        TaskStatus.TESTING,
        TaskStatus.REVIEWING,
        TaskStatus.COMPLETED,
    ]
    assert mapping[AgentName.EXPLORER].contexts[0].evidence == ()
    assert [item.agent for item in mapping[AgentName.TESTER].contexts[0].prior_results] == [
        AgentName.IMPLEMENTER
    ]


def test_failed_tester_replans_and_retries_within_limit() -> None:
    failed = AgentResult(
        agent=AgentName.TESTER,
        status=AgentResultStatus.FAILED,
        summary="Health test failed with status 404.",
        checks=(CheckResult(name="health test", passed=False, exit_code=1),),
        errors=(ErrorInfo(code="test_failed", message="Expected 200, got 404."),),
    )
    overrides = {
        AgentName.IMPLEMENTER: [success_result(AgentName.IMPLEMENTER)] * 2,
        AgentName.TESTER: [failed, success_result(AgentName.TESTER)],
    }
    mapping, order = agents(overrides)

    state = MainAgent(mapping).run(task(max_replans=1))

    assert state.status is TaskStatus.COMPLETED
    assert state.replan_count == 1
    assert order.count(AgentName.IMPLEMENTER) == 2
    assert order.count(AgentName.TESTER) == 2
    assert TaskStatus.REPLANNING in [event.to_status for event in state.events]


def test_reviewer_rejection_never_completes_noncompliant_change() -> None:
    rejected = AgentResult(
        agent=AgentName.REVIEWER,
        status=AgentResultStatus.REJECTED,
        summary="The diff does not implement the requested endpoint.",
        criteria_met=False,
    )
    mapping, _ = agents({AgentName.REVIEWER: [rejected]})

    state = MainAgent(mapping).run(task(max_replans=0))

    assert state.status is TaskStatus.BLOCKED
    assert state.final_result is None
    assert state.events[-1].event_type == "replan_budget_exhausted"


def test_missing_evidence_stops_with_explicit_blocked_state() -> None:
    no_evidence = AgentResult(
        agent=AgentName.RESEARCHER,
        status=AgentResultStatus.NO_EVIDENCE,
        summary="No trustworthy source explains the installed FastAPI version.",
        observations=("Need dependency metadata or permission to inspect it.",),
    )
    mapping, order = agents({AgentName.RESEARCHER: [no_evidence]})

    state = MainAgent(mapping).run(task())

    assert state.status is TaskStatus.STOPPED_NO_EVIDENCE
    assert order == [AgentName.EXPLORER, AgentName.RESEARCHER]
    assert state.events[-1].payload["missing"] == no_evidence.summary


def test_pending_approval_pauses_then_resumes_without_duplicate_effects() -> None:
    mapping, order = agents()
    orchestrator = MainAgent(mapping)

    paused = orchestrator.run(task(approval=True))

    assert paused.status is TaskStatus.WAITING_APPROVAL
    assert paused.pending_approval is not None
    assert order == []

    completed = orchestrator.resume(
        paused,
        ApprovalDecision(approved=True, reason="Plan reviewed and accepted."),
    )

    assert completed.status is TaskStatus.COMPLETED
    assert len(order) == 5
    assert completed.approvals[0].approved is True
    assert completed.iterations == 5
    assert [event.event_type for event in completed.events].count("approval_granted") == 1
