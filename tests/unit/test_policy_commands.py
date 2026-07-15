from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from conftest import ProjectFixture

from coding_agent.models import (
    ApprovalDecision,
    ApprovalRequest,
    FunctionCall,
    ToolStatus,
)
from coding_agent.policies import AuthorizedToolGateway
from coding_agent.tools import ToolRole, build_default_registry


class RecordingRunner:
    def __init__(self, *, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.calls: list[tuple[tuple[str, ...], Path, float]] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((tuple(argv), cwd, timeout))
        return subprocess.CompletedProcess(
            args=list(argv),
            returncode=self.returncode,
            stdout=self.stdout,
            stderr="",
        )


class ApproveAll:
    def __init__(self) -> None:
        self.requests: list[ApprovalRequest] = []

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        self.requests.append(request)
        return ApprovalDecision(approved=True, reason="approved in test")


def _command(call_id: str, argv: list[str]) -> FunctionCall:
    return FunctionCall(
        call_id=call_id,
        name="run_command",
        arguments={"argv": argv},
    )


def _set_role_commands(
    data: dict[str, object],
    *,
    role: str,
    rules: list[str],
) -> None:
    commands = cast(dict[str, object], data["commands"])
    allow_by_role = cast(dict[str, object], commands["allow_by_role"])
    allow_by_role[role] = rules


def test_denied_command_is_not_executed(project: ProjectFixture) -> None:
    runner = RecordingRunner()
    gateway = AuthorizedToolGateway(
        build_default_registry(command_runner=runner),
        config_path=project.config_path,
    )

    result = gateway.execute(
        _command("command-1", ["git", "push", "origin", "main"]),
        role=ToolRole.TESTER,
    )

    assert result.status is ToolStatus.DENIED
    assert not runner.calls
    assert result.policy is not None
    assert result.policy.rule == "commands.builtin.git_push"


def test_inspection_command_cannot_spawn_nested_process(project: ProjectFixture) -> None:
    runner = RecordingRunner()
    gateway = AuthorizedToolGateway(
        build_default_registry(command_runner=runner),
        config_path=project.config_path,
    )

    result = gateway.execute(
        _command("command-nested", ["find", ".", "-exec", "sh", "{}", ";"]),
        role=ToolRole.EXPLORER,
    )

    assert result.status is ToolStatus.DENIED
    assert not runner.calls
    assert result.policy is not None
    assert result.policy.rule == "commands.builtin.find_effect"


def test_command_requiring_approval_is_not_executed_without_approval(
    project: ProjectFixture,
) -> None:
    runner = RecordingRunner()
    gateway = AuthorizedToolGateway(
        build_default_registry(command_runner=runner),
        config_path=project.config_path,
    )

    result = gateway.execute(
        _command("command-2", ["python", "-m", "pip", "install", "demo"]),
        role=ToolRole.TESTER,
    )

    assert result.status is ToolStatus.REQUIRES_APPROVAL
    assert not runner.calls
    assert result.policy is not None
    assert result.policy.approval_granted is None


def test_matching_approval_executes_exact_command(project: ProjectFixture) -> None:
    runner = RecordingRunner(stdout="installed")
    approvals = ApproveAll()
    gateway = AuthorizedToolGateway(
        build_default_registry(command_runner=runner),
        config_path=project.config_path,
        approval_provider=approvals,
    )

    result = gateway.execute(
        _command("command-3", ["python", "-m", "pip", "install", "demo"]),
        role=ToolRole.TESTER,
    )

    assert result.status is ToolStatus.EXECUTED
    assert len(runner.calls) == 1
    assert len(approvals.requests) == 1
    assert result.policy is not None
    assert result.policy.approval_granted is True


def test_command_timeout_is_structured(project: ProjectFixture) -> None:
    project.write_config(lambda data: _set_role_commands(data, role="tester", rules=["sleep"]))
    gateway = AuthorizedToolGateway(
        build_default_registry(),
        config_path=project.config_path,
    )

    result = gateway.execute(
        _command("command-4", ["sleep", "2"]),
        role=ToolRole.TESTER,
    )

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code == "command_timeout"
    assert result.metadata["timed_out"] is True


def test_command_output_is_truncated_by_gateway(project: ProjectFixture) -> None:
    def configure(data: dict[str, object]) -> None:
        _set_role_commands(data, role="tester", rules=["echo"])
        execution = cast(dict[str, object], data["execution"])
        execution["max_output_chars"] = 20

    project.write_config(configure)
    runner = RecordingRunner(stdout="x" * 100)
    gateway = AuthorizedToolGateway(
        build_default_registry(command_runner=runner),
        config_path=project.config_path,
    )

    result = gateway.execute(
        _command("command-5", ["echo", "ignored-by-fake"]),
        role=ToolRole.TESTER,
    )

    assert result.status is ToolStatus.EXECUTED
    assert len(result.output) == 20
    assert result.metadata["truncated"] is True
    assert result.metadata["original_output_chars"] == 100
