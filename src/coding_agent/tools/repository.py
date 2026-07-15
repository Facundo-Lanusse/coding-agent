"""Read-only repository inspection tools."""

from __future__ import annotations

import subprocess

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
from coding_agent.tools.shell import CommandRunner, SubprocessRunner


class RepositoryStatusParameters(ToolParameters):
    include_branch: bool = True


class RepositoryStatusTool(StructuredTool[RepositoryStatusParameters]):
    def __init__(self, runner: CommandRunner | None = None) -> None:
        super().__init__(
            name="repository_status",
            description="Return read-only git working-tree status for the workspace.",
            parameters_model=RepositoryStatusParameters,
            permissions=ToolPermissions(
                kind=PermissionKind.REPOSITORY,
                allowed_roles=frozenset(
                    {
                        ToolRole.EXPLORER,
                        ToolRole.IMPLEMENTER,
                        ToolRole.TESTER,
                        ToolRole.REVIEWER,
                    }
                ),
            ),
        )
        self._runner = runner or SubprocessRunner()

    def _execute(
        self,
        context: ToolContext,
        parameters: RepositoryStatusParameters,
    ) -> ToolExecution:
        argv = ["git", "status", "--short"]
        if parameters.include_branch:
            argv.append("--branch")
        try:
            completed = self._runner.run(
                argv,
                cwd=context.workspace,
                timeout=context.config.execution.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolExecutionFailure(
                "repository_status_timeout",
                "Repository status timed out.",
                retryable=True,
            ) from exc
        except OSError as exc:
            raise ToolExecutionFailure(
                "repository_status_failed",
                f"Repository status could not start ({type(exc).__name__}).",
            ) from exc
        output = completed.stdout or completed.stderr
        if completed.returncode != 0:
            raise ToolExecutionFailure(
                "repository_status_failed",
                f"Git status exited with code {completed.returncode}.",
                output=output,
                metadata={"exit_code": completed.returncode},
            )
        return ToolExecution(
            output=output,
            metadata={"exit_code": completed.returncode, "read_only": True},
        )
