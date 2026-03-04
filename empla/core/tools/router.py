"""
empla.core.tools.router - Unified Tool Router

Combines ToolRegistry + IntegrationRouters behind a single interface:
  - get_all_tool_schemas(employee_id)
  - execute_tool_call(employee_id, tool_name, arguments)
  - get_enabled_capabilities(employee_id)
"""

import logging
from typing import Any
from uuid import UUID

from empla.capabilities.base import ActionResult

from .base import ToolImplementation
from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class _IntegrationToolImpl:
    """Wraps an IntegrationRouter tool as a ToolImplementation."""

    def __init__(self, router: Any, tool_name: str) -> None:
        self._router = router
        self._tool_name = tool_name

    async def _execute(self, params: dict[str, Any]) -> Any:
        return await self._router.execute_tool(self._tool_name, params)


class ToolRouter:
    """
    Unified interface that merges tools from ToolRegistry (standalone @tool
    functions + MCP tools) and IntegrationRouters.

    Provides the interface the agentic loop calls:
    - get_all_tool_schemas(employee_id) -> list[dict]
    - execute_tool_call(employee_id, tool_name, arguments) -> ActionResult
    - get_enabled_capabilities(employee_id) -> list[str]

    Example:
        >>> router = ToolRouter()
        >>> router.register_integration(email_router)
        >>> schemas = router.get_all_tool_schemas(employee_id)
        >>> result = await router.execute_tool_call(employee_id, "email.send_email", {...})
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._tool_registry = tool_registry if tool_registry is not None else ToolRegistry()
        self._integrations: dict[str, Any] = {}

    def register_integration(self, router: Any) -> None:
        """Register all tools from an IntegrationRouter.

        Tools are registered in the ToolRegistry so they appear in
        get_all_tool_schemas() and can be executed via execute_tool_call().

        Args:
            router: IntegrationRouter instance with tool definitions.
        """
        from empla.core.tools.base import Tool

        for tool_info in router._tools:
            tool = Tool(
                name=tool_info["name"],
                description=tool_info["description"],
                parameters_schema=tool_info["schema"],
            )
            impl = _IntegrationToolImpl(router, tool_info["name"])
            self._tool_registry.register_tool(tool, impl)

        self._integrations[router.name] = router
        logger.info(
            f"Registered integration '{router.name}' with {len(router._tools)} tools",
            extra={"integration": router.name},
        )

    async def initialize_integrations(self, configs: dict[str, dict[str, Any]]) -> None:
        """Initialize all registered integrations with their configs.

        Args:
            configs: Dict mapping integration name to config dict.
                Only integrations with matching keys are initialized.
        """
        for name, router in self._integrations.items():
            if name in configs:
                try:
                    await router.initialize(configs[name])
                    logger.info(f"Initialized integration: {name}")
                except Exception as e:
                    logger.error(
                        f"Failed to initialize integration '{name}': {e}",
                        exc_info=True,
                    )

    async def shutdown_integrations(self) -> None:
        """Shutdown all registered integrations."""
        for name, router in self._integrations.items():
            try:
                await router.shutdown()
            except Exception as e:
                logger.error(
                    f"Error shutting down integration '{name}': {e}",
                    exc_info=True,
                )

    def get_all_tool_schemas(self, employee_id: UUID) -> list[dict[str, Any]]:
        """Get all tool schemas from standalone tools + integrations.

        Args:
            employee_id: Employee to collect schemas for

        Returns:
            Combined list of tool schemas for LLM function calling
        """
        return self._tool_registry.get_all_tool_schemas()

    async def execute_tool_call(
        self, employee_id: UUID, tool_name: str, arguments: dict[str, Any]
    ) -> ActionResult:
        """Route tool call to the right implementation.

        Args:
            employee_id: Employee executing the tool call
            tool_name: Tool name (e.g., "web_search" or "email.send_email")
            arguments: Tool call arguments

        Returns:
            ActionResult from execution
        """
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

        return ActionResult(
            success=False,
            error=f"Unknown tool: {tool_name}",
        )

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

    def get_enabled_capabilities(self, employee_id: UUID) -> list[str]:
        """Return registered integration names."""
        return list(self._integrations.keys())

    def __repr__(self) -> str:
        tool_count = len(self._tool_registry)
        integration_count = len(self._integrations)
        return f"ToolRouter(standalone_tools={tool_count}, integrations={integration_count})"
