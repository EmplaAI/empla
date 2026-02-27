"""
Tests for empla.core.tools.decorator - @tool decorator and collect_tools.
"""

import types
from typing import Any

import pytest

from empla.core.tools.decorator import (
    _build_parameters_schema,
    _python_type_to_json_schema,
    collect_tools,
    get_tool_meta,
    tool,
)

# ============================================================================
# Type mapping tests
# ============================================================================


class TestPythonTypeToJsonSchema:
    def test_str(self) -> None:
        assert _python_type_to_json_schema(str) == {"type": "string"}

    def test_int(self) -> None:
        assert _python_type_to_json_schema(int) == {"type": "integer"}

    def test_float(self) -> None:
        assert _python_type_to_json_schema(float) == {"type": "number"}

    def test_bool(self) -> None:
        assert _python_type_to_json_schema(bool) == {"type": "boolean"}

    def test_list(self) -> None:
        assert _python_type_to_json_schema(list) == {"type": "array"}

    def test_dict(self) -> None:
        assert _python_type_to_json_schema(dict) == {"type": "object"}

    def test_none_type(self) -> None:
        assert _python_type_to_json_schema(type(None)) == {"type": "null"}

    def test_list_str(self) -> None:
        result = _python_type_to_json_schema(list[str])
        assert result == {"type": "array", "items": {"type": "string"}}

    def test_list_int(self) -> None:
        result = _python_type_to_json_schema(list[int])
        assert result == {"type": "array", "items": {"type": "integer"}}

    def test_dict_str_any(self) -> None:
        result = _python_type_to_json_schema(dict[str, Any])
        assert result == {"type": "object"}

    def test_optional_str(self) -> None:
        # Python 3.10+ union syntax
        result = _python_type_to_json_schema(str | None)
        assert result == {"type": "string"}

    def test_empty_annotation(self) -> None:
        import inspect

        result = _python_type_to_json_schema(inspect.Parameter.empty)
        assert result == {"type": "string"}


# ============================================================================
# Schema building tests
# ============================================================================


class TestBuildParametersSchema:
    def test_simple_function(self) -> None:
        async def func(query: str, max_results: int = 10) -> None:
            pass

        schema = _build_parameters_schema(func)
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "max_results" in schema["properties"]
        assert schema["properties"]["query"] == {"type": "string"}
        assert schema["properties"]["max_results"] == {"type": "integer", "default": 10}
        assert schema["required"] == ["query"]

    def test_no_params(self) -> None:
        async def func() -> None:
            pass

        schema = _build_parameters_schema(func)
        assert schema["type"] == "object"
        assert schema["properties"] == {}
        assert "required" not in schema

    def test_all_required(self) -> None:
        async def func(a: str, b: int, c: bool) -> None:
            pass

        schema = _build_parameters_schema(func)
        assert set(schema["required"]) == {"a", "b", "c"}

    def test_all_optional(self) -> None:
        async def func(a: str = "hello", b: int = 5) -> None:
            pass

        schema = _build_parameters_schema(func)
        assert "required" not in schema

    def test_mixed_params(self) -> None:
        async def func(required_param: str, optional_param: int = 42) -> None:
            pass

        schema = _build_parameters_schema(func)
        assert schema["required"] == ["required_param"]
        assert schema["properties"]["optional_param"]["default"] == 42

    def test_list_param(self) -> None:
        async def func(items: list[str]) -> None:
            pass

        schema = _build_parameters_schema(func)
        assert schema["properties"]["items"] == {
            "type": "array",
            "items": {"type": "string"},
        }


# ============================================================================
# @tool decorator tests
# ============================================================================


class TestToolDecorator:
    def test_basic_decoration(self) -> None:
        @tool(name="test_tool", description="A test tool")
        async def my_tool(query: str) -> str:
            return f"result: {query}"

        meta = get_tool_meta(my_tool)
        assert meta is not None
        assert meta["tool"].name == "test_tool"
        assert meta["tool"].description == "A test tool"
        assert meta["implementation"] is not None

    def test_default_name_from_function(self) -> None:
        @tool(description="Auto-named tool")
        async def auto_named_tool(x: int) -> int:
            return x * 2

        meta = get_tool_meta(auto_named_tool)
        assert meta["tool"].name == "auto_named_tool"

    def test_description_from_docstring(self) -> None:
        @tool()
        async def documented_tool(x: int) -> int:
            """This tool is documented."""
            return x * 2

        meta = get_tool_meta(documented_tool)
        assert meta["tool"].description == "This tool is documented."

    def test_category_and_tags(self) -> None:
        @tool(name="categorized", description="test", category="research", tags=["web", "search"])
        async def categorized(q: str) -> str:
            return q

        meta = get_tool_meta(categorized)
        assert meta["tool"].category == "research"
        assert meta["tool"].tags == ["web", "search"]

    def test_schema_generation(self) -> None:
        @tool(name="search", description="Search something")
        async def search(query: str, limit: int = 10, exact: bool = False) -> list[dict]:
            return []

        meta = get_tool_meta(search)
        schema = meta["tool"].parameters_schema
        assert schema["type"] == "object"
        assert schema["properties"]["query"]["type"] == "string"
        assert schema["properties"]["limit"]["type"] == "integer"
        assert schema["properties"]["limit"]["default"] == 10
        assert schema["properties"]["exact"]["type"] == "boolean"
        assert schema["properties"]["exact"]["default"] is False
        assert schema["required"] == ["query"]

    def test_sync_function_raises(self) -> None:
        with pytest.raises(TypeError, match="async functions"):

            @tool(name="bad", description="sync")
            def sync_func(x: int) -> int:
                return x

    async def test_implementation_executes(self) -> None:
        @tool(name="adder", description="Add numbers")
        async def adder(a: int, b: int) -> int:
            return a + b

        meta = get_tool_meta(adder)
        result = await meta["implementation"]._execute({"a": 3, "b": 7})
        assert result == 10

    def test_no_meta_on_regular_function(self) -> None:
        async def regular() -> None:
            pass

        assert get_tool_meta(regular) is None


# ============================================================================
# collect_tools tests
# ============================================================================


class TestCollectTools:
    def test_collect_from_module(self) -> None:
        # Create a fake module with decorated functions
        mod = types.ModuleType("fake_tools")

        @tool(name="tool_a", description="Tool A")
        async def tool_a(x: str) -> str:
            return x

        @tool(name="tool_b", description="Tool B")
        async def tool_b(y: int) -> int:
            return y

        async def not_a_tool() -> None:
            pass

        mod.tool_a = tool_a
        mod.tool_b = tool_b
        mod.not_a_tool = not_a_tool
        mod.some_value = 42

        tools = collect_tools(mod)
        assert len(tools) == 2
        names = {t["tool"].name for t in tools}
        assert names == {"tool_a", "tool_b"}

    def test_collect_empty_module(self) -> None:
        mod = types.ModuleType("empty")
        tools = collect_tools(mod)
        assert tools == []


# ============================================================================
# Integration: decorator + ToolRegistry
# ============================================================================


class TestDecoratorWithRegistry:
    async def test_register_and_execute(self) -> None:
        from empla.core.tools.registry import ToolRegistry

        @tool(name="multiply", description="Multiply two numbers")
        async def multiply(a: int, b: int) -> int:
            return a * b

        meta = get_tool_meta(multiply)
        registry = ToolRegistry()
        registry.register_tool(meta["tool"], meta["implementation"])

        # Verify registration
        assert "multiply" in registry
        tool_obj = registry.get_tool_by_name("multiply")
        assert tool_obj is not None
        assert tool_obj.name == "multiply"

        # Verify schema generation for LLM
        schemas = registry.get_all_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "multiply"
        assert schemas[0]["description"] == "Multiply two numbers"
        assert "input_schema" in schemas[0]

        # Execute through registry
        impl = registry.get_implementation(tool_obj.tool_id)
        result = await impl._execute({"a": 6, "b": 7})
        assert result == 42
