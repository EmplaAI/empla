"""
empla.core.tools.router - Unified Tool Router

Combines ToolRegistry + IntegrationRouters behind a single interface:
  - get_all_tool_schemas(employee_id)
  - execute_tool_call(employee_id, tool_name, arguments)
  - get_enabled_capabilities(employee_id)

All tool calls pass through a trust boundary (validate allowlist,
audit log, rate limit) and a timeout wrapper before execution.

Architecture:
  LLM → execute_tool_call()
         ├── TrustBoundary.validate() → DENY? return error
         ├── asyncio.timeout(30s)
         └── _execute_standalone_tool() → ActionResult
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from uuid import UUID

from empla.core.tools.base import ActionResult

from .base import ToolImplementation
from .health import IntegrationHealthMonitor
from .registry import ToolRegistry
from .trust import TrustBoundary

logger = logging.getLogger(__name__)

# Default timeout for tool execution (seconds)
DEFAULT_TOOL_TIMEOUT = 30.0


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
        trust_boundary: TrustBoundary | None = None,
        tool_timeout: float = DEFAULT_TOOL_TIMEOUT,
    ) -> None:
        self._tool_registry = tool_registry if tool_registry is not None else ToolRegistry()
        self._integrations: dict[str, Any] = {}
        self._trust = trust_boundary if trust_boundary is not None else TrustBoundary()
        self._tool_timeout = tool_timeout
        self._health = IntegrationHealthMonitor()

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

    @staticmethod
    def _parse_integration(tool_name: str) -> str:
        """Extract integration name from tool name (prefix before the dot)."""
        return tool_name.split(".")[0] if "." in tool_name else tool_name

    async def execute_tool_call(
        self,
        employee_id: UUID,
        tool_name: str,
        arguments: dict[str, Any],
        employee_role: str | None = None,
        tenant_id: UUID | None = None,
    ) -> ActionResult:
        """Route tool call through trust boundary, timeout, then execution.

        All tool calls pass through:
        1. Trust boundary validation (allowlist + rate limit + audit)
        2. Timeout wrapper (default 30s, configurable)
        3. Actual tool execution

        Args:
            employee_id: Employee executing the tool call
            tool_name: Tool name (e.g., "web_search" or "email.send_email")
            arguments: Tool call arguments
            employee_role: Employee role for trust boundary checks (optional)
            tenant_id: Tenant ID for audit logging (optional)

        Returns:
            ActionResult from execution (or error if denied/timed out)
        """
        # ---- Trust boundary check ----
        decision = self._trust.validate(
            tool_name=tool_name,
            arguments=arguments,
            employee_id=employee_id,
            employee_role=employee_role,
            tenant_id=tenant_id,
        )
        if not decision.allowed:
            return ActionResult(
                success=False,
                error=f"Trust boundary denied: {decision.reason}",
                metadata={"trust_denied": True, "reason": decision.reason},
            )

        # ---- Resolve tool ----
        tool = self._tool_registry.get_tool_by_name(tool_name)
        if tool is None:
            return ActionResult(
                success=False,
                error=f"Unknown tool: {tool_name}",
            )

        impl = self._tool_registry.get_implementation(tool.tool_id)
        if impl is None:
            logger.error(
                "Tool '%s' found in registry but has no implementation",
                tool_name,
                extra={"employee_id": str(employee_id), "tool_name": tool_name},
            )
            return ActionResult(
                success=False,
                error=f"Tool '{tool_name}' has no implementation",
            )

        # ---- Execute with timeout ----
        integration = self._parse_integration(tool_name)
        start = time.monotonic()
        try:
            async with asyncio.timeout(self._tool_timeout):
                result = await self._execute_standalone_tool(tool_name, impl, arguments)
        except TimeoutError:
            duration_ms = (time.monotonic() - start) * 1000
            logger.warning(
                "Tool '%s' timed out after %.1fs",
                tool_name,
                self._tool_timeout,
                extra={
                    "employee_id": str(employee_id),
                    "tool_name": tool_name,
                    "timeout_seconds": self._tool_timeout,
                },
            )
            self._health.record(
                integration=integration,
                success=False,
                duration_ms=duration_ms,
                error="timeout",
                is_timeout=True,
            )
            return ActionResult(
                success=False,
                error=f"Tool '{tool_name}' timed out after {self._tool_timeout}s",
                metadata={"timeout": True, "duration_ms": duration_ms},
            )
        except Exception:
            # Unexpected error — still record health before re-raising
            duration_ms = (time.monotonic() - start) * 1000
            self._health.record(
                integration=integration,
                success=False,
                duration_ms=duration_ms,
                error="unexpected_error",
            )
            raise

        # Add timing metadata and record health
        duration_ms = (time.monotonic() - start) * 1000
        result.metadata["duration_ms"] = duration_ms
        self._health.record(
            integration=integration,
            success=result.success,
            duration_ms=duration_ms,
            error=result.error,
        )
        return result

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

    def reset_trust_cycle(self) -> None:
        """Reset trust boundary per-cycle counters. Call at BDI cycle start."""
        self._trust.reset_cycle()

    def get_trust_stats(self) -> dict[str, Any]:
        """Return trust boundary stats for observability."""
        return self._trust.get_cycle_stats()

    def get_integration_health(self, integration: str) -> dict[str, Any]:
        """Get health status for a specific integration."""
        return self._health.get_status(integration)

    def get_all_integration_health(self) -> list[dict[str, Any]]:
        """Get health status for all tracked integrations."""
        return self._health.get_all_status()

    def get_health_beliefs(self) -> list[dict[str, Any]]:
        """Get BDI-compatible beliefs from integration health. Feed into belief system."""
        return self._health.get_beliefs()

    def __repr__(self) -> str:
        tool_count = len(self._tool_registry)
        integration_count = len(self._integrations)
        return f"ToolRouter(standalone_tools={tool_count}, integrations={integration_count})"
