"""Typed configuration and environment loading for the coding agent."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import Literal, Protocol, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_PATTERN = re.compile(r"^\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}$")


class ConfigurationError(Exception):
    """Base class for configuration errors safe to show to the user."""

    code = "configuration_error"


class ConfigFileNotFoundError(ConfigurationError):
    code = "config_file_not_found"


class ConfigParseError(ConfigurationError):
    code = "config_parse_error"


class MissingEnvironmentVariableError(ConfigurationError):
    code = "missing_environment_variable"

    def __init__(self, variable: str) -> None:
        self.variable = variable
        super().__init__(f"Required environment variable is missing: {variable}")


class ConfigValidationError(ConfigurationError):
    code = "config_validation_error"


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LLMConfig(ConfigModel):
    provider: Literal["openai"]
    model: str = Field(min_length=1)
    max_output_tokens: int = Field(gt=0)
    store_responses: bool = False


class DenyRules(ConfigModel):
    deny: tuple[str, ...] = ()


class PermissionsConfig(ConfigModel):
    read: DenyRules
    write: DenyRules


class RoleCommandRules(ConfigModel):
    explorer: tuple[str, ...] = ()
    researcher: tuple[str, ...] = ()
    implementer: tuple[str, ...] = ()
    tester: tuple[str, ...] = ()
    reviewer: tuple[str, ...] = ()

    def for_role(self, role: str) -> tuple[str, ...]:
        value = getattr(self, role, ())
        return value if isinstance(value, tuple) else ()


class CommandsConfig(ConfigModel):
    deny: tuple[str, ...] = ()
    require_approval: tuple[str, ...] = ()
    allow_by_role: RoleCommandRules = Field(default_factory=RoleCommandRules)


class ExecutionConfig(ConfigModel):
    timeout_seconds: int = Field(gt=0)
    max_output_chars: int = Field(gt=0)
    max_read_bytes: int = Field(default=1_000_000, gt=0)
    max_list_entries: int = Field(default=1_000, gt=0)
    max_agent_iterations: int = Field(gt=0, le=100)
    max_identical_actions: int = Field(gt=0)
    max_identical_failures: int = Field(gt=0)


class RAGConfig(ConfigModel):
    enabled: bool
    collection_name: str = Field(min_length=1)
    collection_version: str = Field(min_length=1)
    persistence_path: Path
    embedding_model: str = Field(min_length=1)
    embedding_dimension: int = Field(gt=0)
    chunk_size_tokens: int = Field(gt=0)
    chunk_overlap_tokens: int = Field(ge=0)
    top_k: int = Field(gt=0)
    minimum_relevance: float = Field(ge=0.0, le=1.0)
    web_fallback: bool
    allowed_url_domains: tuple[str, ...]

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> RAGConfig:
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("RAG chunk overlap must be smaller than chunk size")
        if not self.allowed_url_domains:
            raise ValueError("RAG URL allowlist cannot be empty")
        return self


class MemoryConfig(ConfigModel):
    enabled: bool
    database_path: Path


class ObservabilityConfig(ConfigModel):
    provider: Literal["langfuse"]
    enabled: bool
    redact_sensitive_data: bool
    capture_content: bool = False
    max_payload_chars: int = Field(default=20_000, ge=128, le=1_000_000)


class AgentConfig(ConfigModel):
    workspace: Path
    llm: LLMConfig
    permissions: PermissionsConfig
    commands: CommandsConfig
    execution: ExecutionConfig
    rag: RAGConfig
    memory: MemoryConfig
    observability: ObservabilityConfig


class RuntimeSettings(BaseSettings):
    """Secrets come from the process environment; `.env` is never read implicitly."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        extra="ignore",
        frozen=True,
    )

    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )


class ConfigObservation(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]: ...

    def update(
        self,
        *,
        output: object | None = None,
        metadata: dict[str, object] | None = None,
        error: object | None = None,
    ) -> None: ...


class ConfigTracer(Protocol):
    def observe(
        self,
        name: str,
        *,
        input: object | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ConfigObservation: ...


def load_config(
    path: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
    tracer: ConfigTracer | None = None,
) -> AgentConfig:
    """Load YAML, expand allowlisted placeholder syntax, and validate all fields."""

    if tracer is None:
        return _load_config(path, environ=environ)
    with tracer.observe("config.load_validate", input={"path": str(path)}) as observation:
        try:
            config = _load_config(path, environ=environ)
        except Exception as exc:
            observation.update(error=str(exc))
            raise
        observation.update(
            output={
                "valid": True,
                "llm_provider": config.llm.provider,
                "observability_enabled": config.observability.enabled,
            }
        )
        return config


def _load_config(
    path: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> AgentConfig:

    config_path = Path(path)
    try:
        content = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigFileNotFoundError(f"Configuration file not found: {config_path}") from exc
    except OSError as exc:
        raise ConfigParseError(f"Cannot read configuration file: {config_path}") from exc

    try:
        raw: object = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ConfigParseError(f"Invalid YAML in configuration file: {config_path}") from exc

    if not isinstance(raw, dict):
        raise ConfigParseError("The configuration root must be a mapping.")

    expanded = _expand_environment(raw, os.environ if environ is None else environ)
    try:
        return AgentConfig.model_validate(expanded)
    except ValidationError as exc:
        raise ConfigValidationError(
            f"Configuration validation failed with {exc.error_count()} error(s)."
        ) from exc


def resolve_workspace(config: AgentConfig, config_path: str | Path) -> Path:
    """Resolve the configured workspace relative to the configuration file."""

    workspace = config.workspace
    if not workspace.is_absolute():
        workspace = Path(config_path).resolve().parent / workspace
    return workspace.resolve()


def _expand_environment(value: object, environ: Mapping[str, str]) -> object:
    if isinstance(value, str):
        match = _ENV_PATTERN.fullmatch(value)
        if match is None:
            return value
        variable, default = match.groups()
        if variable in environ:
            return environ[variable]
        if default is not None:
            return default
        raise MissingEnvironmentVariableError(variable)

    if isinstance(value, list):
        return [_expand_environment(item, environ) for item in value]

    if isinstance(value, dict):
        expanded: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ConfigParseError("Configuration mapping keys must be strings.")
            expanded[key] = _expand_environment(item, environ)
        return expanded

    return value
