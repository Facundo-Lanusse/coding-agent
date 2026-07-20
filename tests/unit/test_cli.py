from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from coding_agent import cli
from coding_agent.cli import app
from coding_agent.models import LLMRequest, LLMResponse, LLMUsage
from coding_agent.observability import ObservationKind, RecordingTracer

ROOT = Path(__file__).resolve().parents[2]


class FakeOpenAIClient:
    def __init__(self, **kwargs: object) -> None:
        del kwargs

    def respond(self, request: LLMRequest) -> LLMResponse:
        del request
        return LLMResponse(
            response_id="response-test",
            model="gpt-5-mini",
            text="Inspección completa.",
            usage=LLMUsage(input_tokens=10, output_tokens=4, total_tokens=14),
        )


class FlushRecordingTracer(RecordingTracer):
    def __init__(self) -> None:
        super().__init__()
        self.flushed = False

    def flush(self) -> None:
        self.flushed = True


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


def test_basic_run_is_traced_and_flushed(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer = FlushRecordingTracer()
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-placeholder")
    monkeypatch.setattr(cli, "OpenAIResponsesClient", FakeOpenAIClient)
    monkeypatch.setattr(cli, "create_tracer", lambda config, trace_seed: tracer)

    result = CliRunner().invoke(
        app,
        [
            "run",
            "--task",
            "Inspeccioná el proyecto.",
            "--config",
            str(ROOT / "agent.config.yaml"),
            "--no-plan",
            "--no-supervision",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Langfuse trace id: recording-trace" in result.output
    assert tracer.flushed is True
    assert [record.name for record in tracer.records] == [
        "coding-agent.run",
        "llm.response",
    ]
    assert tracer.records[0].kind is ObservationKind.TASK
    assert tracer.records[1].kind is ObservationKind.GENERATION
    assert tracer.records[1].parent_id == tracer.records[0].observation_id


def test_real_demo_requires_explicit_cost_confirmation_before_providers() -> None:
    result = CliRunner().invoke(app, ["demo", "real", "--scenario", "rag"])

    assert result.exit_code == 2
    assert "No API call made" in result.output
    assert "--confirm-cost" in result.output
