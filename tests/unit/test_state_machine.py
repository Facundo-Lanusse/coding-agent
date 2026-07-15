from pathlib import Path

import pytest
from pydantic import ValidationError

from coding_agent.state import (
    AgentName,
    Evidence,
    EvidenceSource,
    InvalidTransitionError,
    TaskRequest,
    TaskState,
    TaskStateMachine,
    TaskStatus,
)


def request() -> TaskRequest:
    return TaskRequest(
        task_id="task-1",
        project_id="project-1",
        session_id="session-1",
        original_request="Add a health endpoint",
        workspace=Path("/workspace"),
    )


def test_state_machine_records_explicit_append_only_transition() -> None:
    machine = TaskStateMachine()
    initial = TaskState(request=request())

    planning = machine.transition(
        initial,
        TaskStatus.PLANNING,
        actor=AgentName.MAIN,
        event_type="plan_created",
    )

    assert initial.status is TaskStatus.RECEIVED
    assert planning.status is TaskStatus.PLANNING
    assert planning.revision == 1
    assert planning.events[0].sequence == 1
    assert planning.events[0].from_status is TaskStatus.RECEIVED


def test_state_machine_rejects_undeclared_transition() -> None:
    with pytest.raises(InvalidTransitionError):
        TaskStateMachine().transition(
            TaskState(request=request()),
            TaskStatus.COMPLETED,
            actor=AgentName.MAIN,
            event_type="invalid",
        )


def test_inference_requires_explicit_supporting_evidence() -> None:
    with pytest.raises(ValidationError, match="supporting evidence"):
        Evidence(
            evidence_id="inference-1",
            source=EvidenceSource.INFERENCE,
            reference="agent reasoning",
            content="The endpoint probably needs authentication.",
        )
