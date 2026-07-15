"""Validated, append-only transitions for shared task state."""

from __future__ import annotations

from collections.abc import Mapping

from coding_agent.state.models import AgentName, AgentResult, TaskEvent, TaskState, TaskStatus


class InvalidTransitionError(Exception):
    code = "invalid_task_transition"


ALLOWED_TRANSITIONS: Mapping[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.RECEIVED: frozenset({TaskStatus.PLANNING, TaskStatus.FAILED}),
    TaskStatus.PLANNING: frozenset(
        {
            TaskStatus.EXPLORING,
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.BLOCKED,
            TaskStatus.FAILED,
            TaskStatus.STOPPED_NO_EVIDENCE,
        }
    ),
    TaskStatus.EXPLORING: frozenset(
        {
            TaskStatus.RESEARCHING,
            TaskStatus.BLOCKED,
            TaskStatus.FAILED,
            TaskStatus.STOPPED_NO_EVIDENCE,
        }
    ),
    TaskStatus.RESEARCHING: frozenset(
        {
            TaskStatus.IMPLEMENTING,
            TaskStatus.BLOCKED,
            TaskStatus.FAILED,
            TaskStatus.STOPPED_NO_EVIDENCE,
        }
    ),
    TaskStatus.IMPLEMENTING: frozenset(
        {TaskStatus.TESTING, TaskStatus.WAITING_APPROVAL, TaskStatus.BLOCKED, TaskStatus.FAILED}
    ),
    TaskStatus.TESTING: frozenset(
        {TaskStatus.REVIEWING, TaskStatus.REPLANNING, TaskStatus.BLOCKED, TaskStatus.FAILED}
    ),
    TaskStatus.REVIEWING: frozenset(
        {TaskStatus.COMPLETED, TaskStatus.REPLANNING, TaskStatus.BLOCKED, TaskStatus.FAILED}
    ),
    TaskStatus.REPLANNING: frozenset(
        {
            TaskStatus.EXPLORING,
            TaskStatus.RESEARCHING,
            TaskStatus.IMPLEMENTING,
            TaskStatus.TESTING,
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.BLOCKED,
            TaskStatus.FAILED,
            TaskStatus.STOPPED_NO_EVIDENCE,
        }
    ),
    TaskStatus.WAITING_APPROVAL: frozenset(
        {
            TaskStatus.EXPLORING,
            TaskStatus.IMPLEMENTING,
            TaskStatus.REPLANNING,
            TaskStatus.BLOCKED,
            TaskStatus.FAILED,
        }
    ),
    TaskStatus.BLOCKED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.STOPPED_NO_EVIDENCE: frozenset(),
    TaskStatus.COMPLETED: frozenset(),
}


class TaskStateMachine:
    """Only component allowed to change task status or accumulate agent output."""

    def transition(
        self,
        state: TaskState,
        destination: TaskStatus,
        *,
        actor: AgentName,
        event_type: str,
        payload: dict[str, object] | None = None,
        updates: dict[str, object] | None = None,
    ) -> TaskState:
        if destination not in ALLOWED_TRANSITIONS[state.status]:
            raise InvalidTransitionError(
                f"Transition {state.status.value} -> {destination.value} is not allowed."
            )
        revision = state.revision + 1
        event = TaskEvent(
            sequence=len(state.events) + 1,
            revision=revision,
            event_type=event_type,
            actor=actor,
            from_status=state.status,
            to_status=destination,
            payload=payload or {},
        )
        values: dict[str, object] = {
            "status": destination,
            "current_phase": destination,
            "events": (*state.events, event),
            "revision": revision,
        }
        if updates:
            values.update(updates)
        return state.model_copy(update=values)

    def accumulate(self, state: TaskState, result: AgentResult) -> TaskState:
        sources = tuple(
            dict.fromkeys((*state.sources_consulted, *(e.source for e in result.evidence)))
        )
        files_read = tuple(dict.fromkeys((*state.files_read, *result.files_read)))
        return state.model_copy(
            update={
                "agent_results": (*state.agent_results, result),
                "evidence": (*state.evidence, *result.evidence),
                "sources_consulted": sources,
                "files_read": files_read,
                "files_modified": (*state.files_modified, *result.file_changes),
                "tool_invocations": (*state.tool_invocations, *result.tool_invocations),
                "commands": (*state.commands, *result.commands),
                "approvals": (*state.approvals, *result.approvals),
                "errors": (*state.errors, *result.errors),
                "observations": (*state.observations, *result.observations),
                "decisions": (*state.decisions, *result.decisions),
                "iterations": state.iterations + 1,
                "pending_approval": result.pending_approval,
            }
        )
