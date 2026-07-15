"""Single authorized gateway used for every production tool invocation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from coding_agent.approval import ApprovalProvider
from coding_agent.config import AgentConfig, ConfigurationError, load_config
from coding_agent.harness.loop import ToolBinding
from coding_agent.models import (
    ApprovalKind,
    ApprovalRequest,
    FunctionCall,
    PolicyDecision,
    PolicyOutcome,
    ToolError,
    ToolResult,
    ToolStatus,
)
from coding_agent.observability import NoOpTracer, ObservationKind, Tracer
from coding_agent.policies.engine import PolicyEngine
from coding_agent.tools.base import ToolContext, ToolExecutionFailure, ToolInputError, ToolRole
from coding_agent.tools.registry import ToolRegistry, UnknownToolError

ConfigLoader = Callable[[str | Path], AgentConfig]


class PolicyDecisionSink(Protocol):
    def record(self, decision: PolicyDecision) -> None:
        """Persist or observe an already redacted decision."""


class AuthorizedToolGateway:
    """Reload config, authorize, approve when required, then execute exactly once."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        config_path: str | Path,
        policy_engine: PolicyEngine | None = None,
        approval_provider: ApprovalProvider | None = None,
        config_loader: ConfigLoader = load_config,
        decision_sink: PolicyDecisionSink | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self._registry = registry
        self._config_path = Path(config_path)
        self._policy_engine = policy_engine or PolicyEngine()
        self._approval_provider = approval_provider
        self._config_loader = config_loader
        self._decision_sink = decision_sink
        self._tracer = tracer or NoOpTracer()
        self._decisions: list[PolicyDecision] = []

    @property
    def decisions(self) -> tuple[PolicyDecision, ...]:
        return tuple(self._decisions)

    def bindings(self, role: ToolRole) -> tuple[ToolBinding, ...]:
        """Expose only role-eligible tools to the Phase 01 harness."""

        bindings: list[ToolBinding] = []
        for tool in self._registry.for_role(role):
            bindings.append(
                ToolBinding(
                    definition=tool.spec.definition,
                    handler=lambda call, selected_role=role: self.execute(
                        call,
                        role=selected_role,
                    ),
                )
            )
        return tuple(bindings)

    def execute(self, call: FunctionCall, *, role: ToolRole) -> ToolResult:
        with self._tracer.observe(
            f"tool.{call.name}",
            kind=ObservationKind.TOOL,
            input={"tool": call.name, "parameters": call.arguments},
            metadata={"tool": call.name, "agent": role.value},
        ) as tool_observation:
            result = self._execute(call, role=role)
            tool_observation.update(
                output={"status": result.status.value, "output": result.output},
                metadata=result.metadata,
                error=result.error,
            )
            return result

    def _execute(self, call: FunctionCall, *, role: ToolRole) -> ToolResult:
        """Execute one call after fresh config validation and policy evaluation."""

        with self._tracer.observe(
            "config.load_validate",
            input={"path": str(self._config_path)},
        ) as config_observation:
            try:
                config = self._config_loader(self._config_path)
            except ConfigurationError as exc:
                config_observation.update(error=str(exc))
                decision = _precondition_decision(
                    call,
                    role,
                    reason="Configuration validation failed before tool execution.",
                    rule="config.valid",
                )
                self._record(decision)
                return _failure(
                    call,
                    status=ToolStatus.FAILED,
                    code=exc.code,
                    message=str(exc),
                    policy=decision,
                )
            config_observation.update(output={"valid": True})

        try:
            tool = self._registry.get(call.name)
        except UnknownToolError as exc:
            decision = _precondition_decision(
                call,
                role,
                reason="Tool is not registered.",
                rule="registry.registered",
            )
            self._record(decision)
            return _failure(
                call,
                status=ToolStatus.FAILED,
                code=exc.code,
                message=str(exc),
                policy=decision,
            )

        try:
            parameters = tool.parse_arguments(call.arguments)
        except ToolInputError as exc:
            decision = _precondition_decision(
                call,
                role,
                reason="Tool arguments failed schema validation.",
                rule="arguments.schema",
            )
            self._record(decision)
            return _failure(
                call,
                status=ToolStatus.FAILED,
                code=exc.code,
                message=str(exc),
                policy=decision,
            )

        with self._tracer.observe(
            "policy.evaluate",
            input={"tool": call.name, "parameters": call.arguments},
            metadata={"agent": role.value},
        ) as policy_observation:
            decision, guard = self._policy_engine.evaluate(
                tool=tool,
                parameters=parameters,
                config=config,
                config_path=self._config_path,
                role=role,
            )
            policy_observation.update(output=decision)

        if decision.outcome is PolicyOutcome.DENIED:
            self._record(decision)
            return _failure(
                call,
                status=ToolStatus.DENIED,
                code="policy_denied",
                message=decision.reason,
                policy=decision,
            )

        if decision.outcome is PolicyOutcome.REQUIRES_APPROVAL:
            with self._tracer.observe(
                "approval.tool",
                input={"tool": call.name, "reason": decision.reason},
            ) as approval_observation:
                if self._approval_provider is None:
                    approval_observation.update(output={"approved": None})
                    self._record(decision)
                    return _failure(
                        call,
                        status=ToolStatus.REQUIRES_APPROVAL,
                        code="approval_required",
                        message=decision.reason,
                        policy=decision,
                    )
                approval = self._approval_provider.request_approval(
                    ApprovalRequest(
                        kind=ApprovalKind.TOOL,
                        action=call.name,
                        description=decision.reason,
                        arguments=decision.arguments,
                    )
                )
                approval_observation.update(
                    output={"approved": approval.approved, "reason": approval.reason}
                )
                decision = decision.model_copy(
                    update={"approval_granted": approval.approved}
                )
                if not approval.approved:
                    self._record(decision)
                    return _failure(
                        call,
                        status=ToolStatus.DENIED,
                        code="approval_rejected",
                        message=approval.reason,
                        policy=decision,
                    )

        self._record(decision)
        context = ToolContext(config=config, workspace=guard.workspace, paths=guard)
        try:
            execution = tool.execute(context, parameters)
        except ToolExecutionFailure as exc:
            output, metadata = _limit_output(
                exc.output,
                exc.metadata,
                config.execution.max_output_chars,
            )
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.name,
                status=ToolStatus.FAILED,
                output=output,
                error=ToolError(
                    code=exc.code,
                    message=str(exc),
                    retryable=exc.retryable,
                ),
                policy=decision,
                metadata=metadata,
            )
        except Exception as exc:
            return _failure(
                call,
                status=ToolStatus.FAILED,
                code="unexpected_tool_error",
                message=f"Tool execution failed ({type(exc).__name__}).",
                policy=decision,
            )

        output, metadata = _limit_output(
            execution.output,
            execution.metadata,
            config.execution.max_output_chars,
        )
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status=ToolStatus.EXECUTED,
            output=output,
            policy=decision,
            metadata=metadata,
        )

    def _record(self, decision: PolicyDecision) -> None:
        self._decisions.append(decision)
        if self._decision_sink is not None:
            self._decision_sink.record(decision)


def _precondition_decision(
    call: FunctionCall,
    role: ToolRole,
    *,
    reason: str,
    rule: str,
) -> PolicyDecision:
    serialized = json.dumps(
        {"tool": call.name, "role": role.value, "arguments": call.arguments},
        sort_keys=True,
        default=str,
    )
    return PolicyDecision(
        outcome=PolicyOutcome.DENIED,
        reason=reason,
        rule=rule,
        role=role.value,
        arguments={},
        fingerprint=hashlib.sha256(serialized.encode()).hexdigest(),
    )


def _failure(
    call: FunctionCall,
    *,
    status: ToolStatus,
    code: str,
    message: str,
    policy: PolicyDecision,
) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        tool_name=call.name,
        status=status,
        error=ToolError(code=code, message=message),
        policy=policy,
    )


def _limit_output(
    output: str,
    metadata: dict[str, object],
    limit: int,
) -> tuple[str, dict[str, object]]:
    original_length = len(output)
    truncated = original_length > limit
    limited = output[:limit]
    enriched = {
        **metadata,
        "output_chars": len(limited),
        "original_output_chars": original_length,
        "truncated": truncated,
    }
    return limited, enriched
