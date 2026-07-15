"""Bounded subprocess execution using argv and a fixed workspace cwd."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import Field, field_validator

from coding_agent.tools.base import (
    PermissionKind,
    StructuredTool,
    ToolContext,
    ToolExecution,
    ToolExecutionFailure,
    ToolParameters,
    ToolPermissions,
    ToolRole,
)


class CommandRunner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        """Run argv without a shell and return captured text output."""


class SubprocessRunner:
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        for key in (
            "BASH_ENV",
            "ENV",
            "GIT_EXTERNAL_DIFF",
            "GIT_SSH",
            "GIT_SSH_COMMAND",
            "PYTHONSTARTUP",
        ):
            environment.pop(key, None)
        environment.update(
            {
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PAGER": "cat",
                "PAGER": "cat",
            }
        )
        command = list(argv)
        if command and Path(command[0]).name.casefold() == "git":
            command[1:1] = ["-c", "core.fsmonitor=false"]
        return subprocess.run(
            command,
            cwd=cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
            shell=False,
        )


class RunCommandParameters(ToolParameters):
    argv: list[str] = Field(min_length=1)
    timeout_seconds: int | None = Field(default=None, gt=0)

    @field_validator("argv")
    @classmethod
    def validate_argv(cls, value: list[str]) -> list[str]:
        if any(not item or "\x00" in item or "\n" in item or "\r" in item for item in value):
            raise ValueError("argv entries must be non-empty and contain no control lines")
        return value


class RunCommandTool(StructuredTool[RunCommandParameters]):
    def __init__(self, runner: CommandRunner | None = None) -> None:
        super().__init__(
            name="run_command",
            description="Run an allowlisted argv command with fixed cwd and timeout.",
            parameters_model=RunCommandParameters,
            permissions=ToolPermissions(
                kind=PermissionKind.COMMAND,
                allowed_roles=frozenset({ToolRole.EXPLORER, ToolRole.TESTER}),
                command_argument="argv",
                sensitive_arguments=frozenset({"stdin"}),
            ),
        )
        self._runner = runner or SubprocessRunner()

    def _execute(
        self,
        context: ToolContext,
        parameters: RunCommandParameters,
    ) -> ToolExecution:
        configured_timeout = context.config.execution.timeout_seconds
        timeout = min(parameters.timeout_seconds or configured_timeout, configured_timeout)
        try:
            completed = self._runner.run(
                parameters.argv,
                cwd=context.workspace,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            output = _combine_output(_as_text(exc.stdout), _as_text(exc.stderr))
            raise ToolExecutionFailure(
                "command_timeout",
                f"Command exceeded the {timeout} second timeout.",
                output=output,
                retryable=True,
                metadata={"timeout_seconds": timeout, "timed_out": True},
            ) from exc
        except FileNotFoundError as exc:
            raise ToolExecutionFailure(
                "command_not_found",
                "Command executable was not found.",
            ) from exc
        except OSError as exc:
            raise ToolExecutionFailure(
                "command_start_failed",
                f"Command could not start ({type(exc).__name__}).",
            ) from exc

        output = _combine_output(completed.stdout, completed.stderr)
        metadata: dict[str, object] = {
            "exit_code": completed.returncode,
            "timeout_seconds": timeout,
            "timed_out": False,
            "cwd": ".",
        }
        if completed.returncode != 0:
            raise ToolExecutionFailure(
                "command_failed",
                f"Command exited with code {completed.returncode}.",
                output=output,
                metadata=metadata,
            )
        return ToolExecution(output=output, metadata=metadata)


def _combine_output(stdout: str, stderr: str) -> str:
    if stdout and stderr:
        return f"{stdout}\n[stderr]\n{stderr}"
    return stdout or stderr


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
