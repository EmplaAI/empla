"""
Tests for empla.core.tools.mcp_bridge - MCP server bridge.

Tests use mocks since actual MCP servers require external dependencies.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from empla.core.tools.mcp_bridge import MCPBridge, MCPServerConfig, _MCPToolImplementation
from empla.core.tools.registry import ToolRegistry

# ============================================================================
# MCPServerConfig tests
# ============================================================================


class TestMCPServerConfig:
    def test_stdio_config(self):
        config = MCPServerConfig(
            name="salesforce",
            transport="stdio",
            command=["python", "sf_server.py"],
        )
        assert config.name == "salesforce"
        assert config.transport == "stdio"
        assert config.command == ["python", "sf_server.py"]
        assert config.url is None
        assert config.env == {}

    def test_http_config(self):
        config = MCPServerConfig(
            name="slack",
            transport="http",
            url="http://localhost:8000/mcp",
        )
        assert config.name == "slack"
        assert config.transport == "http"
        assert config.url == "http://localhost:8000/mcp"
        assert config.command is None

    def test_config_with_env(self):
        config = MCPServerConfig(
            name="custom",
            transport="stdio",
            command=["node", "server.js"],
            env={"API_KEY": "secret123"},
        )
        assert config.env == {"API_KEY": "secret123"}


# ============================================================================
# MCPBridge basic tests
# ============================================================================


class TestMCPBridge:
    @pytest.fixture
    def registry(self):
        return ToolRegistry()

    @pytest.fixture
    def bridge(self, registry):
        return MCPBridge(registry)

    def test_init(self, bridge):
        assert bridge.connected_servers == []

    def test_connected_servers_empty(self, bridge):
        assert bridge.connected_servers == []

    async def test_connect_invalid_transport(self, bridge):
        config = MCPServerConfig(
            name="bad",
            transport="websocket",
            url="ws://localhost:8000",
        )
        with pytest.raises(ValueError, match="Unknown transport"):
            await bridge.connect(config)

    async def test_connect_stdio_missing_command(self, bridge):
        config = MCPServerConfig(
            name="bad",
            transport="stdio",
        )
        # This should fail because no command is provided
        # But first it needs to import mcp - if mcp is not installed, ImportError
        with pytest.raises((ValueError, ImportError)):
            await bridge.connect(config)

    async def test_connect_http_missing_url(self, bridge):
        config = MCPServerConfig(
            name="bad",
            transport="http",
        )
        with pytest.raises((ValueError, ImportError)):
            await bridge.connect(config)

    async def test_disconnect_unknown_server(self, bridge):
        # Should not raise, just log warning
        await bridge.disconnect("nonexistent")

    async def test_disconnect_all_empty(self, bridge):
        # Should not raise
        await bridge.disconnect_all()


# ============================================================================
# _MCPToolImplementation tests
# ============================================================================


class TestMCPToolImplementation:
    async def test_execute_with_text_content(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "search result here"
        mock_result.content = [mock_block]
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        impl = _MCPToolImplementation(mock_session, "search")
        result = await impl._execute({"query": "test"})

        mock_session.call_tool.assert_called_once_with("search", arguments={"query": "test"})
        assert result == "search result here"

    async def test_execute_with_multiple_blocks(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        block1 = MagicMock()
        block1.text = "line 1"
        block2 = MagicMock()
        block2.text = "line 2"
        mock_result.content = [block1, block2]
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        impl = _MCPToolImplementation(mock_session, "multi")
        result = await impl._execute({})

        assert result == "line 1\nline 2"

    async def test_execute_with_no_content(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.content = []
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        impl = _MCPToolImplementation(mock_session, "empty")
        result = await impl._execute({})
        # Returns the raw result when no text blocks
        assert result == mock_result

    async def test_execute_with_no_text_attr(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_block = MagicMock(spec=[])  # No text attribute
        mock_result.content = [mock_block]
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        impl = _MCPToolImplementation(mock_session, "no_text")
        result = await impl._execute({})
        # No text blocks found, returns raw result
        assert result == mock_result


# ============================================================================
# MCPBridge with mocked MCP SDK
# ============================================================================


class TestMCPBridgeWithMocks:
    """Test MCPBridge connection flow with mocked MCP SDK."""

    @pytest.fixture
    def registry(self):
        return ToolRegistry()

    @pytest.fixture
    def bridge(self, registry):
        return MCPBridge(registry)

    async def test_register_server_tools(self, bridge, registry):
        """Test that _register_server_tools correctly registers MCP tools."""
        mock_session = AsyncMock()

        # Create mock MCP tools
        mock_tool_1 = MagicMock(spec=["name", "description", "inputSchema"])
        mock_tool_1.name = "query"
        mock_tool_1.description = "Query records"
        mock_tool_1.inputSchema = {
            "type": "object",
            "properties": {"soql": {"type": "string"}},
            "required": ["soql"],
        }

        mock_tool_2 = MagicMock(spec=["name", "description", "inputSchema"])
        mock_tool_2.name = "create_record"
        mock_tool_2.description = "Create a record"
        mock_tool_2.inputSchema = {
            "type": "object",
            "properties": {"object_type": {"type": "string"}, "data": {"type": "object"}},
        }

        mock_tools_result = MagicMock()
        mock_tools_result.tools = [mock_tool_1, mock_tool_2]
        mock_session.list_tools = AsyncMock(return_value=mock_tools_result)

        # Register tools
        names = await bridge._register_server_tools("salesforce", mock_session)

        assert len(names) == 2
        assert "salesforce.query" in names
        assert "salesforce.create_record" in names

        # Verify tools are in registry
        assert "salesforce.query" in registry
        assert "salesforce.create_record" in registry

        # Verify schema
        schemas = registry.get_all_tool_schemas()
        assert len(schemas) == 2
        query_schema = next(s for s in schemas if s["name"] == "salesforce.query")
        assert query_schema["description"] == "Query records"

    async def test_register_skips_duplicate(self, bridge, registry):
        """Test that duplicate tool names are skipped."""
        # Pre-register a tool with conflicting name
        from empla.core.tools.base import Tool

        existing = Tool(
            name="server.existing",
            description="Already registered",
            parameters_schema={},
        )

        class Impl:
            async def _execute(self, params):
                return None

        registry.register_tool(existing, Impl())

        # Try to register MCP tool with same name
        mock_session = AsyncMock()
        mock_tool = MagicMock(spec=["name", "description", "inputSchema"])
        mock_tool.name = "existing"
        mock_tool.description = "MCP version"
        mock_tool.inputSchema = {}
        mock_tools_result = MagicMock()
        mock_tools_result.tools = [mock_tool]
        mock_session.list_tools = AsyncMock(return_value=mock_tools_result)

        names = await bridge._register_server_tools("server", mock_session)
        # Should skip the duplicate
        assert names == []

    async def test_disconnect_unregisters_tools(self, bridge, registry):
        """Test that disconnect removes tools from registry."""
        mock_session = AsyncMock()

        # Simulate a connected server
        bridge._connections["testserver"] = {
            "session": mock_session,
            "tool_names": ["testserver.tool_a", "testserver.tool_b"],
            "config": MCPServerConfig(name="testserver", transport="stdio", command=["test"]),
        }

        # Register the tools
        from empla.core.tools.base import Tool

        for name in ["testserver.tool_a", "testserver.tool_b"]:
            t = Tool(name=name, description="test", parameters_schema={})

            class Impl:
                async def _execute(self, params):
                    return None

            registry.register_tool(t, Impl())

        assert "testserver.tool_a" in registry
        assert "testserver.tool_b" in registry

        # Disconnect
        await bridge.disconnect("testserver")

        assert "testserver.tool_a" not in registry
        assert "testserver.tool_b" not in registry
        assert "testserver" not in bridge.connected_servers

    async def test_disconnect_all(self, bridge):
        """Test disconnecting all servers."""
        # Add two mock connections
        for name in ["server_a", "server_b"]:
            bridge._connections[name] = {
                "session": AsyncMock(),
                "tool_names": [],
                "config": MCPServerConfig(name=name, transport="stdio", command=["test"]),
            }

        assert len(bridge.connected_servers) == 2

        await bridge.disconnect_all()

        assert len(bridge.connected_servers) == 0


# ============================================================================
# Integration: MCPBridge + ToolRouter
# ============================================================================


class TestMCPBridgeWithRouter:
    async def test_mcp_tools_appear_in_router(self):
        """Verify MCP-registered tools show up via ToolRouter."""
        from empla.capabilities.registry import CapabilityRegistry
        from empla.core.tools.router import ToolRouter

        cap_registry = CapabilityRegistry()
        tool_registry = ToolRegistry()
        router = ToolRouter(cap_registry, tool_registry)
        bridge = MCPBridge(tool_registry)

        # Simulate registering MCP tools
        mock_session = AsyncMock()
        mock_tool = MagicMock(spec=["name", "description", "inputSchema"])
        mock_tool.name = "post_message"
        mock_tool.description = "Post a message to Slack"
        mock_tool.inputSchema = {
            "type": "object",
            "properties": {"channel": {"type": "string"}, "text": {"type": "string"}},
        }
        mock_tools_result = MagicMock()
        mock_tools_result.tools = [mock_tool]
        mock_session.list_tools = AsyncMock(return_value=mock_tools_result)

        await bridge._register_server_tools("slack", mock_session)

        # Verify tool appears in router schemas
        employee_id = uuid4()
        schemas = router.get_all_tool_schemas(employee_id)
        assert len(schemas) == 1
        assert schemas[0]["name"] == "slack.post_message"
        assert schemas[0]["description"] == "Post a message to Slack"

    async def test_mcp_tool_execution_through_router(self):
        """Verify MCP tools can be executed via ToolRouter."""
        from empla.capabilities.registry import CapabilityRegistry
        from empla.core.tools.router import ToolRouter

        cap_registry = CapabilityRegistry()
        tool_registry = ToolRegistry()
        router = ToolRouter(cap_registry, tool_registry)
        bridge = MCPBridge(tool_registry)

        # Simulate an MCP tool
        mock_session = AsyncMock()
        mock_tool = MagicMock(spec=["name", "description", "inputSchema"])
        mock_tool.name = "list_channels"
        mock_tool.description = "List Slack channels"
        mock_tool.inputSchema = {"type": "object", "properties": {}}
        mock_tools_result = MagicMock()
        mock_tools_result.tools = [mock_tool]
        mock_session.list_tools = AsyncMock(return_value=mock_tools_result)

        # Mock call_tool response
        mock_call_result = MagicMock()
        mock_block = MagicMock()
        mock_block.text = '["general", "random"]'
        mock_call_result.content = [mock_block]
        mock_session.call_tool = AsyncMock(return_value=mock_call_result)

        await bridge._register_server_tools("slack", mock_session)

        # Execute through router
        employee_id = uuid4()
        result = await router.execute_tool_call(employee_id, "slack.list_channels", {})
        assert result.success is True
        assert result.output == '["general", "random"]'
