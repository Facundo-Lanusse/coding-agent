from __future__ import annotations

from collections.abc import Iterator

import pytest

from coding_agent.tools import (
    DuplicateToolError,
    PermissionKind,
    StructuredTool,
    ToolContext,
    ToolExecution,
    ToolParameters,
    ToolPermissions,
    ToolRegistry,
    ToolRole,
    build_default_registry,
)


class PluginParameters(ToolParameters):
    pass


class PluginTool(StructuredTool[PluginParameters]):
    def __init__(self) -> None:
        super().__init__(
            name="plugin_tool",
            description="Tool supplied without changing registry internals.",
            parameters_model=PluginParameters,
            permissions=ToolPermissions(
                kind=PermissionKind.REPOSITORY,
                allowed_roles=frozenset({ToolRole.EXPLORER}),
            ),
        )

    def _execute(
        self,
        context: ToolContext,
        parameters: PluginParameters,
    ) -> ToolExecution:
        return ToolExecution(output="plugin")


class FakeEntryPoint:
    name = "test-plugin"

    def load(self) -> object:
        return PluginTool


class FakeEntryPoints:
    def select(self, *, group: str) -> Iterator[FakeEntryPoint]:
        assert group == "coding_agent.tools"
        return iter((FakeEntryPoint(),))


def test_default_registry_contains_seven_structured_tools() -> None:
    registry = build_default_registry()

    names = {tool.spec.definition.name for tool in registry.all()}

    assert names == {
        "read_file",
        "write_file",
        "list_files",
        "run_command",
        "search_files",
        "repository_status",
        "web_search",
    }
    for tool in registry.all():
        assert tool.spec.definition.description
        assert tool.spec.definition.parameters["type"] == "object"
        assert tool.spec.permissions.allowed_roles


def test_default_tool_schemas_are_openai_strict_compatible() -> None:
    registry = build_default_registry()

    for tool in registry.all():
        definition = tool.spec.definition
        assert definition.strict is True
        _assert_strict_objects(definition.parameters)

    read_schema = registry.get("read_file").spec.definition.parameters
    read_properties = read_schema["properties"]
    assert isinstance(read_properties, dict)
    start_line = read_properties["start_line"]
    assert isinstance(start_line, dict)
    assert "default" not in start_line
    assert {variant.get("type") for variant in start_line["anyOf"]} == {
        "integer",
        "null",
    }


def test_registry_accepts_extension_and_rejects_duplicate() -> None:
    registry = ToolRegistry()
    tool = PluginTool()

    registry.register(tool)

    assert registry.get("plugin_tool") is tool
    with pytest.raises(DuplicateToolError):
        registry.register(PluginTool())


def test_registry_discovers_explicit_entry_point_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "coding_agent.tools.registry.metadata.entry_points",
        lambda: FakeEntryPoints(),
    )
    registry = ToolRegistry()

    count = registry.discover()

    assert count == 1
    assert registry.get("plugin_tool").spec.definition.name == "plugin_tool"


def _assert_strict_objects(value: object) -> None:
    if isinstance(value, dict):
        assert "default" not in value
        properties = value.get("properties")
        if isinstance(properties, dict):
            assert value.get("additionalProperties") is False
            assert value.get("required") == list(properties)
        for child in value.values():
            _assert_strict_objects(child)
    elif isinstance(value, list):
        for child in value:
            _assert_strict_objects(child)
