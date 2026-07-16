from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from coding_agent.cli import app

ROOT = Path(__file__).resolve().parents[2]


def test_cli_help_does_not_require_credentials() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "coding-agent" in result.stdout
    assert "config" in result.stdout


def test_config_validate_does_not_contact_openai() -> None:
    result = CliRunner().invoke(
        app,
        ["config", "validate", "--config", str(ROOT / "agent.config.yaml")],
    )

    assert result.exit_code == 0
    assert "Configuration valid." in result.stdout
    assert "gpt-5-mini" in result.stdout


def test_real_demo_requires_explicit_cost_confirmation_before_providers() -> None:
    result = CliRunner().invoke(app, ["demo", "real", "--scenario", "rag"])

    assert result.exit_code == 2
    assert "No API call made" in result.output
    assert "--confirm-cost" in result.output
