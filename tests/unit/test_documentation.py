"""Delivery documentation and local-route validation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from coding_agent.cli import app

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "docs/case_use.md",
    ROOT / "docs/architecture.md",
    ROOT / "docs/state_and_memory.md",
    ROOT / "docs/rag.md",
    ROOT / "docs/security_policies.md",
    ROOT / "docs/context_and_loop_detection.md",
    ROOT / "docs/observability.md",
    ROOT / "docs/testing.md",
    ROOT / "docs/demo_runbook.md",
    ROOT / "docs/reflection.md",
    ROOT / "docs/delivery_checklist.md",
    ROOT / "docs/requirements_matrix.md",
)
RUN_IDS = (
    "scenario-a-rag",
    "scenario-b-session-1",
    "scenario-b-session-2",
    "scenario-c-safety",
)
ARTIFACT_FILES = frozenset(
    {
        "run.json",
        "task_state.json",
        "summary.md",
        "sources.json",
        "commands.json",
        "memory.json",
        "events.json",
        "diff.patch",
    }
)
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def test_required_documents_and_artifact_bundles_exist() -> None:
    assert all(path.is_file() for path in REQUIRED_DOCUMENTS)
    for run_id in RUN_IDS:
        run_directory = ROOT / "docs/evidence/runs" / run_id
        assert run_directory.is_dir()
        assert ARTIFACT_FILES.issubset(path.name for path in run_directory.iterdir())


def test_local_markdown_links_resolve() -> None:
    markdown_files = (ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md")))
    broken: list[str] = []
    for markdown in markdown_files:
        content = markdown.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(content):
            target = raw_target.strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative_path = target.split("#", maxsplit=1)[0]
            if not relative_path:
                continue
            resolved = (markdown.parent / relative_path).resolve()
            if not resolved.exists():
                broken.append(f"{markdown.relative_to(ROOT)} -> {target}")
    assert broken == []


def test_requirements_matrix_has_one_seven_column_row_per_requirement() -> None:
    matrix = (ROOT / "docs/requirements_matrix.md").read_text(encoding="utf-8")
    rows = [line for line in matrix.splitlines() if re.match(r"^\| R\d{2}\.", line)]
    identifiers = [re.match(r"^\| (R\d{2})\.", row) for row in rows]
    assert [match.group(1) for match in identifiers if match is not None] == [
        f"R{number:02d}" for number in range(1, 45)
    ]
    assert all(len(row.split("|")) - 2 == 7 for row in rows)


@pytest.mark.parametrize(
    "arguments",
    [
        ("--help",),
        ("config", "--help"),
        ("config", "validate", "--help"),
        ("run", "--help"),
        ("rag", "--help"),
        ("rag", "ingest", "--help"),
        ("rag", "query", "--help"),
        ("demo", "--help"),
        ("demo", "reset", "--help"),
        ("demo", "rag", "--help"),
        ("demo", "memory", "--help"),
        ("demo", "safety", "--help"),
        ("demo", "all", "--help"),
        ("demo", "real", "--help"),
    ],
)
def test_documented_cli_routes_have_help(arguments: tuple[str, ...]) -> None:
    result = CliRunner().invoke(app, list(arguments))
    assert result.exit_code == 0, result.output
