"""
Extended coverage tests for MCPBridge and related classes.

Tests MCPServerConfig validation, MCPBridge connect/disconnect,
_MCPToolImplementation, and error paths -- all with mocked MCP libraries.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from empla.core.tools.base import Tool
from empla.core.tools.mcp_bridge import (
    MCPBridge,
    MCPServerConfig,
    _MCPToolImplementation,
)
from empla.core.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# MCPServerConfig validation
# ---------------------------------------------------------------------------


class TestMCPServerConfig:
    def test_http_requires_url(self):
        with pytest.raises(ValidationError, match="HTTP transport requires 'url'"):
            MCPServerConfig(name="test", transport="http")

    def test_stdio_requires_command(self):
        with pytest.raises(ValidationError, match="stdio transport requires 'command'"):
            MCPServerConfig(name="test", transport="stdio")

    def test_http_valid(self):
        cfg = MCPServerConfig(name="s", transport="http", url="http://localhost:8000")
        assert cfg.url == "http://localhost:8000"

    def test_stdio_valid(self):
        cfg = MCPServerConfig(name="s", transport="stdio", command=["python", "s.py"])
        assert cfg.command == ["python", "s.py"]

    def test_headers_default_empty(self):
        cfg = MCPServerConfig(name="s", transport="http", url="http://x")
        assert cfg.headers == {}

    def test_env_default_empty(self):
        cfg = MCPServerConfig(name="s", transport="stdio", command=["x"])
        assert cfg.env == {}


# ---------------------------------------------------------------------------
# _MCPToolImplementation
# ---------------------------------------------------------------------------


class TestMCPToolImplementation:
    @pytest.mark.asyncio
    async def test_execute_with_text_content(self):
        """Extracts text from content blocks."""
        mock_session = AsyncMock()
        result = MagicMock()
        block1 = MagicMock()
        block1.text = "hello"
        block2 = MagicMock()
        block2.text = "world"
        result.content = [block1, block2]
        mock_session.call_tool.return_value = result

        impl = _MCPToolImplementation(mock_session, "test_tool")
        output = await impl._execute({"arg": "val"})
        assert output == "hello\nworld"
        mock_session.call_tool.assert_awaited_once_with("test_tool", arguments={"arg": "val"})

    @pytest.mark.asyncio
    async def test_execute_single_text(self):
        """Single text block returns just the string."""
        mock_session = AsyncMock()
        result = MagicMock()
        block = MagicMock()
        block.text = "only text"
        result.content = [block]
        mock_session.call_tool.return_value = result

        impl = _MCPToolImplementation(mock_session, "tool")
        output = await impl._execute({})
        assert output == "only text"

    @pytest.mark.asyncio
    async def test_execute_no_content(self):
        """Returns raw result when content is empty."""
        mock_session = AsyncMock()
        result = MagicMock()
        result.content = []
        mock_session.call_tool.return_value = result

        impl = _MCPToolImplementation(mock_session, "tool")
        output = await impl._execute({})
        assert output is result

    @pytest.mark.asyncio
    async def test_execute_no_content_attr(self):
        """Returns raw result when no content attribute."""
        mock_session = AsyncMock()
        result = "raw_string_result"
        mock_session.call_tool.return_value = result

        impl = _MCPToolImplementation(mock_session, "tool")
        output = await impl._execute({})
        assert output == "raw_string_result"

    @pytest.mark.asyncio
    async def test_execute_content_blocks_without_text(self):
        """Content blocks without text attribute are skipped."""
        mock_session = AsyncMock()
        result = MagicMock()
        block = MagicMock(spec=[])  # No attributes
        result.content = [block]
        mock_session.call_tool.return_value = result

        impl = _MCPToolImplementation(mock_session, "tool")
        output = await impl._execute({})
        # No texts extracted, returns raw result
        assert output is result


# ---------------------------------------------------------------------------
# MCPBridge
# ---------------------------------------------------------------------------


class TestMCPBridge:
    @pytest.fixture
    def registry(self) -> ToolRegistry:
        return ToolRegistry()

    @pytest.fixture
    def bridge(self, registry: ToolRegistry) -> MCPBridge:
        return MCPBridge(registry)

    def test_connected_servers_empty(self, bridge: MCPBridge):
        assert bridge.connected_servers == []

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, bridge: MCPBridge):
        """Connecting to an already-connected server returns existing tools."""
        bridge._connections["myserver"] = {
            "tool_names": ["myserver.tool1", "myserver.tool2"],
        }
        config = MCPServerConfig(name="myserver", transport="http", url="http://x")
        result = await bridge.connect(config)
        assert result == ["myserver.tool1", "myserver.tool2"]

    @pytest.mark.asyncio
    async def test_disconnect_unknown_server(self, bridge: MCPBridge):
        """Disconnecting from unknown server is a no-op."""
        await bridge.disconnect("nonexistent")
        assert bridge.connected_servers == []

    @pytest.mark.asyncio
    async def test_disconnect_unregisters_tools_and_closes(
        self, bridge: MCPBridge, registry: ToolRegistry
    ):
        """Disconnect unregisters tools and closes session/transport CMs."""
        # Register a real tool first
        tool = Tool(
            name="srv.tool1",
            description="t",
            parameters_schema={},
            category="mcp",
        )
        impl = MagicMock()
        registry.register_tool(tool, impl)

        session_cm = AsyncMock()
        transport_cm = AsyncMock()
        http_client = AsyncMock()

        bridge._connections["srv"] = {
            "session": MagicMock(),
            "session_cm": session_cm,
            "transport_cm": transport_cm,
            "http_client": http_client,
            "tool_names": ["srv.tool1"],
            "config": MagicMock(),
        }

        await bridge.disconnect("srv")

        assert "srv" not in bridge._connections
        assert registry.get_tool_by_name("srv.tool1") is None
        session_cm.__aexit__.assert_awaited_once()
        transport_cm.__aexit__.assert_awaited_once()
        http_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_handles_session_cm_error(self, bridge: MCPBridge):
        """Disconnect handles errors from session CM gracefully."""
        session_cm = AsyncMock()
        session_cm.__aexit__.side_effect = Exception("session error")
        transport_cm = AsyncMock()

        bridge._connections["srv"] = {
            "session": MagicMock(),
            "session_cm": session_cm,
            "transport_cm": transport_cm,
            "tool_names": [],
            "config": MagicMock(),
        }

        await bridge.disconnect("srv")
        assert "srv" not in bridge._connections

    @pytest.mark.asyncio
    async def test_disconnect_handles_transport_cm_error(self, bridge: MCPBridge):
        """Disconnect handles errors from transport CM gracefully."""
        transport_cm = AsyncMock()
        transport_cm.__aexit__.side_effect = Exception("transport error")

        bridge._connections["srv"] = {
            "session": MagicMock(),
            "session_cm": None,
            "transport_cm": transport_cm,
            "tool_names": [],
            "config": MagicMock(),
        }

        await bridge.disconnect("srv")
        assert "srv" not in bridge._connections

    @pytest.mark.asyncio
    async def test_disconnect_handles_http_client_error(self, bridge: MCPBridge):
        """Disconnect handles errors from HTTP client close gracefully."""
        http_client = AsyncMock()
        http_client.aclose.side_effect = Exception("close error")

        bridge._connections["srv"] = {
            "session": MagicMock(),
            "session_cm": None,
            "transport_cm": None,
            "http_client": http_client,
            "tool_names": [],
            "config": MagicMock(),
        }

        await bridge.disconnect("srv")
        assert "srv" not in bridge._connections

    @pytest.mark.asyncio
    async def test_disconnect_all(self, bridge: MCPBridge):
        """disconnect_all disconnects every server."""
        bridge._connections["a"] = {
            "session": MagicMock(),
            "session_cm": None,
            "transport_cm": None,
            "tool_names": [],
            "config": MagicMock(),
        }
        bridge._connections["b"] = {
            "session": MagicMock(),
            "session_cm": None,
            "transport_cm": None,
            "tool_names": [],
            "config": MagicMock(),
        }

        await bridge.disconnect_all()
        assert bridge.connected_servers == []

    @pytest.mark.asyncio
    async def test_register_server_tools(self, bridge: MCPBridge, registry: ToolRegistry):
        """_register_server_tools discovers tools and registers them."""
        mock_session = AsyncMock()

        # Use spec=[] to prevent auto-attribute creation, then set what we need
        mcp_tool_1 = MagicMock(spec=[])
        mcp_tool_1.name = "query"
        mcp_tool_1.description = "Query data"
        mcp_tool_1.inputSchema = {"type": "object"}

        mcp_tool_2 = MagicMock(spec=[])
        mcp_tool_2.name = "create"
        mcp_tool_2.description = None
        # Use input_schema instead of inputSchema
        mcp_tool_2.input_schema = {"type": "object"}

        tools_result = MagicMock()
        tools_result.tools = [mcp_tool_1, mcp_tool_2]
        mock_session.list_tools.return_value = tools_result

        names = await bridge._register_server_tools("salesforce", mock_session)
        assert names == ["salesforce.query", "salesforce.create"]
        assert registry.get_tool_by_name("salesforce.query") is not None
        assert registry.get_tool_by_name("salesforce.create") is not None

    @pytest.mark.asyncio
    async def test_register_server_tools_rollback_on_error(
        self, bridge: MCPBridge, registry: ToolRegistry
    ):
        """If registration fails mid-way, already-registered tools are rolled back.

        We use a mock registry to verify rollback behavior since the real
        registry + Pydantic Tool construction is hard to fail mid-loop.
        """
        mock_registry = MagicMock(spec=ToolRegistry)
        call_count = [0]

        def register_side_effect(tool, impl):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("boom")

        mock_registry.register_tool.side_effect = register_side_effect
        bridge_with_mock = MCPBridge(mock_registry)

        mock_session = AsyncMock()
        tool1 = MagicMock()
        tool1.name = "good_tool"
        tool1.description = "OK"
        tool1.inputSchema = {"type": "object"}

        tool2 = MagicMock()
        tool2.name = "bad_tool"
        tool2.description = "Fails"
        tool2.inputSchema = {"type": "object"}

        tools_result = MagicMock()
        tools_result.tools = [tool1, tool2]
        mock_session.list_tools.return_value = tools_result

        with pytest.raises(RuntimeError, match="boom"):
            await bridge_with_mock._register_server_tools("srv", mock_session)

        # Rollback should have unregistered the first tool
        mock_registry.unregister_tool.assert_called_once_with("srv.good_tool")

    @pytest.mark.asyncio
    async def test_register_tool_duplicate_skipped(self, bridge: MCPBridge, registry: ToolRegistry):
        """Duplicate tool names are skipped (logged as warning)."""
        # Pre-register a tool
        existing = Tool(
            name="srv.query",
            description="existing",
            parameters_schema={},
        )
        registry.register_tool(existing, MagicMock())

        mock_session = AsyncMock()
        mcp_tool = MagicMock(spec=[])
        mcp_tool.name = "query"
        mcp_tool.description = "new version"
        # No inputSchema/input_schema attrs on spec=[] mock
        tools_result = MagicMock()
        tools_result.tools = [mcp_tool]
        mock_session.list_tools.return_value = tools_result

        names = await bridge._register_server_tools("srv", mock_session)
        # Duplicate was skipped, so not in returned list
        assert names == []

    @pytest.mark.asyncio
    async def test_register_tool_no_schema(self, bridge: MCPBridge, registry: ToolRegistry):
        """Tool with no inputSchema or input_schema gets empty schema."""
        mock_session = AsyncMock()
        mcp_tool = MagicMock(spec=[])
        mcp_tool.name = "simple"
        mcp_tool.description = "No schema"
        # No inputSchema or input_schema attributes
        tools_result = MagicMock()
        tools_result.tools = [mcp_tool]
        mock_session.list_tools.return_value = tools_result

        names = await bridge._register_server_tools("srv", mock_session)
        assert names == ["srv.simple"]
        tool = registry.get_tool_by_name("srv.simple")
        assert tool is not None
        assert tool.parameters_schema == {}
