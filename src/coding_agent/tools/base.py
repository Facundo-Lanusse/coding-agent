"""Common contracts for structured, policy-controlled tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Generic, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ConfigDict, ValidationError

from coding_agent.config import AgentConfig
from coding_agent.models import ToolDefinition


class ToolRole(StrEnum):
    EXPLORER = "explorer"
    RESEARCHER = "researcher"
    IMPLEMENTER = "implementer"
    TESTER = "tester"
    REVIEWER = "reviewer"


class PermissionKind(StrEnum):
    READ = "read"
    WRITE = "write"
    COMMAND = "command"
    REPOSITORY = "repository"
    WEB = "web"


class ToolParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True, slots=True)
class ToolPermissions:
    kind: PermissionKind
    allowed_roles: frozenset[ToolRole]
    path_argument: str | None = None
    command_argument: str | None = None
    sensitive_arguments: frozenset[str] = frozenset()
    mutates_workspace: bool = False


@dataclass(frozen=True, slots=True)
class ToolSpec:
    definition: ToolDefinition
    permissions: ToolPermissions


@dataclass(frozen=True, slots=True)
class ToolExecution:
    output: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


class ToolInputError(Exception):
    code = "invalid_tool_arguments"


class ToolExecutionFailure(Exception):
    """Expected tool failure that can safely cross the gateway boundary."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        output: str = "",
        retryable: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.code = code
        self.output = output
        self.retryable = retryable
        self.metadata = metadata or {}
        super().__init__(message)


class PathAuthorizer(Protocol):
    def resolve_read(self, value: str) -> Path:
        """Return a canonical allowed read path or raise a policy error."""

    def resolve_write(self, value: str) -> Path:
        """Return a canonical allowed write path or raise a policy error."""

    def is_read_allowed(self, path: Path) -> bool:
        """Return whether a discovered path may be exposed."""


@dataclass(frozen=True, slots=True)
class ToolContext:
    config: AgentConfig
    workspace: Path
    paths: PathAuthorizer


@runtime_checkable
class Tool(Protocol):
    @property
    def spec(self) -> ToolSpec:
        """Expose LLM definition and permission metadata."""

    def parse_arguments(self, arguments: dict[str, object]) -> BaseModel:
        """Validate untrusted arguments without causing effects."""

    def execute(self, context: ToolContext, parameters: BaseModel) -> ToolExecution:
        """Execute previously validated parameters."""


ParametersT = TypeVar("ParametersT", bound=BaseModel)


class StructuredTool(ABC, Generic[ParametersT]):
    """Pydantic-backed base that derives a strict JSON schema."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        parameters_model: type[ParametersT],
        permissions: ToolPermissions,
    ) -> None:
        self._parameters_model = parameters_model
        self._spec = ToolSpec(
            definition=ToolDefinition(
                name=name,
                description=description,
                parameters=parameters_model.model_json_schema(),
            ),
            permissions=permissions,
        )

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    def parse_arguments(self, arguments: dict[str, object]) -> BaseModel:
        try:
            return self._parameters_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolInputError(
                f"Invalid arguments for tool {self.spec.definition.name}."
            ) from exc

    def execute(self, context: ToolContext, parameters: BaseModel) -> ToolExecution:
        if not isinstance(parameters, self._parameters_model):
            raise ToolInputError(
                f"Parameters for tool {self.spec.definition.name} were not validated."
            )
        return self._execute(context, parameters)

    @abstractmethod
    def _execute(self, context: ToolContext, parameters: ParametersT) -> ToolExecution:
        """Implement the effect behind the policy gateway."""
