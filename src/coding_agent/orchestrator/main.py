"""Explicit coordination of the five specialized agents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from coding_agent.agents import Agent
from coding_agent.context import ContextManager
from coding_agent.models import ApprovalDecision, ErrorInfo
from coding_agent.observability import NoOpTracer, ObservationKind, Tracer
from coding_agent.state import (
    AgentName,
    AgentResult,
    AgentResultStatus,
    ApprovalRecord,
    Decision,
    Evidence,
    PendingApproval,
    TaskRequest,
    TaskState,
    TaskStateMachine,
    TaskStatus,
)
from coding_agent.state.models import utc_now

from .context import build_agent_context, build_final_result


class OrchestrationError(Exception):
    code = "orchestration_error"


class Planner(Protocol):
    def create_plan(self, request: TaskRequest, normalized_objective: str) -> tuple[str, ...]:
        """Return a non-empty ordered plan without executing effects."""

    def replan(self, state: TaskState, failed_result: AgentResult) -> tuple[str, ...]:
        """Return a replacement plan after a concrete failed validation."""


class InitialEvidenceProvider(Protocol):
    def load(self, request: TaskRequest) -> tuple[Evidence, ...]:
        """Load verified project evidence before coordination starts."""


class DefaultPlanner:
    """Provider-free baseline planner suitable for deterministic composition."""

    def create_plan(self, request: TaskRequest, normalized_objective: str) -> tuple[str, ...]:
        del request, normalized_objective
        return (
            "Explore the repository and collect attributable evidence.",
            "Research missing technical context.",
            "Apply only authorized changes.",
            "Run concrete checks and review the resulting change.",
        )

    def replan(self, state: TaskState, failed_result: AgentResult) -> tuple[str, ...]:
        return (
            *state.plan,
            f"Address {failed_result.agent.value} feedback: {failed_result.summary}",
        )


_PHASE_AGENT: Mapping[TaskStatus, AgentName] = {
    TaskStatus.EXPLORING: AgentName.EXPLORER,
    TaskStatus.RESEARCHING: AgentName.RESEARCHER,
    TaskStatus.IMPLEMENTING: AgentName.IMPLEMENTER,
    TaskStatus.TESTING: AgentName.TESTER,
    TaskStatus.REVIEWING: AgentName.REVIEWER,
}

_NEXT_PHASE: Mapping[TaskStatus, TaskStatus] = {
    TaskStatus.EXPLORING: TaskStatus.RESEARCHING,
    TaskStatus.RESEARCHING: TaskStatus.IMPLEMENTING,
    TaskStatus.IMPLEMENTING: TaskStatus.TESTING,
    TaskStatus.TESTING: TaskStatus.REVIEWING,
}

_REQUIRED_AGENTS = frozenset(
    {
        AgentName.EXPLORER,
        AgentName.RESEARCHER,
        AgentName.IMPLEMENTER,
        AgentName.TESTER,
        AgentName.REVIEWER,
    }
)


class MainAgent:
    """Own state, sequence agents, and stop at explicit control/terminal states."""

    def __init__(
        self,
        agents: Mapping[AgentName, Agent],
        *,
        planner: Planner | None = None,
        machine: TaskStateMachine | None = None,
        tracer: Tracer | None = None,
        initial_evidence_provider: InitialEvidenceProvider | None = None,
        context_manager: ContextManager | None = None,
    ) -> None:
        if frozenset(agents) != _REQUIRED_AGENTS:
            missing = sorted(name.value for name in _REQUIRED_AGENTS.difference(agents))
            extra = sorted(name.value for name in frozenset(agents).difference(_REQUIRED_AGENTS))
            raise OrchestrationError(f"Invalid agent set; missing={missing}, extra={extra}.")
        for name, agent in agents.items():
            if agent.name is not name:
                raise OrchestrationError(
                    f"Agent mapping key {name.value} does not match agent name."
                )
        self._agents = dict(agents)
        self._planner = planner or DefaultPlanner()
        self._machine = machine or TaskStateMachine()
        self._tracer = tracer or NoOpTracer()
        self._initial_evidence_provider = initial_evidence_provider
        self._context_manager = context_manager

    def run(self, request: TaskRequest) -> TaskState:
        identifiers: dict[str, object] = {
            "task_id": request.task_id,
            "project_id": request.project_id,
            "session_id": request.session_id,
        }
        with self._tracer.observe(
            "task.run",
            kind=ObservationKind.TASK,
            input=request.original_request,
            metadata=identifiers,
        ) as observation:
            try:
                state = self._run(request)
            except Exception as exc:
                observation.update(error=str(exc))
                raise
            observation.update(
                output=state.final_result or {"status": state.status.value},
                metadata={
                    **identifiers,
                    "iterations": state.iterations,
                    "files_modified": [str(item.path) for item in state.files_modified],
                    "status": state.status.value,
                },
            )
            self._tracer.flush()
            return state

    def _run(self, request: TaskRequest) -> TaskState:
        objective = " ".join(request.original_request.split())
        if not objective:
            raise OrchestrationError("The normalized objective cannot be empty.")
        plan = self._planner.create_plan(request, objective)
        if not plan or any(not step.strip() for step in plan):
            raise OrchestrationError("Planner returned an empty or invalid plan.")

        initial_evidence = (
            ()
            if self._initial_evidence_provider is None
            else self._initial_evidence_provider.load(request)
        )
        state = TaskState(
            request=request,
            evidence=initial_evidence,
            sources_consulted=tuple(dict.fromkeys(item.source for item in initial_evidence)),
        )
        state = self._machine.transition(
            state,
            TaskStatus.PLANNING,
            actor=AgentName.MAIN,
            event_type="plan_created",
            updates={
                "normalized_objective": objective,
                "plan": plan,
                "plan_version": 1,
            },
        )
        if request.require_plan_approval:
            approval_id = f"{request.task_id}:plan:1"
            pending = PendingApproval(
                approval_id=approval_id,
                action="approve_plan",
                description="Approve the initial execution plan.",
                resume_status=TaskStatus.EXPLORING,
            )
            with self._tracer.observe(
                "approval.plan",
                input={"approval_id": approval_id, "action": pending.action},
            ) as approval_observation:
                paused = self._machine.transition(
                    state,
                    TaskStatus.WAITING_APPROVAL,
                    actor=AgentName.MAIN,
                    event_type="approval_requested",
                    payload={"approval_id": approval_id, "action": pending.action},
                    updates={
                        "pending_approval": pending,
                        "approvals": (
                            *state.approvals,
                            ApprovalRecord(approval_id=approval_id, action=pending.action),
                        ),
                    },
                )
                approval_observation.update(output={"status": "waiting"})
                return paused

        state = self._machine.transition(
            state,
            TaskStatus.EXPLORING,
            actor=AgentName.MAIN,
            event_type="execution_started",
        )
        return self._drive(state)

    def resume(self, state: TaskState, decision: ApprovalDecision) -> TaskState:
        with self._tracer.observe(
            "task.resume",
            kind=ObservationKind.TASK,
            input=decision,
            metadata={
                "task_id": state.request.task_id,
                "project_id": state.request.project_id,
                "session_id": state.request.session_id,
            },
        ) as observation:
            resumed = self._resume(state, decision)
            observation.update(output={"status": resumed.status.value})
            self._tracer.flush()
            return resumed

    def _resume(self, state: TaskState, decision: ApprovalDecision) -> TaskState:
        pending = state.pending_approval
        if state.status is not TaskStatus.WAITING_APPROVAL or pending is None:
            raise OrchestrationError("Only a task waiting for approval can be resumed.")
        records = tuple(
            record.model_copy(
                update={
                    "approved": decision.approved,
                    "reason": decision.reason,
                    "decided_at": utc_now(),
                }
            )
            if record.approval_id == pending.approval_id
            else record
            for record in state.approvals
        )
        with self._tracer.observe(
            "approval.decision",
            input={"approval_id": pending.approval_id},
        ) as approval_observation:
            approval_observation.update(
                output={"approved": decision.approved, "reason": decision.reason}
            )
            if not decision.approved:
                return self._machine.transition(
                    state,
                    TaskStatus.BLOCKED,
                    actor=AgentName.MAIN,
                    event_type="approval_rejected",
                    payload={"approval_id": pending.approval_id, "reason": decision.reason},
                    updates={"approvals": records, "pending_approval": None},
                )
            resumed = self._machine.transition(
                state,
                pending.resume_status,
                actor=AgentName.MAIN,
                event_type="approval_granted",
                payload={"approval_id": pending.approval_id},
                updates={"approvals": records, "pending_approval": None},
            )
        return self._drive(resumed)

    def _drive(self, state: TaskState) -> TaskState:
        while state.status in _PHASE_AGENT:
            agent_name = _PHASE_AGENT[state.status]
            agent = self._agents[agent_name]
            context = build_agent_context(state, agent_name, self._context_manager)
            with self._tracer.observe(
                f"agent.{agent_name.value}",
                kind=ObservationKind.AGENT,
                input=context,
                metadata={"agent": agent_name.value, "iteration": state.iterations + 1},
            ) as agent_observation:
                try:
                    result = agent.run(context)
                except Exception as exc:
                    agent_observation.update(error=str(exc))
                    error = ErrorInfo(
                        code=getattr(exc, "code", "agent_execution_error"),
                        message=f"{agent_name.value} failed ({type(exc).__name__}): {exc}",
                    )
                    return self._machine.transition(
                        state,
                        TaskStatus.FAILED,
                        actor=AgentName.MAIN,
                        event_type="agent_exception",
                        payload={"agent": agent_name.value, "error_code": error.code},
                        updates={"errors": (*state.errors, error)},
                    )
                agent_observation.update(output=result)

            state = self._machine.accumulate(state, result)
            self._trace_role_details(result)
            state = self._handle_result(state, result)
        return state

    def _handle_result(self, state: TaskState, result: AgentResult) -> TaskState:
        if result.status is AgentResultStatus.NO_EVIDENCE:
            return self._machine.transition(
                state,
                TaskStatus.STOPPED_NO_EVIDENCE,
                actor=AgentName.MAIN,
                event_type="insufficient_evidence",
                payload={"agent": result.agent.value, "missing": result.summary},
            )
        if result.status is AgentResultStatus.BLOCKED:
            return self._machine.transition(
                state,
                TaskStatus.BLOCKED,
                actor=AgentName.MAIN,
                event_type="agent_blocked",
                payload={"agent": result.agent.value, "reason": result.summary},
            )
        if result.status is AgentResultStatus.WAITING_APPROVAL:
            pending = result.pending_approval
            if pending is None:
                raise OrchestrationError("Waiting result omitted pending approval.")
            return self._machine.transition(
                state,
                TaskStatus.WAITING_APPROVAL,
                actor=AgentName.MAIN,
                event_type="approval_requested",
                payload={"approval_id": pending.approval_id, "action": pending.action},
                updates={"pending_approval": pending},
            )
        if result.status in {AgentResultStatus.FAILED, AgentResultStatus.REJECTED}:
            if result.agent in {AgentName.TESTER, AgentName.REVIEWER}:
                return self._replan_or_stop(state, result)
            return self._machine.transition(
                state,
                TaskStatus.FAILED,
                actor=AgentName.MAIN,
                event_type="agent_failed",
                payload={"agent": result.agent.value, "reason": result.summary},
            )

        if state.status is TaskStatus.REVIEWING:
            final_result = build_final_result(state, result)
            with self._tracer.observe(
                "result.final", input={"task_id": state.request.task_id}
            ) as obs:
                obs.update(
                    output=final_result,
                    metadata={"files_modified": [str(item.path) for item in state.files_modified]},
                )
                return self._machine.transition(
                    state,
                    TaskStatus.COMPLETED,
                    actor=AgentName.MAIN,
                    event_type="task_completed",
                    updates={"final_result": final_result},
                )
        destination = _NEXT_PHASE[state.status]
        return self._machine.transition(
            state,
            destination,
            actor=AgentName.MAIN,
            event_type="agent_completed",
            payload={"agent": result.agent.value},
        )

    def _replan_or_stop(self, state: TaskState, result: AgentResult) -> TaskState:
        if state.replan_count >= state.request.max_replans:
            return self._machine.transition(
                state,
                TaskStatus.BLOCKED,
                actor=AgentName.MAIN,
                event_type="replan_budget_exhausted",
                payload={"agent": result.agent.value, "reason": result.summary},
            )
        with self._tracer.observe(
            "orchestrator.replan",
            input={"failed_agent": result.agent.value, "reason": result.summary},
            metadata={"iteration": state.replan_count + 1},
        ) as observation:
            new_plan = self._planner.replan(state, result)
            observation.update(output={"plan": new_plan})
        decision = Decision(
            decision_id=f"{state.request.task_id}:replan:{state.replan_count + 1}",
            kind="replan",
            actor=AgentName.MAIN,
            reason=result.summary,
            evidence_ids=tuple(e.evidence_id for e in result.evidence),
        )
        replanning = self._machine.transition(
            state,
            TaskStatus.REPLANNING,
            actor=AgentName.MAIN,
            event_type="validation_failed",
            payload={"agent": result.agent.value},
            updates={
                "plan": new_plan,
                "plan_version": state.plan_version + 1,
                "replan_count": state.replan_count + 1,
                "decisions": (*state.decisions, decision),
            },
        )
        return self._machine.transition(
            replanning,
            TaskStatus.IMPLEMENTING,
            actor=AgentName.MAIN,
            event_type="replan_completed",
        )

    def _trace_role_details(self, result: AgentResult) -> None:
        if result.agent is AgentName.TESTER:
            with self._tracer.observe(
                "checks",
                input={"commands": result.commands},
                metadata={"agent": result.agent.value},
            ) as observation:
                observation.update(output={"checks": result.checks, "errors": result.errors})
        if result.agent is AgentName.REVIEWER:
            with self._tracer.observe(
                "review",
                input={"files": [str(change.path) for change in result.file_changes]},
                metadata={"agent": result.agent.value},
            ) as observation:
                observation.update(
                    output={"criteria_met": result.criteria_met, "summary": result.summary}
                )

Orchestrator = MainAgent
