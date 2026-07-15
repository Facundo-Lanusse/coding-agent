"""Path and command authorization evaluated before every tool effect."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from coding_agent.config import AgentConfig, resolve_workspace
from coding_agent.models import PolicyDecision, PolicyOutcome
from coding_agent.policies.redaction import redact_arguments
from coding_agent.tools.base import PermissionKind, Tool, ToolRole


class PolicyViolation(Exception):
    def __init__(self, code: str, message: str, *, rule: str) -> None:
        self.code = code
        self.rule = rule
        super().__init__(message)


class WorkspaceGuard:
    """Canonical containment and glob enforcement for one config snapshot."""

    def __init__(self, config: AgentConfig, config_path: str | Path) -> None:
        self.workspace = resolve_workspace(config, config_path)
        self._read_deny = config.permissions.read.deny
        self._write_deny = config.permissions.write.deny

    def resolve_read(self, value: str) -> Path:
        return self._resolve(value, patterns=self._read_deny, access="read")

    def resolve_write(self, value: str) -> Path:
        return self._resolve(value, patterns=self._write_deny, access="write")

    def is_read_allowed(self, path: Path) -> bool:
        try:
            self.resolve_read(str(path))
        except PolicyViolation:
            return False
        return True

    def _resolve(self, value: str, *, patterns: tuple[str, ...], access: str) -> Path:
        if not value or "\x00" in value:
            raise PolicyViolation(
                "invalid_path",
                "Path must be a non-empty string without null bytes.",
                rule=f"permissions.{access}.path",
            )

        raw = Path(value)
        if ".." in raw.parts:
            raise PolicyViolation(
                "path_traversal",
                "Parent traversal is not allowed.",
                rule=f"permissions.{access}.containment",
            )

        candidate = raw if raw.is_absolute() else self.workspace / raw
        resolved = candidate.resolve(strict=False)
        try:
            relative = resolved.relative_to(self.workspace)
        except ValueError as exc:
            raise PolicyViolation(
                "path_outside_workspace",
                "Resolved path is outside the configured workspace.",
                rule=f"permissions.{access}.containment",
            ) from exc

        relative_text = relative.as_posix() or "."
        if _is_secret_path(relative):
            raise PolicyViolation(
                "sensitive_path_denied",
                "Sensitive paths are denied independently of configured globs.",
                rule="permissions.secrets",
            )
        for pattern in patterns:
            if _glob_matches(relative_text, pattern):
                raise PolicyViolation(
                    "path_pattern_denied",
                    f"Path is denied by the configured {access} policy.",
                    rule=f"permissions.{access}.deny:{pattern}",
                )
        return resolved


class PolicyEngine:
    """Evaluate role, resource and command rules without executing a tool."""

    def evaluate(
        self,
        *,
        tool: Tool,
        parameters: BaseModel,
        config: AgentConfig,
        config_path: str | Path,
        role: ToolRole,
    ) -> tuple[PolicyDecision, WorkspaceGuard]:
        arguments = parameters.model_dump(mode="json")
        permissions = tool.spec.permissions
        sanitized = redact_arguments(
            arguments,
            sensitive_keys=permissions.sensitive_arguments,
        )
        digest = _config_digest(config)
        fingerprint = _fingerprint(
            tool.spec.definition.name,
            role,
            arguments,
            digest,
        )
        guard = WorkspaceGuard(config, config_path)

        if role not in permissions.allowed_roles:
            return (
                _decision(
                    PolicyOutcome.DENIED,
                    "The role is not allowed to use this tool.",
                    "roles.tool_permissions",
                    role,
                    sanitized,
                    digest,
                    fingerprint,
                ),
                guard,
            )

        try:
            if permissions.kind is PermissionKind.READ and permissions.path_argument:
                guard.resolve_read(_string_argument(arguments, permissions.path_argument))
            elif permissions.kind is PermissionKind.WRITE and permissions.path_argument:
                guard.resolve_write(_string_argument(arguments, permissions.path_argument))
        except PolicyViolation as exc:
            return (
                _decision(
                    PolicyOutcome.DENIED,
                    str(exc),
                    exc.rule,
                    role,
                    sanitized,
                    digest,
                    fingerprint,
                ),
                guard,
            )

        if permissions.kind is PermissionKind.COMMAND:
            return (
                self._evaluate_command(
                    arguments=arguments,
                    sanitized=sanitized,
                    config=config,
                    role=role,
                    digest=digest,
                    fingerprint=fingerprint,
                    argument_name=permissions.command_argument or "argv",
                ),
                guard,
            )

        return (
            _decision(
                PolicyOutcome.ALLOWED,
                "Tool call is allowed by role and resource policies.",
                "policy.allowed",
                role,
                sanitized,
                digest,
                fingerprint,
            ),
            guard,
        )

    def _evaluate_command(
        self,
        *,
        arguments: dict[str, object],
        sanitized: dict[str, object],
        config: AgentConfig,
        role: ToolRole,
        digest: str,
        fingerprint: str,
        argument_name: str,
    ) -> PolicyDecision:
        argv = _argv_argument(arguments, argument_name)
        normalized = _normalize_argv(argv)

        dangerous_rule = _built_in_dangerous_rule(normalized)
        if dangerous_rule is not None:
            return _decision(
                PolicyOutcome.DENIED,
                "Command is denied by a non-overridable safety rule.",
                dangerous_rule,
                role,
                sanitized,
                digest,
                fingerprint,
            )

        for rule in config.commands.deny:
            if _command_matches(normalized, rule):
                return _decision(
                    PolicyOutcome.DENIED,
                    "Command is denied by configuration.",
                    f"commands.deny:{rule}",
                    role,
                    sanitized,
                    digest,
                    fingerprint,
                )

        for rule in config.commands.require_approval:
            if _command_matches(normalized, rule):
                return _decision(
                    PolicyOutcome.REQUIRES_APPROVAL,
                    "Command requires explicit human approval.",
                    f"commands.require_approval:{rule}",
                    role,
                    sanitized,
                    digest,
                    fingerprint,
                )

        allowed = config.commands.allow_by_role.for_role(role.value)
        if any(_command_matches(normalized, rule) for rule in allowed):
            return _decision(
                PolicyOutcome.ALLOWED,
                "Command matches the role-specific allowlist.",
                f"commands.allow_by_role.{role.value}",
                role,
                sanitized,
                digest,
                fingerprint,
            )

        return _decision(
            PolicyOutcome.DENIED,
            "Command is not present in the role-specific allowlist.",
            f"commands.allow_by_role.{role.value}",
            role,
            sanitized,
            digest,
            fingerprint,
        )


def _decision(
    outcome: PolicyOutcome,
    reason: str,
    rule: str,
    role: ToolRole,
    arguments: dict[str, object],
    config_digest: str,
    fingerprint: str,
) -> PolicyDecision:
    return PolicyDecision(
        outcome=outcome,
        reason=reason,
        rule=rule,
        role=role.value,
        arguments=arguments,
        config_digest=config_digest,
        fingerprint=fingerprint,
    )


def _config_digest(config: AgentConfig) -> str:
    serialized = config.model_dump_json(exclude_none=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _fingerprint(
    tool_name: str,
    role: ToolRole,
    arguments: dict[str, object],
    config_digest: str,
) -> str:
    payload = json.dumps(
        {
            "tool": tool_name,
            "role": role.value,
            "arguments": arguments,
            "config_digest": config_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _string_argument(arguments: dict[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str):
        raise PolicyViolation(
            "invalid_path_argument",
            "Path argument must be a string.",
            rule="arguments.path",
        )
    return value


def _argv_argument(arguments: dict[str, object], name: str) -> list[str]:
    value = arguments.get(name)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise PolicyViolation(
            "invalid_command_arguments",
            "Command argv must be a non-empty list of strings.",
            rule="arguments.argv",
        )
    return value


def _normalize_argv(argv: list[str]) -> tuple[str, ...]:
    executable = Path(argv[0]).name.casefold()
    if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", executable):
        executable = "python"
    return (executable, *(item.casefold() for item in argv[1:]))


def _command_matches(argv: tuple[str, ...], rule: str) -> bool:
    try:
        tokens = shlex.split(rule)
    except ValueError:
        return False
    if not tokens:
        return False
    normalized = _normalize_argv(tokens)
    return len(argv) >= len(normalized) and argv[: len(normalized)] == normalized


def _built_in_dangerous_rule(argv: tuple[str, ...]) -> str | None:
    executable = argv[0]
    if executable in {"sudo", "shutdown", "reboot", "mkfs", "su"}:
        return "commands.builtin.privileged"
    if executable in {"sh", "bash", "zsh", "dash", "fish", "pwsh", "powershell", "cmd"}:
        return "commands.builtin.shell_interpreter"
    if executable == "git" and "push" in argv[1:]:
        return "commands.builtin.git_push"
    if executable == "git" and "reset" in argv[1:] and "--hard" in argv[1:]:
        return "commands.builtin.git_hard_reset"
    if executable == "rm":
        flags = "".join(item.lstrip("-") for item in argv[1:] if item.startswith("-"))
        if "r" in flags and "f" in flags:
            return "commands.builtin.rm_recursive_force"
    if executable == "find" and any(
        item in {"-delete", "-exec", "-execdir", "-fls", "-fprint", "-ok", "-okdir"}
        for item in argv[1:]
    ):
        return "commands.builtin.find_effect"
    if executable == "rg" and any(
        item == "--pre" or item.startswith("--pre=") for item in argv[1:]
    ):
        return "commands.builtin.rg_preprocessor"
    if executable == "git" and any(item in {"--ext-diff", "--textconv"} for item in argv[1:]):
        return "commands.builtin.git_external_helper"
    return None


def _is_secret_path(relative: Path) -> bool:
    for part in relative.parts:
        lowered = part.casefold()
        if lowered == "secrets" or lowered == ".env" or lowered.startswith(".env."):
            return True
        if lowered.endswith((".pem", ".key")):
            return True
    return False


def _glob_matches(path: str, pattern: str) -> bool:
    candidate = PurePosixPath(path)
    if candidate.match(pattern):
        return True
    if pattern.startswith("**/") and candidate.match(pattern[3:]):
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        base = PurePosixPath(prefix)
        return candidate == base or candidate.is_relative_to(base)
    return False
