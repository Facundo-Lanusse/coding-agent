"""Provider-neutral models shared by the basic harness and its adapters."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    """Base model for immutable messages and results."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class RunStatus(StrEnum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    MAX_ITERATIONS = "max_iterations"
    FAILED = "failed"


class ToolStatus(StrEnum):
    EXECUTED = "executed"
    FAILED = "failed"
    DENIED = "denied"
    REQUIRES_APPROVAL = "requires_approval"
    REJECTED = "rejected"


class PolicyOutcome(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_APPROVAL = "requires_approval"


class ApprovalKind(StrEnum):
    PLAN = "plan"
    TOOL = "tool"


class ErrorInfo(FrozenModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False


class ToolError(ErrorInfo):
    """Structured error returned by the tool gateway."""


class LLMUsage(FrozenModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ToolDefinition(FrozenModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    parameters: dict[str, object]
    strict: bool = True


class MessageInput(FrozenModel):
    type: Literal["message"] = "message"
    role: MessageRole
    content: str = Field(min_length=1)


class FunctionCallOutput(FrozenModel):
    type: Literal["function_call_output"] = "function_call_output"
    call_id: str = Field(min_length=1)
    output: str


class ProviderInput(FrozenModel):
    """Opaque, JSON-compatible continuation item returned by an LLM adapter."""

    type: Literal["provider_item"] = "provider_item"
    data: dict[str, object]


LLMInput: TypeAlias = Annotated[
    MessageInput | FunctionCallOutput | ProviderInput,
    Field(discriminator="type"),
]


class FunctionCall(FrozenModel):
    call_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: dict[str, object]


class LLMRequest(FrozenModel):
    instructions: str = Field(min_length=1)
    input: tuple[LLMInput, ...]
    tools: tuple[ToolDefinition, ...] = ()


class LLMResponse(FrozenModel):
    response_id: str | None = None
    model: str | None = None
    text: str = ""
    tool_calls: tuple[FunctionCall, ...] = ()
    continuation: tuple[ProviderInput, ...] = ()
    usage: LLMUsage = Field(default_factory=LLMUsage)


class ApprovalRequest(FrozenModel):
    kind: ApprovalKind
    action: str = Field(min_length=1)
    description: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)


class ApprovalDecision(FrozenModel):
    approved: bool
    reason: str = Field(min_length=1)


class PolicyDecision(FrozenModel):
    outcome: PolicyOutcome
    reason: str = Field(min_length=1)
    rule: str = Field(min_length=1)
    role: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)
    config_digest: str | None = None
    fingerprint: str = Field(min_length=1)
    approval_granted: bool | None = None


class ToolResult(FrozenModel):
    call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    status: ToolStatus
    output: str = ""
    error: ErrorInfo | None = None
    policy: PolicyDecision | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_error(self) -> ToolResult:
        if self.status is ToolStatus.EXECUTED and self.error is not None:
            raise ValueError("executed tool results cannot contain an error")
        if self.status is not ToolStatus.EXECUTED and self.error is None:
            raise ValueError("non-executed tool results require an error")
        return self


class AgentRunRequest(FrozenModel):
    task: str = Field(min_length=1)
    plan_mode: bool = True
    supervision_mode: bool = True
    max_iterations: int = Field(default=15, ge=1, le=100)


class Plan(FrozenModel):
    text: str = Field(min_length=1)


class RunMetrics(FrozenModel):
    planning_calls: int = Field(default=0, ge=0)
    model_iterations: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    usage: LLMUsage = Field(default_factory=LLMUsage)


class AgentRunResult(FrozenModel):
    status: RunStatus
    final_answer: str = ""
    plan: Plan | None = None
    metrics: RunMetrics = Field(default_factory=RunMetrics)
    tool_results: tuple[ToolResult, ...] = ()
    error: ErrorInfo | None = None

    @model_validator(mode="after")
    def validate_terminal_result(self) -> AgentRunResult:
        if self.status is RunStatus.COMPLETED and self.error is not None:
            raise ValueError("completed runs cannot contain an error")
        if self.status is not RunStatus.COMPLETED and self.error is None:
            raise ValueError("non-completed runs require an error")
        return self
