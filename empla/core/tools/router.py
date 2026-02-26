"""
empla.core.tools.router - Unified Tool Router

Drop-in wrapper that combines CapabilityRegistry + ToolRegistry behind the same
interface the agentic execution loop already uses:
  - get_all_tool_schemas(employee_id)
  - execute_tool_call(employee_id, tool_name, arguments)
  - perceive_all(employee_id)

The loop code changes minimally — swap capability_registry for tool_router.
"""

import logging
from typing import Any
from uuid import UUID

from empla.capabilities.base import ActionResult, Observation
from empla.capabilities.registry import CapabilityRegistry

from .base import ToolImplementation
from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolRouter:
    """
    Unified interface that merges tools from CapabilityRegistry (heavyweight
    capabilities) and ToolRegistry (lightweight @tool functions + MCP tools).

    Provides the same interface the agentic loop calls:
    - get_all_tool_schemas(employee_id) -> list[dict]
    - execute_tool_call(employee_id, tool_name, arguments) -> ActionResult
    - perceive_all(employee_id) -> list[Observation]
    - get_enabled_capabilities(employee_id) -> list[str]

    Example:
        >>> router = ToolRouter(capability_registry, tool_registry)
        >>> schemas = router.get_all_tool_schemas(employee_id)
        >>> result = await router.execute_tool_call(employee_id, "web_search", {"query": "AI"})
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._capability_registry = capability_registry
        self._tool_registry = tool_registry if tool_registry is not None else ToolRegistry()

    def get_all_tool_schemas(self, employee_id: UUID) -> list[dict[str, Any]]:
        """Merge schemas from capabilities + standalone tools.

        Args:
            employee_id: Employee to collect schemas for

        Returns:
            Combined list of tool schemas for LLM function calling
        """
        # Capability tools (email.send_email, workspace.read_file, etc.)
        schemas = self._capability_registry.get_all_tool_schemas(employee_id)

        # Standalone tools (web_search, enrich_company, MCP tools, etc.)
        schemas.extend(self._tool_registry.get_all_tool_schemas())

        return schemas

    async def execute_tool_call(
        self, employee_id: UUID, tool_name: str, arguments: dict[str, Any]
    ) -> ActionResult:
        """Route tool call to the right source.

        Checks ToolRegistry first (standalone tools), then falls back to
        CapabilityRegistry (capability-based tools with dotted names).

        Args:
            employee_id: Employee executing the tool call
            tool_name: Tool name (e.g., "web_search" or "email.send_email")
            arguments: Tool call arguments

        Returns:
            ActionResult from execution
        """
        # Check standalone tool registry first
        tool = self._tool_registry.get_tool_by_name(tool_name)
        if tool is not None:
            impl = self._tool_registry.get_implementation(tool.tool_id)
            if impl is not None:
                return await self._execute_standalone_tool(tool_name, impl, arguments)

            logger.error(
                f"Tool '{tool_name}' found in registry but has no implementation",
                extra={"employee_id": str(employee_id), "tool_name": tool_name},
            )
            return ActionResult(
                success=False,
                error=f"Tool '{tool_name}' has no implementation",
            )

        # Fall back to capability registry (dotted names like "email.send_email")
        return await self._capability_registry.execute_tool_call(employee_id, tool_name, arguments)

    async def _execute_standalone_tool(
        self, tool_name: str, impl: ToolImplementation, arguments: dict[str, Any]
    ) -> ActionResult:
        """Execute a standalone tool and wrap result as ActionResult."""
        try:
            output = await impl._execute(arguments)
            return ActionResult(success=True, output=output)
        except Exception as e:
            logger.error(
                f"Standalone tool '{tool_name}' failed: {e}",
                exc_info=True,
                extra={"tool_name": tool_name},
            )
            return ActionResult(
                success=False,
                error=f"{type(e).__name__}: {e}",
            )

    async def perceive_all(self, employee_id: UUID) -> list[Observation]:
        """Delegate perception to capability registry.

        Standalone tools don't perceive — only capabilities do.
        """
        return await self._capability_registry.perceive_all(employee_id)

    def get_enabled_capabilities(self, employee_id: UUID) -> list[str]:
        """Delegate to capability registry."""
        return self._capability_registry.get_enabled_capabilities(employee_id)

    def __repr__(self) -> str:
        cap_count = len(self._capability_registry.get_registered_types())
        tool_count = len(self._tool_registry)
        return f"ToolRouter(capabilities={cap_count}, standalone_tools={tool_count})"
