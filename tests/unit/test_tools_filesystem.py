from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

import pytest
from conftest import ProjectFixture

from coding_agent.models import FunctionCall, ToolStatus
from coding_agent.policies import REDACTED, AuthorizedToolGateway
from coding_agent.tools import ToolRole, build_default_registry


def test_write_file_uses_atomic_replace(
    project: ProjectFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = project.workspace / "module.py"
    target.write_text("old\n", encoding="utf-8")
    calls: list[tuple[Path, Path]] = []
    original_replace = os.replace

    def recording_replace(source: str | Path, destination: str | Path) -> None:
        calls.append((Path(source), Path(destination)))
        original_replace(source, destination)

    monkeypatch.setattr("coding_agent.tools.filesystem.os.replace", recording_replace)
    gateway = AuthorizedToolGateway(
        build_default_registry(),
        config_path=project.config_path,
    )

    result = gateway.execute(
        FunctionCall(
            call_id="write-atomic",
            name="write_file",
            arguments={"path": "module.py", "content": "new\n"},
        ),
        role=ToolRole.IMPLEMENTER,
    )

    assert result.status is ToolStatus.EXECUTED
    assert target.read_text(encoding="utf-8") == "new\n"
    assert calls and calls[0][1] == target
    assert result.metadata["atomic"] is True
    assert result.policy is not None
    assert result.policy.arguments["content"] == REDACTED
    assert not list(project.workspace.glob(".module.py.*.tmp"))


def test_read_file_enforces_size_limit(project: ProjectFixture) -> None:
    target = project.workspace / "large.txt"
    target.write_text("x" * 100, encoding="utf-8")

    def configure(data: dict[str, object]) -> None:
        execution = cast(dict[str, object], data["execution"])
        execution["max_read_bytes"] = 10

    project.write_config(configure)
    gateway = AuthorizedToolGateway(
        build_default_registry(),
        config_path=project.config_path,
    )

    result = gateway.execute(
        FunctionCall(
            call_id="read-large",
            name="read_file",
            arguments={"path": "large.txt"},
        ),
        role=ToolRole.EXPLORER,
    )

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code == "file_too_large"


def test_list_and_search_skip_denied_files(project: ProjectFixture) -> None:
    package = project.workspace / "package"
    package.mkdir()
    (package / "main.py").write_text("needle = True\n", encoding="utf-8")
    (project.workspace / ".env").write_text("synthetic", encoding="utf-8")
    gateway = AuthorizedToolGateway(
        build_default_registry(),
        config_path=project.config_path,
    )

    listed = gateway.execute(
        FunctionCall(
            call_id="list-1",
            name="list_files",
            arguments={"path": ".", "pattern": "*.py"},
        ),
        role=ToolRole.EXPLORER,
    )
    searched = gateway.execute(
        FunctionCall(
            call_id="search-1",
            name="search_files",
            arguments={"path": ".", "query": "needle", "pattern": "*.py"},
        ),
        role=ToolRole.EXPLORER,
    )

    assert listed.status is ToolStatus.EXECUTED
    assert listed.output == "package/main.py"
    assert ".env" not in listed.output
    assert searched.status is ToolStatus.EXECUTED
    matches = json.loads(searched.output)
    assert matches == [{"path": "package/main.py", "line": 1, "text": "needle = True"}]
