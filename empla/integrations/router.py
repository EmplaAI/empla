"""
empla.integrations.router - IntegrationRouter

FastAPI-style pattern for defining integration tools. Write one file
with @router.tool()-decorated functions and get auto-registration,
auto-schema generation, and namespace prefixing.

Example:
    >>> router = IntegrationRouter("email", adapter_factory=create_email_adapter)
    >>>
    >>> @router.tool()
    ... async def send_email(to: list[str], subject: str, body: str) -> dict:
    ...     return await router.adapter.send(to, subject, body)
    >>>
    >>> # Tools auto-named as "email.send_email", schemas auto-generated
    >>> router.get_tool_schemas()
"""

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from empla.core.tools.decorator import _build_parameters_schema

logger = logging.getLogger(__name__)


class IntegrationRouter:
    """Defines tools for an integration. One file = one integration.

    Modeled after FastAPI's APIRouter: you create a router, decorate
    functions with @router.tool(), and the framework handles schema
    generation, namespace prefixing, and registration.

    Args:
        name: Integration name (e.g. "email", "calendar", "crm").
            Used as namespace prefix for tool names.
        adapter_factory: Optional callable that creates an adapter
            from config kwargs. Called during initialize().
    """

    def __init__(
        self,
        name: str,
        adapter_factory: Callable[..., Any] | None = None,
        on_init: Callable[..., Awaitable[None]] | None = None,
        on_shutdown: Callable[..., Awaitable[None]] | None = None,
    ) -> None:
        self.name = name
        self._adapter_factory = adapter_factory
        self._on_init = on_init
        self._on_shutdown = on_shutdown
        self._adapter: Any = None
        self._tools: list[dict[str, Any]] = []
        self._mcp_config: dict[str, Any] | None = None

    @property
    def adapter(self) -> Any:
        """Access the adapter from tool functions.

        Raises:
            RuntimeError: If initialize() has not been called.
        """
        if self._adapter is None:
            raise RuntimeError(f"Integration '{self.name}' not initialized")
        return self._adapter

    async def initialize(self, config: dict[str, Any]) -> None:
        """Create adapter and initialize connection.

        For API adapters: calls adapter_factory with config, then
        adapter.initialize() if it exists.

        For MCP routers: connects to the MCP server and discovers tools.

        Args:
            config: Provider-specific configuration dict. For API adapters,
                passed as kwargs to adapter_factory. For MCP routers,
                may contain credentials.
        """
        if self._mcp_config is not None:
            await self._initialize_mcp(config)
            return

        # Direct connector: call on_init callback (no adapter needed)
        if self._on_init is not None:
            await self._on_init(**config)
            return

        if self._adapter_factory:
            # Shut down existing adapter before creating a new one
            if self._adapter is not None and hasattr(self._adapter, "shutdown"):
                await self._adapter.shutdown()
            factory_kwargs = {k: v for k, v in config.items() if k != "credentials"}
            self._adapter = self._adapter_factory(**factory_kwargs)
            if hasattr(self._adapter, "initialize"):
                await self._adapter.initialize(config.get("credentials", {}))

    async def _initialize_mcp(self, config: dict[str, Any]) -> None:
        """Connect to MCP server and discover tools."""
        from empla.core.tools.mcp_bridge import MCPBridge, MCPServerConfig
        from empla.core.tools.registry import ToolRegistry

        # Disconnect existing MCP bridge if re-initializing
        if hasattr(self, "_mcp_bridge"):
            await self._mcp_bridge.disconnect_all()

        # Clear previously discovered MCP tools to avoid duplicates
        self._tools = [t for t in self._tools if t["func"] is not None]

        # Merge stored MCP config with runtime overrides from initialize()
        merged = {**self._mcp_config, **config}
        mcp_config = MCPServerConfig(name=self.name, **merged)

        # Use a temporary registry to discover tools, then copy them
        temp_registry = ToolRegistry()
        bridge = MCPBridge(temp_registry)
        tool_names = await bridge.connect(mcp_config)

        # Convert discovered tools into our format
        for name in tool_names:
            tool = temp_registry.get_tool_by_name(name)
            impl = temp_registry.get_implementation(tool.tool_id) if tool else None
            if tool and impl:
                self._tools.append(
                    {
                        "name": name,
                        "description": tool.description,
                        "schema": tool.parameters_schema,
                        "func": None,
                        "impl": impl,
                    }
                )

        # Store bridge for cleanup
        self._mcp_bridge = bridge

        logger.info(
            f"MCP integration '{self.name}' discovered {len(tool_names)} tools",
            extra={"integration": self.name, "tools": tool_names},
        )

    async def shutdown(self) -> None:
        """Clean up adapter/connector connection. Each step is independent."""
        if hasattr(self, "_mcp_bridge"):
            try:
                await self._mcp_bridge.disconnect_all()
            except Exception:
                logger.exception("Error disconnecting MCP bridge for %s", self.name)
        if self._on_shutdown is not None:
            try:
                await self._on_shutdown()
            except Exception:
                logger.exception("Error in shutdown callback for %s", self.name)
        if self._adapter and hasattr(self._adapter, "shutdown"):
            try:
                await self._adapter.shutdown()
            except Exception:
                logger.exception("Error shutting down adapter for %s", self.name)

    def tool(self, name: str | None = None, description: str = "") -> Callable[..., Any]:
        """Decorator that registers a tool on this integration.

        Auto-generates JSON schema from type hints.
        Auto-prefixes tool name with integration name (email.send_email).

        Args:
            name: Override tool name (default: function name).
            description: Override description (default: function docstring).

        Returns:
            Decorator function.

        Example:
            >>> @router.tool()
            ... async def send_email(to: list[str], subject: str) -> dict:
            ...     '''Send a new email.'''
            ...     ...
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if not inspect.iscoroutinefunction(func):
                raise TypeError(f"Tool function '{func.__name__}' must be async (use 'async def')")
            tool_name = f"{self.name}.{name or func.__name__}"
            tool_desc = description or func.__doc__ or f"Tool: {tool_name}"
            schema = _build_parameters_schema(func)

            self._tools.append(
                {
                    "name": tool_name,
                    "description": tool_desc,
                    "schema": schema,
                    "func": func,
                    "impl": None,
                }
            )
            return func

        return decorator

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Get all tool schemas for ToolRouter registration.

        Returns:
            List of dicts with name, description, input_schema keys.
        """
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["schema"],
            }
            for t in self._tools
        ]

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool by name.

        Args:
            tool_name: Full tool name (e.g. "email.send_email").
            arguments: Tool call arguments.

        Returns:
            Tool execution result.

        Raises:
            ValueError: If tool_name is not registered on this router.
        """
        for t in self._tools:
            if t["name"] == tool_name:
                if t["func"] is not None:
                    return await t["func"](**arguments)
                if t["impl"] is not None:
                    return await t["impl"]._execute(arguments)
                raise RuntimeError(f"Tool '{tool_name}' has no implementation")
        raise ValueError(f"Unknown tool: {tool_name}")

    @classmethod
    def from_mcp(cls, name: str, **mcp_config: Any) -> "IntegrationRouter":
        """Create router that wraps an MCP server.

        Tools are auto-discovered via MCP protocol when initialize() is called.

        Args:
            name: Integration name (used as namespace prefix).
            **mcp_config: Passed to MCPServerConfig (transport, url, command, etc.).

        Returns:
            IntegrationRouter configured for MCP.

        Example:
            >>> calendar = IntegrationRouter.from_mcp(
            ...     "calendar", transport="http", url="http://localhost:9101"
            ... )
        """
        router = cls(name)
        router._mcp_config = mcp_config
        return router

    def __repr__(self) -> str:
        return f"IntegrationRouter(name={self.name!r}, tools={len(self._tools)})"


__all__ = ["IntegrationRouter"]
