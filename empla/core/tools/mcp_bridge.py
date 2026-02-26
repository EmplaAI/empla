"""
empla.core.tools.mcp_bridge - MCP Server Bridge

Manages connections to external MCP (Model Context Protocol) servers,
discovers their tools, and registers them into the ToolRegistry.

MCP tools appear as "{server_name}.{tool_name}" in the registry,
avoiding name collisions between servers.

Requires the `mcp` optional dependency: pip install empla[mcp]

Example:
    >>> bridge = MCPBridge(tool_registry)
    >>> await bridge.connect(MCPServerConfig(
    ...     name="salesforce",
    ...     transport="stdio",
    ...     command=["python", "salesforce_mcp_server.py"],
    ... ))
    >>> # Tools like "salesforce.query", "salesforce.create_record" now in registry
    >>> await bridge.disconnect_all()
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from .base import Tool
from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class MCPServerConfig(BaseModel):
    """Configuration for connecting to an MCP server."""

    name: str = Field(..., description="Server name used as tool prefix (e.g., 'salesforce')")
    transport: str = Field(..., description="Transport type: 'stdio' or 'http'")
    command: list[str] | None = Field(
        default=None,
        description="Command for stdio transport (e.g., ['python', 'server.py'])",
    )
    url: str | None = Field(
        default=None,
        description="URL for HTTP transport (e.g., 'http://localhost:8000/mcp')",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables for stdio subprocess",
    )


class _MCPToolImplementation:
    """Wraps an MCP session.call_tool() as a ToolImplementation."""

    def __init__(self, session: Any, tool_name: str) -> None:
        self._session = session
        self._tool_name = tool_name

    async def _execute(self, params: dict[str, Any]) -> Any:
        result = await self._session.call_tool(self._tool_name, arguments=params)
        # MCP result may have .content with text blocks
        if hasattr(result, "content") and result.content:
            # Extract text from content blocks
            texts = []
            for block in result.content:
                if hasattr(block, "text"):
                    texts.append(block.text)
            if texts:
                return "\n".join(texts) if len(texts) > 1 else texts[0]
        return result


class MCPBridge:
    """
    Manages connections to external MCP servers and registers their tools.

    Each connected server's tools appear in the ToolRegistry as
    "{server_name}.{tool_name}", enabling the agentic loop to call them.

    Example:
        >>> bridge = MCPBridge(tool_registry)
        >>> await bridge.connect(MCPServerConfig(
        ...     name="slack",
        ...     transport="stdio",
        ...     command=["npx", "@slack/mcp-server"],
        ... ))
        >>> # "slack.post_message", "slack.list_channels", etc. now available
        >>> await bridge.disconnect_all()
    """

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tool_registry = tool_registry
        # server_name -> (session, context_manager, registered_tool_names)
        self._connections: dict[str, dict[str, Any]] = {}

    @property
    def connected_servers(self) -> list[str]:
        """List of currently connected server names."""
        return list(self._connections.keys())

    async def connect(self, config: MCPServerConfig) -> list[str]:
        """Connect to an MCP server and register its tools.

        Args:
            config: Server connection configuration

        Returns:
            List of registered tool names (prefixed)

        Raises:
            ImportError: If the mcp package is not installed
            ValueError: If transport config is invalid
            ConnectionError: If connection to server fails
        """
        # Validate transport before importing mcp
        if config.transport not in ("stdio", "http"):
            raise ValueError(f"Unknown transport '{config.transport}'. Use 'stdio' or 'http'.")

        if config.name in self._connections:
            logger.warning(f"Already connected to MCP server: {config.name}")
            return list(self._connections[config.name].get("tool_names", []))

        if config.transport == "stdio":
            return await self._connect_stdio(config)
        return await self._connect_http(config)

    async def _connect_stdio(self, config: MCPServerConfig) -> list[str]:
        """Connect via stdio transport."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        if not config.command:
            raise ValueError("stdio transport requires 'command' in config")

        server_params = StdioServerParameters(
            command=config.command[0],
            args=config.command[1:] if len(config.command) > 1 else [],
            env=config.env or None,
        )

        # Create transport and session
        read_stream, write_stream = await stdio_client(server_params).__aenter__()
        session = await ClientSession(read_stream, write_stream).__aenter__()
        await session.initialize()

        # Discover and register tools
        tool_names = await self._register_server_tools(config.name, session)

        self._connections[config.name] = {
            "session": session,
            "tool_names": tool_names,
            "config": config,
        }

        logger.info(
            f"Connected to MCP server '{config.name}' via stdio, "
            f"registered {len(tool_names)} tools",
            extra={
                "server_name": config.name,
                "tool_count": len(tool_names),
                "tools": tool_names,
            },
        )

        return tool_names

    async def _connect_http(self, config: MCPServerConfig) -> list[str]:
        """Connect via HTTP/SSE transport."""
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as e:
            raise ImportError(
                "HTTP MCP transport requires the 'mcp' package with HTTP support."
            ) from e

        if not config.url:
            raise ValueError("http transport requires 'url' in config")

        read_stream, write_stream, _ = await streamablehttp_client(config.url).__aenter__()
        session = await ClientSession(read_stream, write_stream).__aenter__()
        await session.initialize()

        tool_names = await self._register_server_tools(config.name, session)

        self._connections[config.name] = {
            "session": session,
            "tool_names": tool_names,
            "config": config,
        }

        logger.info(
            f"Connected to MCP server '{config.name}' via HTTP, registered {len(tool_names)} tools",
            extra={
                "server_name": config.name,
                "tool_count": len(tool_names),
                "tools": tool_names,
            },
        )

        return tool_names

    async def _register_server_tools(self, server_name: str, session: Any) -> list[str]:
        """Discover tools from MCP server and register them.

        Args:
            server_name: Name prefix for tools
            session: MCP ClientSession

        Returns:
            List of registered tool names
        """
        tools_result = await session.list_tools()
        registered_names: list[str] = []

        for mcp_tool in tools_result.tools:
            prefixed_name = f"{server_name}.{mcp_tool.name}"

            # Build Tool model from MCP tool definition
            input_schema = {}
            if hasattr(mcp_tool, "inputSchema") and mcp_tool.inputSchema:
                input_schema = mcp_tool.inputSchema
            elif hasattr(mcp_tool, "input_schema") and mcp_tool.input_schema:
                input_schema = mcp_tool.input_schema

            tool = Tool(
                name=prefixed_name,
                description=mcp_tool.description or f"MCP tool: {mcp_tool.name}",
                parameters_schema=input_schema,
                category="mcp",
                tags=["mcp", server_name],
            )

            impl = _MCPToolImplementation(session, mcp_tool.name)

            try:
                self._tool_registry.register_tool(tool, impl)
                registered_names.append(prefixed_name)
            except ValueError:
                logger.warning(
                    f"Tool '{prefixed_name}' already registered, skipping",
                    extra={"server_name": server_name, "tool_name": mcp_tool.name},
                )

        return registered_names

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from an MCP server and unregister its tools.

        Args:
            server_name: Name of the server to disconnect
        """
        conn = self._connections.pop(server_name, None)
        if conn is None:
            logger.warning(f"No connection found for MCP server: {server_name}")
            return

        # Unregister tools
        for tool_name in conn.get("tool_names", []):
            self._tool_registry.unregister_tool(tool_name)

        # Close session
        session = conn.get("session")
        if session:
            try:
                await session.__aexit__(None, None, None)
            except Exception:
                logger.warning(
                    f"Error closing MCP session for {server_name}",
                    exc_info=True,
                )

        logger.info(
            f"Disconnected from MCP server: {server_name}",
            extra={"server_name": server_name},
        )

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        server_names = list(self._connections.keys())
        for name in server_names:
            await self.disconnect(name)
