from __future__ import annotations

from pathlib import Path
from typing import cast

from conftest import ProjectFixture

from coding_agent.config import AgentConfig, load_config
from coding_agent.models import FunctionCall, PolicyDecision, ToolStatus
from coding_agent.policies import AuthorizedToolGateway
from coding_agent.tools import (
    PermissionKind,
    StructuredTool,
    ToolContext,
    ToolExecution,
    ToolParameters,
    ToolPermissions,
    ToolRegistry,
    ToolRole,
    build_default_registry,
)


class EmptyParameters(ToolParameters):
    pass


class RecordingTool(StructuredTool[EmptyParameters]):
    def __init__(self, events: list[str]) -> None:
        super().__init__(
            name="recording_tool",
            description="Record deterministic execution order.",
            parameters_model=EmptyParameters,
            permissions=ToolPermissions(
                kind=PermissionKind.REPOSITORY,
                allowed_roles=frozenset({ToolRole.EXPLORER}),
            ),
        )
        self.events = events

    def _execute(
        self,
        context: ToolContext,
        parameters: EmptyParameters,
    ) -> ToolExecution:
        self.events.append("tool")
        return ToolExecution(output="executed")


class RecordingSink:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.decisions: list[PolicyDecision] = []

    def record(self, decision: PolicyDecision) -> None:
        self.events.append("policy")
        self.decisions.append(decision)


class RecordingConfigLoader:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __call__(self, path: str | Path) -> AgentConfig:
        self.events.append("config")
        return load_config(path)


def test_config_and_policy_are_evaluated_before_tool(project: ProjectFixture) -> None:
    events: list[str] = []
    tool = RecordingTool(events)
    sink = RecordingSink(events)
    gateway = AuthorizedToolGateway(
        ToolRegistry((tool,)),
        config_path=project.config_path,
        config_loader=RecordingConfigLoader(events),
        decision_sink=sink,
    )

    result = gateway.execute(
        FunctionCall(call_id="ordered", name="recording_tool", arguments={}),
        role=ToolRole.EXPLORER,
    )

    assert result.status is ToolStatus.EXECUTED
    assert events == ["config", "policy", "tool"]
    assert len(sink.decisions) == 1


def test_invalid_configuration_prevents_tool_execution(project: ProjectFixture) -> None:
    events: list[str] = []
    tool = RecordingTool(events)

    def invalidate(data: dict[str, object]) -> None:
        execution = cast(dict[str, object], data["execution"])
        execution["timeout_seconds"] = 0

    project.write_config(invalidate)
    gateway = AuthorizedToolGateway(
        ToolRegistry((tool,)),
        config_path=project.config_path,
    )

    result = gateway.execute(
        FunctionCall(call_id="invalid-config", name="recording_tool", arguments={}),
        role=ToolRole.EXPLORER,
    )

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code == "config_validation_error"
    assert not events
    assert gateway.decisions[0].rule == "config.valid"


def test_configuration_is_reloaded_before_each_call(project: ProjectFixture) -> None:
    target = project.workspace / "visible.txt"
    target.write_text("visible", encoding="utf-8")
    gateway = AuthorizedToolGateway(
        build_default_registry(),
        config_path=project.config_path,
    )
    call = FunctionCall(
        call_id="reload-1",
        name="read_file",
        arguments={"path": "visible.txt"},
    )

    first = gateway.execute(call, role=ToolRole.EXPLORER)

    def deny_file(data: dict[str, object]) -> None:
        permissions = cast(dict[str, object], data["permissions"])
        read = cast(dict[str, object], permissions["read"])
        read["deny"] = ["visible.txt"]

    project.write_config(deny_file)
    second = gateway.execute(
        call.model_copy(update={"call_id": "reload-2"}),
        role=ToolRole.EXPLORER,
    )

    assert first.status is ToolStatus.EXECUTED
    assert second.status is ToolStatus.DENIED
    assert len(gateway.decisions) == 2
