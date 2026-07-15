from __future__ import annotations

from pathlib import Path

from coding_agent.agents import AgentContext, ReviewerAgent
from coding_agent.demo.scenarios import DemoBackend, DemoScenarioRunner
from coding_agent.state import (
    AgentName,
    EvidenceSource,
    FileChange,
    FileOperation,
    TaskStatus,
)


def runner(tmp_path: Path) -> DemoScenarioRunner:
    return DemoScenarioRunner(
        seed_root=Path("examples/fastapi_demo/seed"),
        runtime_root=tmp_path / "runtime",
        rag_sources=Path("rag_sources"),
        output_root=tmp_path / "artifacts",
    )


def test_scenario_a_coordinates_all_roles_rag_checks_and_review(tmp_path: Path) -> None:
    sentinel = tmp_path / "outside.txt"
    sentinel.write_text("untouched", encoding="utf-8")

    run = runner(tmp_path).run_rag()

    assert run.state.status is TaskStatus.COMPLETED
    assert [result.agent for result in run.state.agent_results] == [
        AgentName.EXPLORER,
        AgentName.RESEARCHER,
        AgentName.IMPLEMENTER,
        AgentName.TESTER,
        AgentName.REVIEWER,
    ]
    assert EvidenceSource.RAG in run.state.sources_consulted
    assert EvidenceSource.WEB not in run.state.sources_consulted
    assert run.state.final_result is not None
    assert run.state.final_result.reviewer_accepted
    assert all(check.passed for result in run.state.agent_results for check in result.checks)
    assert (run.workspace / "app/routers/health.py").read_text(encoding="utf-8").find(
        '@router.get("/ready"'
    ) >= 0
    assert "test_readiness" in (run.workspace / "tests/test_health.py").read_text(
        encoding="utf-8"
    )
    assert run.artifact.sources
    assert run.artifact.diff
    assert sentinel.read_text(encoding="utf-8") == "untouched"


def test_scenario_b_persists_memory_across_runner_instances(tmp_path: Path) -> None:
    database = tmp_path / "memory.sqlite3"
    first_runner = runner(tmp_path)

    first = first_runner.run_memory_session_1(database)
    second_runner = runner(tmp_path)
    second = second_runner.run_memory_session_2(database)

    assert first.state.status is TaskStatus.COMPLETED
    assert second.state.status is TaskStatus.COMPLETED
    assert len(second.artifact.memory_retrieved) == 4
    assert EvidenceSource.MEMORY in second.state.sources_consulted
    assert "thin and delegate" in " ".join(second.artifact.memory_retrieved)
    assert '@router.get("/version"' in (second.workspace / "app/routers/meta.py").read_text(
        encoding="utf-8"
    )
    assert second.state.final_result is not None
    assert second.state.final_result.reviewer_accepted


def test_scenario_c_stops_after_two_identical_failures_and_enforces_policy(
    tmp_path: Path,
) -> None:
    run = runner(tmp_path).run_safety()

    assert run.state.status is TaskStatus.BLOCKED
    assert run.state.replan_count == 1
    failing = [
        command
        for command in run.state.commands
        if "test_intentional_failure" in " ".join(command)
    ]
    assert len(failing) == 2
    assert not (run.workspace / ".github").exists()
    policy_events = [event for event in run.artifact.control_events if event.event_type == "policy"]
    assert [event.outcome for event in policy_events].count("requires_approval") == 2
    assert [event.outcome for event in policy_events].count("denied") == 1
    assert any(event.event_type == "loop.no_progress" for event in run.artifact.control_events)
    assert "no third failing check" in run.artifact.final_summary.lower()


def test_reviewer_rejects_a_change_outside_requested_scope() -> None:
    changes = (
        FileChange(
            path=Path("app/routers/health.py"),
            operation=FileOperation.MODIFIED,
            actor=AgentName.IMPLEMENTER,
            authorized=True,
        ),
        FileChange(
            path=Path("app/core/config.py"),
            operation=FileOperation.MODIFIED,
            actor=AgentName.IMPLEMENTER,
            authorized=True,
        ),
    )
    reviewer = ReviewerAgent(DemoBackend(scenario="rag", workspace=Path(".")))

    result = reviewer.run(
        AgentContext(
            task_id="review-scope",
            original_request="Add readiness.",
            normalized_objective="Add readiness.",
            plan=("Review diff.",),
            file_changes=changes,
        )
    )

    assert result.status.value == "rejected"
    assert result.criteria_met is False
    assert result.observations == ("Change outside requested scope: app/core/config.py",)
