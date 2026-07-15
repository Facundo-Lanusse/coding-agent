"""Contained filesystem tools with bounded reads and atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path, PurePosixPath

from pydantic import Field, model_validator

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

READ_ROLES = frozenset(
    {
        ToolRole.EXPLORER,
        ToolRole.RESEARCHER,
        ToolRole.IMPLEMENTER,
        ToolRole.TESTER,
        ToolRole.REVIEWER,
    }
)
DISCOVERY_ROLES = frozenset(
    {
        ToolRole.EXPLORER,
        ToolRole.IMPLEMENTER,
        ToolRole.TESTER,
        ToolRole.REVIEWER,
    }
)


class ReadFileParameters(ToolParameters):
    path: str = Field(min_length=1)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> ReadFileParameters:
        if (
            self.start_line is not None
            and self.end_line is not None
            and self.end_line < self.start_line
        ):
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class ReadFileTool(StructuredTool[ReadFileParameters]):
    def __init__(self) -> None:
        super().__init__(
            name="read_file",
            description="Read a UTF-8 text file inside the authorized workspace.",
            parameters_model=ReadFileParameters,
            permissions=ToolPermissions(
                kind=PermissionKind.READ,
                allowed_roles=READ_ROLES,
                path_argument="path",
            ),
        )

    def _execute(
        self,
        context: ToolContext,
        parameters: ReadFileParameters,
    ) -> ToolExecution:
        path = context.paths.resolve_read(parameters.path)
        if not path.is_file():
            raise ToolExecutionFailure("file_not_found", "Requested path is not a file.")

        content = _read_utf8(path, context.config.execution.max_read_bytes)
        lines = content.splitlines(keepends=True)
        start = (parameters.start_line or 1) - 1
        end = parameters.end_line
        selected = "".join(lines[start:end])
        return ToolExecution(
            output=selected,
            metadata={
                "path": path.relative_to(context.workspace).as_posix(),
                "bytes": len(content.encode("utf-8")),
                "start_line": start + 1,
                "end_line": min(end or len(lines), len(lines)),
            },
        )


class WriteFileParameters(ToolParameters):
    path: str = Field(min_length=1)
    content: str
    overwrite: bool = True


class WriteFileTool(StructuredTool[WriteFileParameters]):
    def __init__(self) -> None:
        super().__init__(
            name="write_file",
            description="Atomically write UTF-8 text inside the authorized workspace.",
            parameters_model=WriteFileParameters,
            permissions=ToolPermissions(
                kind=PermissionKind.WRITE,
                allowed_roles=frozenset({ToolRole.IMPLEMENTER}),
                path_argument="path",
                sensitive_arguments=frozenset({"content"}),
                mutates_workspace=True,
            ),
        )

    def _execute(
        self,
        context: ToolContext,
        parameters: WriteFileParameters,
    ) -> ToolExecution:
        path = context.paths.resolve_write(parameters.path)
        parent = path.parent
        if not parent.is_dir():
            raise ToolExecutionFailure(
                "parent_not_found",
                "The target parent directory does not exist.",
            )
        if path.exists() and not path.is_file():
            raise ToolExecutionFailure("invalid_write_target", "Write target is not a file.")
        if path.exists() and not parameters.overwrite:
            raise ToolExecutionFailure("file_exists", "Write target already exists.")

        encoded = parameters.content.encode("utf-8")
        if len(encoded) > context.config.execution.max_read_bytes:
            raise ToolExecutionFailure(
                "write_too_large",
                "Write content exceeds the configured size limit.",
            )

        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(parameters.content)
                stream.flush()
                os.fsync(stream.fileno())
            if path.exists():
                os.chmod(temporary, path.stat().st_mode)
            os.replace(temporary, path)
            temporary = None
        except OSError as exc:
            raise ToolExecutionFailure(
                "atomic_write_failed",
                f"Atomic write failed ({type(exc).__name__}).",
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

        return ToolExecution(
            output=path.relative_to(context.workspace).as_posix(),
            metadata={"bytes_written": len(encoded), "atomic": True},
        )


class ListFilesParameters(ToolParameters):
    path: str = "."
    pattern: str = "*"
    recursive: bool = True
    max_entries: int = Field(default=200, ge=1)


class ListFilesTool(StructuredTool[ListFilesParameters]):
    def __init__(self) -> None:
        super().__init__(
            name="list_files",
            description="List allowed files and directories below a workspace path.",
            parameters_model=ListFilesParameters,
            permissions=ToolPermissions(
                kind=PermissionKind.READ,
                allowed_roles=DISCOVERY_ROLES,
                path_argument="path",
            ),
        )

    def _execute(
        self,
        context: ToolContext,
        parameters: ListFilesParameters,
    ) -> ToolExecution:
        root = context.paths.resolve_read(parameters.path)
        if not root.exists():
            raise ToolExecutionFailure("path_not_found", "List path does not exist.")

        limit = min(parameters.max_entries, context.config.execution.max_list_entries)
        entries: list[str] = []
        if root.is_file():
            relative = root.relative_to(context.workspace).as_posix()
            if _matches(relative, parameters.pattern):
                entries.append(relative)
        else:
            for path in _iter_allowed_paths(context, root, recursive=parameters.recursive):
                relative = path.relative_to(context.workspace).as_posix()
                if _matches(relative, parameters.pattern):
                    entries.append(relative)
                    if len(entries) >= limit:
                        break

        entries.sort()
        return ToolExecution(
            output="\n".join(entries),
            metadata={"count": len(entries), "entry_limit": limit},
        )


class SearchFilesParameters(ToolParameters):
    query: str = Field(min_length=1)
    path: str = "."
    pattern: str = "*"
    case_sensitive: bool = False
    max_results: int = Field(default=100, ge=1)


class SearchFilesTool(StructuredTool[SearchFilesParameters]):
    def __init__(self) -> None:
        super().__init__(
            name="search_files",
            description="Search for a literal string in allowed UTF-8 workspace files.",
            parameters_model=SearchFilesParameters,
            permissions=ToolPermissions(
                kind=PermissionKind.READ,
                allowed_roles=DISCOVERY_ROLES,
                path_argument="path",
            ),
        )

    def _execute(
        self,
        context: ToolContext,
        parameters: SearchFilesParameters,
    ) -> ToolExecution:
        root = context.paths.resolve_read(parameters.path)
        if not root.exists():
            raise ToolExecutionFailure("path_not_found", "Search path does not exist.")

        limit = min(parameters.max_results, context.config.execution.max_list_entries)
        matches: list[dict[str, object]] = []
        candidates = (root,) if root.is_file() else _iter_allowed_files(context, root)
        needle = parameters.query if parameters.case_sensitive else parameters.query.casefold()
        for path in candidates:
            relative = path.relative_to(context.workspace).as_posix()
            if not _matches(relative, parameters.pattern):
                continue
            try:
                content = _read_utf8(path, context.config.execution.max_read_bytes)
            except ToolExecutionFailure:
                continue
            for line_number, line in enumerate(content.splitlines(), start=1):
                haystack = line if parameters.case_sensitive else line.casefold()
                if needle in haystack:
                    matches.append({"path": relative, "line": line_number, "text": line})
                    if len(matches) >= limit:
                        break
            if len(matches) >= limit:
                break

        return ToolExecution(
            output=json.dumps(matches, ensure_ascii=False),
            metadata={"count": len(matches), "result_limit": limit},
        )


def _read_utf8(path: Path, limit: int) -> str:
    try:
        with path.open("rb") as stream:
            payload = stream.read(limit + 1)
    except OSError as exc:
        raise ToolExecutionFailure(
            "file_read_failed",
            f"File read failed ({type(exc).__name__}).",
        ) from exc
    if len(payload) > limit:
        raise ToolExecutionFailure(
            "file_too_large",
            "File exceeds the configured read limit.",
        )
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ToolExecutionFailure("binary_file", "File is not valid UTF-8 text.") from exc


def _iter_allowed_paths(
    context: ToolContext,
    root: Path,
    *,
    recursive: bool,
) -> list[Path]:
    discovered: list[Path] = []
    try:
        for current, directories, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            allowed_directories: list[str] = []
            for name in sorted(directories):
                candidate = current_path / name
                if candidate.is_symlink() or not context.paths.is_read_allowed(candidate):
                    continue
                allowed_directories.append(name)
                discovered.append(candidate)
            directories[:] = allowed_directories if recursive else []
            for name in sorted(files):
                candidate = current_path / name
                if candidate.is_symlink() or not context.paths.is_read_allowed(candidate):
                    continue
                discovered.append(candidate)
            if not recursive:
                break
    except OSError as exc:
        raise ToolExecutionFailure(
            "directory_list_failed",
            f"Directory listing failed ({type(exc).__name__}).",
        ) from exc
    return discovered


def _iter_allowed_files(context: ToolContext, root: Path) -> list[Path]:
    return [path for path in _iter_allowed_paths(context, root, recursive=True) if path.is_file()]


def _matches(path: str, pattern: str) -> bool:
    candidate = PurePosixPath(path)
    return candidate.match(pattern) or (pattern.startswith("**/") and candidate.match(pattern[3:]))
