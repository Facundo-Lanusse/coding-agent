"""Structured tools and their extensible registry."""

from coding_agent.tools.base import (
    PermissionKind,
    StructuredTool,
    Tool,
    ToolContext,
    ToolExecution,
    ToolExecutionFailure,
    ToolInputError,
    ToolParameters,
    ToolPermissions,
    ToolRole,
    ToolSpec,
)
from coding_agent.tools.registry import (
    DuplicateToolError,
    ToolDiscoveryError,
    ToolRegistry,
    ToolRegistryError,
    UnknownToolError,
    build_default_registry,
)
from coding_agent.tools.tavily import (
    TavilyConfigurationError,
    TavilySearchBudgetError,
    TavilyWebSearchProvider,
)

__all__ = [
    "DuplicateToolError",
    "PermissionKind",
    "StructuredTool",
    "TavilyConfigurationError",
    "TavilySearchBudgetError",
    "TavilyWebSearchProvider",
    "Tool",
    "ToolContext",
    "ToolDiscoveryError",
    "ToolExecution",
    "ToolExecutionFailure",
    "ToolInputError",
    "ToolParameters",
    "ToolPermissions",
    "ToolRegistry",
    "ToolRegistryError",
    "ToolRole",
    "ToolSpec",
    "UnknownToolError",
    "build_default_registry",
]
