from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

from conftest import ProjectFixture

from coding_agent.models import FunctionCall, ToolStatus
from coding_agent.policies import AuthorizedToolGateway
from coding_agent.tools import ToolRole, build_default_registry
from coding_agent.tools.web import SearchResult


class FakeWebProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...], int]] = []

    def search(
        self,
        query: str,
        *,
        allowed_domains: tuple[str, ...],
        max_results: int,
    ) -> tuple[SearchResult, ...]:
        self.calls.append((query, allowed_domains, max_results))
        return (
            SearchResult(
                title="Official reference",
                url="https://docs.example.test/reference",
                snippet="Technical evidence.",
            ),
        )


class RepositoryRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], Path, float]] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((tuple(argv), cwd, timeout))
        return subprocess.CompletedProcess(argv, 0, stdout="## main\n", stderr="")


def test_web_search_uses_injected_provider(project: ProjectFixture) -> None:
    provider = FakeWebProvider()
    gateway = AuthorizedToolGateway(
        build_default_registry(web_provider=provider),
        config_path=project.config_path,
    )

    result = gateway.execute(
        FunctionCall(
            call_id="web-1",
            name="web_search",
            arguments={
                "query": "framework documentation",
                "allowed_domains": ["docs.example.test"],
                "max_results": 3,
            },
        ),
        role=ToolRole.RESEARCHER,
    )

    assert result.status is ToolStatus.EXECUTED
    assert provider.calls == [("framework documentation", ("docs.example.test",), 3)]
    assert json.loads(result.output)[0]["title"] == "Official reference"


def test_web_search_is_denied_to_implementer(project: ProjectFixture) -> None:
    provider = FakeWebProvider()
    gateway = AuthorizedToolGateway(
        build_default_registry(web_provider=provider),
        config_path=project.config_path,
    )

    result = gateway.execute(
        FunctionCall(
            call_id="web-2",
            name="web_search",
            arguments={"query": "should not execute"},
        ),
        role=ToolRole.IMPLEMENTER,
    )

    assert result.status is ToolStatus.DENIED
    assert not provider.calls


def test_repository_status_uses_fixed_workspace(project: ProjectFixture) -> None:
    runner = RepositoryRunner()
    gateway = AuthorizedToolGateway(
        build_default_registry(command_runner=runner),
        config_path=project.config_path,
    )

    result = gateway.execute(
        FunctionCall(
            call_id="repo-1",
            name="repository_status",
            arguments={},
        ),
        role=ToolRole.REVIEWER,
    )

    assert result.status is ToolStatus.EXECUTED
    assert runner.calls[0][0] == ("git", "status", "--short", "--branch")
    assert runner.calls[0][1] == project.workspace
