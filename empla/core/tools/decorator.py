"""
empla.core.tools.decorator - @tool Decorator

Turn async functions into tools with auto-generated JSON schemas.

Example:
    >>> @tool(name="web_search", description="Search the web")
    ... async def web_search(query: str, max_results: int = 10) -> list[dict]:
    ...     ...
    >>>
    >>> # Collect all @tool-decorated functions from a module
    >>> tools = collect_tools(my_module)
"""

import inspect
import logging
import types
from collections.abc import Callable
from typing import Any, get_args, get_origin

from .base import Tool

logger = logging.getLogger(__name__)

# Attribute name stored on decorated functions
_TOOL_META_ATTR = "_tool_meta"


def _python_type_to_json_schema(annotation: Any) -> dict[str, Any]:
    """Map a Python type annotation to a JSON schema type descriptor.

    Handles: str, int, float, bool, list, dict, None, Optional, Union,
    and generic forms like list[str], dict[str, Any].
    """
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}

    origin = get_origin(annotation)
    args = get_args(annotation)

    # Handle Optional[X] (Union[X, None])
    if origin is types.UnionType:
        # Python 3.10+ X | Y syntax
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _python_type_to_json_schema(non_none[0])
        return {"type": "string"}

    # typing.Union / typing.Optional
    try:
        import typing

        if origin is typing.Union:
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return _python_type_to_json_schema(non_none[0])
            return {"type": "string"}
    except Exception:
        pass

    # list[X]
    if origin is list:
        schema: dict[str, Any] = {"type": "array"}
        if args:
            schema["items"] = _python_type_to_json_schema(args[0])
        return schema

    # dict[K, V]
    if origin is dict:
        return {"type": "object"}

    # Plain types
    type_map: dict[type, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        type(None): "null",
    }

    if isinstance(annotation, type) and annotation in type_map:
        return {"type": type_map[annotation]}

    return {"type": "string"}


def _build_parameters_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Build a JSON-schema-style parameters_schema from a function signature.

    Returns a dict compatible with OpenAI/Anthropic function-calling format:
    {"type": "object", "properties": {...}, "required": [...]}
    """
    sig = inspect.signature(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name == "self":
            continue

        prop = _python_type_to_json_schema(param.annotation)

        # Add description from docstring if available (future enhancement)
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            prop["default"] = param.default

        properties[name] = prop

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema


class _FuncToolImplementation:
    """Wraps an async function as a ToolImplementation."""

    def __init__(self, func: Callable[..., Any]) -> None:
        self._func = func

    async def _execute(self, params: dict[str, Any]) -> Any:
        return await self._func(**params)


def tool(
    name: str | None = None,
    description: str = "",
    category: str | None = None,
    tags: list[str] | None = None,
    required_capabilities: list[str] | None = None,
) -> Callable[..., Any]:
    """Decorator that turns an async function into a registered tool.

    Args:
        name: Tool name (defaults to function name)
        description: Human-readable description
        category: Optional category for grouping
        tags: Optional tags for discovery
        required_capabilities: Capabilities needed (usually empty for standalone tools)

    Returns:
        Decorator that attaches _tool_meta to the function

    Example:
        >>> @tool(name="web_search", description="Search the web for information")
        ... async def web_search(query: str, max_results: int = 10) -> list[dict]:
        ...     ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if not inspect.iscoroutinefunction(func):
            raise TypeError(f"@tool can only decorate async functions, got {func.__name__}")

        tool_name = name or func.__name__
        tool_desc = description or func.__doc__ or f"Tool: {tool_name}"

        parameters_schema = _build_parameters_schema(func)

        tool_model = Tool(
            name=tool_name,
            description=tool_desc,
            parameters_schema=parameters_schema,
            required_capabilities=required_capabilities or [],
            category=category,
            tags=tags or [],
        )

        impl = _FuncToolImplementation(func)

        # Store metadata on the function for later collection
        setattr(
            func,
            _TOOL_META_ATTR,
            {
                "tool": tool_model,
                "implementation": impl,
            },
        )

        return func

    return decorator


def get_tool_meta(func: Callable[..., Any]) -> dict[str, Any] | None:
    """Get tool metadata from a @tool-decorated function.

    Returns:
        Dict with 'tool' (Tool model) and 'implementation' (_FuncToolImplementation),
        or None if the function is not decorated with @tool.
    """
    return getattr(func, _TOOL_META_ATTR, None)


def collect_tools(module: types.ModuleType) -> list[dict[str, Any]]:
    """Find all @tool-decorated functions in a module.

    Args:
        module: Python module to scan

    Returns:
        List of dicts with 'tool' and 'implementation' keys

    Example:
        >>> import my_tools
        >>> tools = collect_tools(my_tools)
        >>> for t in tools:
        ...     registry.register_tool(t["tool"], t["implementation"])
    """
    results: list[dict[str, Any]] = []

    for attr_name in dir(module):
        obj = getattr(module, attr_name, None)
        if callable(obj):
            meta = get_tool_meta(obj)
            if meta is not None:
                results.append(meta)

    return results
