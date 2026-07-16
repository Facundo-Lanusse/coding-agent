from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.config import (
    MissingEnvironmentVariableError,
    RuntimeSettings,
    load_config,
    resolve_workspace,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "agent.config.yaml"


def test_load_config_expands_environment_and_validates_types() -> None:
    config = load_config(CONFIG_PATH, environ={"OPENAI_MODEL": "model-from-environment"})

    assert config.llm.model == "model-from-environment"
    assert config.execution.max_agent_iterations == 20
    assert config.permissions.read.deny[0] == ".env"
    assert resolve_workspace(config, CONFIG_PATH) == (ROOT / "examples/fastapi_demo").resolve()


def test_load_config_uses_declared_default_when_environment_is_absent() -> None:
    config = load_config(CONFIG_PATH, environ={})

    assert config.llm.model == "gpt-5-mini"


def test_required_model_environment_variable_missing_is_explicit(tmp_path: Path) -> None:
    config_text = CONFIG_PATH.read_text(encoding="utf-8").replace(
        "${OPENAI_MODEL:-gpt-5-mini}",
        "${OPENAI_MODEL}",
    )
    config_path = tmp_path / "agent.config.yaml"
    config_path.write_text(config_text, encoding="utf-8")

    with pytest.raises(MissingEnvironmentVariableError) as error:
        load_config(config_path, environ={})

    assert error.value.variable == "OPENAI_MODEL"
    assert "OPENAI_MODEL" in str(error.value)


def test_runtime_settings_load_secret_from_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-openai-placeholder")
    monkeypatch.setenv("TAVILY_API_KEY", "test-only-tavily-placeholder")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "test-only-public-placeholder")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "test-only-secret-placeholder")

    settings = RuntimeSettings()

    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "test-only-openai-placeholder"
    assert settings.tavily_api_key is not None
    assert settings.langfuse_public_key is not None
    assert settings.langfuse_secret_key is not None
    assert "test-only-openai-placeholder" not in repr(settings)
    assert "test-only-tavily-placeholder" not in repr(settings)
