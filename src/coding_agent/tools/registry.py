"""Extensible registry and optional entry-point discovery for tools."""

from __future__ import annotations

from collections.abc import Iterable
from importlib import metadata

from coding_agent.tools.base import Tool, ToolRole
from coding_agent.tools.shell import CommandRunner
from coding_agent.tools.web import WebSearchProvider


class ToolRegistryError(Exception):
    code = "tool_registry_error"


class DuplicateToolError(ToolRegistryError):
    code = "duplicate_tool"


class UnknownToolError(ToolRegistryError):
    code = "unknown_tool"


class ToolDiscoveryError(ToolRegistryError):
    code = "tool_discovery_error"


class ToolRegistry:
    """Register project tools without coupling the harness to concrete classes."""

    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        self.register_many(tools)

    def register(self, tool: Tool) -> None:
        name = tool.spec.definition.name
        if name in self._tools:
            raise DuplicateToolError(f"Tool already registered: {name}.")
        self._tools[name] = tool

    def register_many(self, tools: Iterable[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise UnknownToolError(f"Unknown tool: {name}.") from exc

    def all(self) -> tuple[Tool, ...]:
        return tuple(self._tools[name] for name in sorted(self._tools))

    def for_role(self, role: ToolRole) -> tuple[Tool, ...]:
        return tuple(tool for tool in self.all() if role in tool.spec.permissions.allowed_roles)

    def discover(self, *, group: str = "coding_agent.tools") -> int:
        """Load explicitly requested plugin entry points from an isolated group."""

        discovered = metadata.entry_points().select(group=group)
        count = 0
        for entry_point in discovered:
            try:
                loaded = entry_point.load()
                candidate = loaded() if callable(loaded) else loaded
                tools = candidate if isinstance(candidate, Iterable) else (candidate,)
                for tool in tools:
                    if not isinstance(tool, Tool):
                        raise TypeError("entry point did not provide a Tool")
                    self.register(tool)
                    count += 1
            except Exception as exc:
                raise ToolDiscoveryError(
                    f"Cannot load tool entry point {entry_point.name}."
                ) from exc
        return count


def build_default_registry(
    *,
    command_runner: CommandRunner | None = None,
    web_provider: WebSearchProvider | None = None,
) -> ToolRegistry:
    """Compose all Phase 02 tools without importing them from the harness."""

    from coding_agent.tools.filesystem import (
        ListFilesTool,
        ReadFileTool,
        SearchFilesTool,
        WriteFileTool,
    )
    from coding_agent.tools.repository import RepositoryStatusTool
    from coding_agent.tools.shell import RunCommandTool
    from coding_agent.tools.web import WebSearchTool

    return ToolRegistry(
        (
            ReadFileTool(),
            WriteFileTool(),
            ListFilesTool(),
            RunCommandTool(command_runner),
            SearchFilesTool(),
            RepositoryStatusTool(command_runner),
            WebSearchTool(web_provider),
        )
    )
