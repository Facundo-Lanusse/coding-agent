from __future__ import annotations

import pytest
from conftest import ProjectFixture

from coding_agent.models import FunctionCall, PolicyOutcome, ToolResult, ToolStatus
from coding_agent.policies import AuthorizedToolGateway
from coding_agent.tools import ToolRole, build_default_registry


def _read(gateway: AuthorizedToolGateway, path: str) -> ToolResult:
    return gateway.execute(
        FunctionCall(call_id="read-1", name="read_file", arguments={"path": path}),
        role=ToolRole.EXPLORER,
    )


def test_normal_path_is_allowed(project: ProjectFixture) -> None:
    target = project.workspace / "app.py"
    target.write_text("print('ok')\n", encoding="utf-8")
    gateway = AuthorizedToolGateway(
        build_default_registry(),
        config_path=project.config_path,
    )

    result = _read(gateway, "app.py")

    assert result.status is ToolStatus.EXECUTED
    assert result.output == "print('ok')\n"
    assert result.policy is not None
    assert result.policy.outcome is PolicyOutcome.ALLOWED


def test_parent_traversal_is_blocked(project: ProjectFixture) -> None:
    outside = project.workspace.parent / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    gateway = AuthorizedToolGateway(
        build_default_registry(),
        config_path=project.config_path,
    )

    result = _read(gateway, "../outside.txt")

    assert result.status is ToolStatus.DENIED
    assert result.policy is not None
    assert result.policy.rule == "permissions.read.containment"


def test_similar_prefix_outside_workspace_is_blocked(project: ProjectFixture) -> None:
    sibling = project.workspace.parent / f"{project.workspace.name}-other"
    sibling.mkdir()
    target = sibling / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    gateway = AuthorizedToolGateway(
        build_default_registry(),
        config_path=project.config_path,
    )

    result = _read(gateway, str(target))

    assert result.status is ToolStatus.DENIED
    assert result.policy is not None
    assert result.policy.rule == "permissions.read.containment"


def test_symlink_that_escapes_workspace_is_blocked(project: ProjectFixture) -> None:
    outside = project.workspace.parent / "external.txt"
    outside.write_text("external", encoding="utf-8")
    link = project.workspace / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not available on this platform")
    gateway = AuthorizedToolGateway(
        build_default_registry(),
        config_path=project.config_path,
    )

    result = _read(gateway, "linked.txt")

    assert result.status is ToolStatus.DENIED
    assert result.policy is not None
    assert result.policy.rule == "permissions.read.containment"


@pytest.mark.parametrize(
    "relative",
    [".env", ".env.local", "certificate.pem", "private.key", "secrets/value.txt"],
)
def test_sensitive_paths_are_blocked(project: ProjectFixture, relative: str) -> None:
    target = project.workspace / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("synthetic test value", encoding="utf-8")
    gateway = AuthorizedToolGateway(
        build_default_registry(),
        config_path=project.config_path,
    )

    result = _read(gateway, relative)

    assert result.status is ToolStatus.DENIED
    assert result.policy is not None
    assert result.policy.rule == "permissions.secrets"


def test_github_path_is_blocked_for_write(project: ProjectFixture) -> None:
    target = project.workspace / ".github" / "workflow.yml"
    target.parent.mkdir()
    gateway = AuthorizedToolGateway(
        build_default_registry(),
        config_path=project.config_path,
    )

    result = gateway.execute(
        FunctionCall(
            call_id="write-1",
            name="write_file",
            arguments={"path": ".github/workflow.yml", "content": "blocked"},
        ),
        role=ToolRole.IMPLEMENTER,
    )

    assert result.status is ToolStatus.DENIED
    assert not target.exists()
