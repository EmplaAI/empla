"""
Tests for empla.core.tools.router - ToolRouter unified interface.
"""

from uuid import uuid4

import pytest

from empla.core.tools.base import Tool
from empla.core.tools.decorator import tool
from empla.core.tools.registry import ToolRegistry
from empla.core.tools.router import ToolRouter


@pytest.fixture
def employee_id():
    return uuid4()


@pytest.fixture
def tool_registry():
    return ToolRegistry()


@pytest.fixture
def router(tool_registry):
    return ToolRouter(tool_registry)


# ============================================================================
# Schema aggregation tests
# ============================================================================


class TestGetAllToolSchemas:
    def test_empty_schemas(self, router, employee_id):
        schemas = router.get_all_tool_schemas(employee_id)
        assert schemas == []

    def test_standalone_tools_only(self, router, tool_registry, employee_id):
        # Register a standalone tool
        t = Tool(
            name="web_search",
            description="Search the web",
            parameters_schema={"type": "object", "properties": {"q": {"type": "string"}}},
        )

        class Impl:
            async def _execute(self, params):
                return []

        tool_registry.register_tool(t, Impl())

        schemas = router.get_all_tool_schemas(employee_id)
        assert len(schemas) == 1
        assert schemas[0]["name"] == "web_search"


# ============================================================================
# Tool call routing tests
# ============================================================================


class TestExecuteToolCall:
    async def test_routes_to_standalone_tool(self, router, tool_registry, employee_id):
        @tool(name="greet", description="Greet someone")
        async def greet(name: str) -> str:
            return f"Hello, {name}!"

        from empla.core.tools.decorator import get_tool_meta

        meta = get_tool_meta(greet)
        tool_registry.register_tool(meta["tool"], meta["implementation"])

        result = await router.execute_tool_call(employee_id, "greet", {"name": "World"})
        assert result.success is True
        assert result.output == "Hello, World!"

    async def test_standalone_takes_priority(self, router, tool_registry, employee_id):
        # Register standalone tool with a dotted name
        @tool(name="custom.action", description="Custom action")
        async def custom_action() -> str:
            return "standalone"

        from empla.core.tools.decorator import get_tool_meta

        meta = get_tool_meta(custom_action)
        tool_registry.register_tool(meta["tool"], meta["implementation"])

        result = await router.execute_tool_call(employee_id, "custom.action", {})
        assert result.success is True
        assert result.output == "standalone"

    async def test_standalone_tool_error(self, router, tool_registry, employee_id):
        t = Tool(
            name="failing_tool",
            description="Always fails",
            parameters_schema={"type": "object", "properties": {}},
        )

        class FailImpl:
            async def _execute(self, params):
                raise ValueError("Something went wrong")

        tool_registry.register_tool(t, FailImpl())

        result = await router.execute_tool_call(employee_id, "failing_tool", {})
        assert result.success is False
        assert "ValueError" in result.error
        assert "Something went wrong" in result.error

    async def test_unknown_tool_returns_error(self, router, employee_id):
        result = await router.execute_tool_call(employee_id, "nonexistent.tool", {})
        assert result.success is False
        assert "Unknown tool" in result.error

    async def test_tool_with_no_implementation(self, router, tool_registry, employee_id):
        """Tool exists in registry but implementation is missing."""
        t = Tool(
            name="orphan_tool",
            description="Tool with no impl",
            parameters_schema={"type": "object", "properties": {}},
        )

        class DummyImpl:
            async def _execute(self, params):
                return None

        # Register, then remove the implementation manually
        tool_registry.register_tool(t, DummyImpl())
        del tool_registry._implementations[t.tool_id]

        result = await router.execute_tool_call(employee_id, "orphan_tool", {})
        assert result.success is False
        assert "no implementation" in result.error


# ============================================================================
# Misc tests
# ============================================================================


class TestToolRouterMisc:
    def test_repr(self, router):
        r = repr(router)
        assert "ToolRouter" in r
        assert "standalone_tools=" in r

    def test_default_tool_registry(self):
        # Should create default ToolRegistry if none provided
        router = ToolRouter()
        assert router._tool_registry is not None
        assert len(router._tool_registry) == 0

    def test_get_enabled_capabilities(self, router, employee_id):
        caps = router.get_enabled_capabilities(employee_id)
        assert caps == []
