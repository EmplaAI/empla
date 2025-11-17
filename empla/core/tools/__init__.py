"""
empla.core.tools - Tool Execution System

Custom tool execution layer for autonomous action execution.

Design Decision (ADR-009): We build a custom tool execution layer rather than
using agent frameworks (Agno, LangGraph) because:
1. Our tool patterns are simple (direct API calls)
2. We already have complex orchestration (BDI + IntentionStack)
3. Custom implementation gives perfect BDI integration
4. Zero framework lock-in, maximum flexibility

Architecture:
- base.py: Tool, ToolResult, ToolExecutor protocol, ToolCapability
- executor.py: ToolExecutionEngine with retry logic and error handling
- registry.py: ToolRegistry for managing available tools
- capabilities/: Concrete tool implementations (email, calendar, research, etc.)

Example Usage:
    >>> from empla.core.tools import ToolExecutionEngine, ToolRegistry, Tool
    >>> from empla.core.tools.capabilities.email import SendEmailTool
    >>>
    >>> # Register tools
    >>> registry = ToolRegistry()
    >>> email_tool = Tool(name="send_email", ...)
    >>> registry.register_tool(email_tool, SendEmailTool())
    >>>
    >>> # Execute tool
    >>> engine = ToolExecutionEngine()
    >>> tool = registry.get_tool_by_name("send_email")
    >>> impl = registry.get_implementation(tool.tool_id)
    >>> result = await engine.execute(
    ...     tool=tool,
    ...     implementation=impl,
    ...     params={"to": "user@example.com", "subject": "Hello"}
    ... )
    >>>
    >>> if result.success:
    ...     print(f"Success: {result.output}")
    ... else:
    ...     print(f"Failed: {result.error}")
"""

from .base import Tool, ToolCapability, ToolExecutor, ToolImplementation, ToolResult
from .executor import ToolExecutionEngine
from .registry import ToolRegistry

__all__ = [
    # Base types
    "Tool",
    "ToolResult",
    "ToolExecutor",
    "ToolImplementation",
    "ToolCapability",
    # Implementations
    "ToolExecutionEngine",
    "ToolRegistry",
]
