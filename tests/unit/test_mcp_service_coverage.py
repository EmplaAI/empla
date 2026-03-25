"""
Extended coverage tests for MCPIntegrationService.

Covers CRUD operations, credential management, active server resolution,
and error paths with mocked SQLAlchemy sessions and TokenManager.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from empla.models.integration import (
    Integration,
    IntegrationAuthType,
    IntegrationCredential,
    IntegrationStatus,
    IntegrationType,
)
from empla.services.integrations.key_provider import NoKeysConfiguredError
from empla.services.integrations.mcp_service import MCPIntegrationService
from empla.services.integrations.token_manager import DecryptionError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT_ID = uuid4()
SERVER_ID = uuid4()
USER_ID = uuid4()


def _make_integration(
    server_id: UUID | None = None,
    name: str = "test-server",
    transport: str = "http",
    auth_type: str = IntegrationAuthType.NONE,
    status: str = IntegrationStatus.ACTIVE,
    url: str = "http://localhost:8000/mcp",
) -> Integration:
    """Build a mock Integration object."""
    sid = server_id or uuid4()
    integration = MagicMock(spec=Integration)
    integration.id = sid
    integration.tenant_id = TENANT_ID
    integration.integration_type = IntegrationType.MCP
    integration.provider = name
    integration.auth_type = auth_type
    integration.display_name = name
    integration.status = status
    integration.deleted_at = None
    integration.created_at = datetime.now(UTC)
    integration.oauth_config = {
        "transport": transport,
        "name": name,
        "description": "Test server",
        "discovered_tools": [],
        "last_connected_at": None,
        "last_error": None,
        "url": url,
    }
    return integration


def _mock_scalar_result(value):
    """Create a mock result that returns value from scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalars_result(values):
    """Create a mock result with scalars().all() returning values."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    result.scalars.return_value = scalars
    return result


@pytest.fixture
def session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    s.flush = AsyncMock()
    s.commit = AsyncMock()
    s.refresh = AsyncMock()
    s.execute = AsyncMock()
    return s


@pytest.fixture
def token_manager() -> MagicMock:
    tm = MagicMock()
    tm.encrypt.return_value = (b"encrypted_data", "key-1")
    tm.decrypt.return_value = {"api_key": "sk-123"}
    return tm


@pytest.fixture
def service(session: AsyncMock, token_manager: MagicMock) -> MCPIntegrationService:
    return MCPIntegrationService(session=session, token_manager=token_manager)


# ---------------------------------------------------------------------------
# list_mcp_servers
# ---------------------------------------------------------------------------


class TestListMCPServers:
    @pytest.mark.asyncio
    async def test_returns_servers(self, service: MCPIntegrationService, session: AsyncMock):
        servers = [_make_integration(), _make_integration(name="s2")]
        session.execute.return_value = _mock_scalars_result(servers)

        result = await service.list_mcp_servers(TENANT_ID)
        assert len(result) == 2
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_list(self, service: MCPIntegrationService, session: AsyncMock):
        session.execute.return_value = _mock_scalars_result([])
        result = await service.list_mcp_servers(TENANT_ID)
        assert result == []


# ---------------------------------------------------------------------------
# get_mcp_server
# ---------------------------------------------------------------------------


class TestGetMCPServer:
    @pytest.mark.asyncio
    async def test_found(self, service: MCPIntegrationService, session: AsyncMock):
        server = _make_integration()
        session.execute.return_value = _mock_scalar_result(server)

        result = await service.get_mcp_server(TENANT_ID, SERVER_ID)
        assert result is server

    @pytest.mark.asyncio
    async def test_not_found(self, service: MCPIntegrationService, session: AsyncMock):
        session.execute.return_value = _mock_scalar_result(None)
        result = await service.get_mcp_server(TENANT_ID, SERVER_ID)
        assert result is None


# ---------------------------------------------------------------------------
# create_mcp_server
# ---------------------------------------------------------------------------


class TestCreateMCPServer:
    @pytest.mark.asyncio
    async def test_create_http_no_auth(self, service: MCPIntegrationService, session: AsyncMock):
        result = await service.create_mcp_server(
            tenant_id=TENANT_ID,
            name="test-server",
            display_name="Test Server",
            description="A test",
            transport="http",
            url="http://localhost:8000/mcp",
            command=None,
            env=None,
            auth_type=IntegrationAuthType.NONE,
            credentials=None,
            enabled_by=USER_ID,
        )
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_stdio_transport(self, service: MCPIntegrationService, session: AsyncMock):
        await service.create_mcp_server(
            tenant_id=TENANT_ID,
            name="stdio-server",
            display_name="Stdio Server",
            description="Runs via subprocess",
            transport="stdio",
            url=None,
            command=["python", "server.py"],
            env={"API_KEY": "xxx"},
            auth_type=IntegrationAuthType.NONE,
            credentials=None,
            enabled_by=None,
        )
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_with_api_key_credential(
        self,
        service: MCPIntegrationService,
        session: AsyncMock,
        token_manager: MagicMock,
    ):
        # _upsert_credential will query for existing credential
        session.execute.return_value = _mock_scalar_result(None)

        await service.create_mcp_server(
            tenant_id=TENANT_ID,
            name="authed-server",
            display_name="Authed Server",
            description="With API key",
            transport="http",
            url="http://localhost:8000/mcp",
            command=None,
            env=None,
            auth_type=IntegrationAuthType.API_KEY,
            credentials={"api_key": "sk-123"},
            enabled_by=USER_ID,
        )
        token_manager.encrypt.assert_called_once_with({"api_key": "sk-123"})


# ---------------------------------------------------------------------------
# update_mcp_server
# ---------------------------------------------------------------------------


class TestUpdateMCPServer:
    @pytest.mark.asyncio
    async def test_update_display_name(self, service: MCPIntegrationService, session: AsyncMock):
        server = _make_integration()
        result = await service.update_mcp_server(server, display_name="New Name")
        assert server.display_name == "New Name"
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_description(self, service: MCPIntegrationService, session: AsyncMock):
        server = _make_integration()
        await service.update_mcp_server(server, description="Updated desc")
        assert server.oauth_config["description"] == "Updated desc"

    @pytest.mark.asyncio
    async def test_update_url_on_http_server(
        self, service: MCPIntegrationService, session: AsyncMock
    ):
        server = _make_integration(transport="http")
        await service.update_mcp_server(server, url="http://new-url.com/mcp")
        assert server.oauth_config["url"] == "http://new-url.com/mcp"

    @pytest.mark.asyncio
    async def test_update_url_on_stdio_server_raises(
        self, service: MCPIntegrationService, session: AsyncMock
    ):
        server = _make_integration(transport="stdio")
        server.oauth_config = {**server.oauth_config, "transport": "stdio"}
        with pytest.raises(ValueError, match="Cannot set URL"):
            await service.update_mcp_server(server, url="http://bad.com")

    @pytest.mark.asyncio
    async def test_update_command_on_http_server_raises(
        self, service: MCPIntegrationService, session: AsyncMock
    ):
        server = _make_integration(transport="http")
        with pytest.raises(ValueError, match="Cannot set command"):
            await service.update_mcp_server(server, command=["python", "x.py"])

    @pytest.mark.asyncio
    async def test_update_env_on_http_server_raises(
        self, service: MCPIntegrationService, session: AsyncMock
    ):
        server = _make_integration(transport="http")
        with pytest.raises(ValueError, match="Cannot set env"):
            await service.update_mcp_server(server, env={"K": "V"})

    @pytest.mark.asyncio
    async def test_update_status(self, service: MCPIntegrationService, session: AsyncMock):
        server = _make_integration()
        await service.update_mcp_server(server, status=IntegrationStatus.DISABLED)
        assert server.status == IntegrationStatus.DISABLED

    @pytest.mark.asyncio
    async def test_switch_to_none_auth_removes_credential(
        self, service: MCPIntegrationService, session: AsyncMock
    ):
        server = _make_integration(auth_type=IntegrationAuthType.API_KEY)
        existing_cred = MagicMock(spec=IntegrationCredential)
        existing_cred.deleted_at = None
        session.execute.return_value = _mock_scalar_result(existing_cred)

        await service.update_mcp_server(server, auth_type=IntegrationAuthType.NONE)
        assert existing_cred.deleted_at is not None

    @pytest.mark.asyncio
    async def test_change_auth_type_without_credentials_raises(
        self, service: MCPIntegrationService, session: AsyncMock
    ):
        server = _make_integration(auth_type=IntegrationAuthType.API_KEY)
        with pytest.raises(ValueError, match="Credentials are required"):
            await service.update_mcp_server(server, auth_type=IntegrationAuthType.BEARER_TOKEN)

    @pytest.mark.asyncio
    async def test_credentials_with_none_auth_raises(
        self, service: MCPIntegrationService, session: AsyncMock
    ):
        server = _make_integration(auth_type=IntegrationAuthType.NONE)
        with pytest.raises(ValueError, match="Cannot provide credentials"):
            await service.update_mcp_server(
                server,
                auth_type=IntegrationAuthType.NONE,
                credentials={"api_key": "sk-123"},
            )

    @pytest.mark.asyncio
    async def test_update_credentials_existing(
        self,
        service: MCPIntegrationService,
        session: AsyncMock,
        token_manager: MagicMock,
    ):
        server = _make_integration(auth_type=IntegrationAuthType.API_KEY)
        existing_cred = MagicMock(spec=IntegrationCredential)
        session.execute.return_value = _mock_scalar_result(existing_cred)

        await service.update_mcp_server(server, credentials={"api_key": "sk-new"})
        token_manager.encrypt.assert_called_with({"api_key": "sk-new"})
        assert existing_cred.encrypted_data == b"encrypted_data"

    @pytest.mark.asyncio
    async def test_update_command_on_stdio_server(
        self, service: MCPIntegrationService, session: AsyncMock
    ):
        server = _make_integration(transport="stdio")
        server.oauth_config = {**server.oauth_config, "transport": "stdio"}
        await service.update_mcp_server(server, command=["node", "new_server.js"])
        assert server.oauth_config["command"] == ["node", "new_server.js"]

    @pytest.mark.asyncio
    async def test_update_env_on_stdio_server(
        self, service: MCPIntegrationService, session: AsyncMock
    ):
        server = _make_integration(transport="stdio")
        server.oauth_config = {**server.oauth_config, "transport": "stdio"}
        await service.update_mcp_server(server, env={"NEW_VAR": "val"})
        assert server.oauth_config["env"] == {"NEW_VAR": "val"}


# ---------------------------------------------------------------------------
# delete_mcp_server
# ---------------------------------------------------------------------------


class TestDeleteMCPServer:
    @pytest.mark.asyncio
    async def test_soft_deletes_server_and_credentials(
        self, service: MCPIntegrationService, session: AsyncMock
    ):
        server = _make_integration()
        cred = MagicMock(spec=IntegrationCredential)
        cred.deleted_at = None
        session.execute.return_value = _mock_scalars_result([cred])

        await service.delete_mcp_server(server)
        assert server.deleted_at is not None
        assert server.status == IntegrationStatus.REVOKED
        assert cred.deleted_at is not None
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_credentials_to_delete(
        self, service: MCPIntegrationService, session: AsyncMock
    ):
        server = _make_integration()
        session.execute.return_value = _mock_scalars_result([])

        await service.delete_mcp_server(server)
        assert server.status == IntegrationStatus.REVOKED


# ---------------------------------------------------------------------------
# update_discovered_tools
# ---------------------------------------------------------------------------


class TestUpdateDiscoveredTools:
    @pytest.mark.asyncio
    async def test_success(self, service: MCPIntegrationService, session: AsyncMock):
        server = _make_integration()
        tools = [{"name": "tool1", "description": "Tool 1"}]

        await service.update_discovered_tools(server, tools)
        assert server.oauth_config["discovered_tools"] == tools
        assert server.oauth_config["last_connected_at"] is not None
        assert server.oauth_config["last_error"] is None

    @pytest.mark.asyncio
    async def test_with_error(self, service: MCPIntegrationService, session: AsyncMock):
        server = _make_integration()
        server.oauth_config["last_connected_at"] = "2024-01-01T00:00:00"

        await service.update_discovered_tools(server, [], error="Connection refused")
        assert server.oauth_config["last_error"] == "Connection refused"
        # last_connected_at preserved on error
        assert server.oauth_config["last_connected_at"] == "2024-01-01T00:00:00"


# ---------------------------------------------------------------------------
# get_server_credential
# ---------------------------------------------------------------------------


class TestGetServerCredential:
    @pytest.mark.asyncio
    async def test_found(
        self,
        service: MCPIntegrationService,
        session: AsyncMock,
        token_manager: MagicMock,
    ):
        server = _make_integration()
        cred = MagicMock(spec=IntegrationCredential)
        cred.encrypted_data = b"enc"
        cred.encryption_key_id = "key-1"
        session.execute.return_value = _mock_scalar_result(cred)

        result = await service.get_server_credential(server)
        token_manager.decrypt.assert_called_once_with(b"enc", "key-1")
        assert result == {"api_key": "sk-123"}

    @pytest.mark.asyncio
    async def test_not_found(self, service: MCPIntegrationService, session: AsyncMock):
        server = _make_integration()
        session.execute.return_value = _mock_scalar_result(None)

        result = await service.get_server_credential(server)
        assert result is None


# ---------------------------------------------------------------------------
# has_credential / has_credentials_batch
# ---------------------------------------------------------------------------


class TestHasCredential:
    @pytest.mark.asyncio
    async def test_has_credential_true(self, service: MCPIntegrationService, session: AsyncMock):
        server = _make_integration()
        session.execute.return_value = _mock_scalar_result(uuid4())

        assert await service.has_credential(server) is True

    @pytest.mark.asyncio
    async def test_has_credential_false(self, service: MCPIntegrationService, session: AsyncMock):
        server = _make_integration()
        session.execute.return_value = _mock_scalar_result(None)

        assert await service.has_credential(server) is False


class TestHasCredentialsBatch:
    @pytest.mark.asyncio
    async def test_empty_input(self, service: MCPIntegrationService, session: AsyncMock):
        result = await service.has_credentials_batch([])
        assert result == set()
        session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_set_of_ids(self, service: MCPIntegrationService, session: AsyncMock):
        id1, id2 = uuid4(), uuid4()
        session.execute.return_value = _mock_scalars_result([id1])

        result = await service.has_credentials_batch([id1, id2])
        assert result == {id1}


# ---------------------------------------------------------------------------
# get_active_mcp_servers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_mcp_service_logger():
    """Patch the logger to avoid KeyError from extra={'name': ...} in source code.

    Python's logging rejects 'name' in extra because it clashes with LogRecord.name.
    """
    with patch("empla.services.integrations.mcp_service.logger"):
        yield


class TestGetActiveMCPServers:
    @pytest.mark.asyncio
    async def test_no_auth_server(self, service: MCPIntegrationService, session: AsyncMock):
        server = _make_integration(auth_type=IntegrationAuthType.NONE)
        session.execute.return_value = _mock_scalars_result([server])

        configs = await service.get_active_mcp_servers(TENANT_ID)
        assert len(configs) == 1
        assert configs[0]["name"] == "test-server"
        assert configs[0]["transport"] == "http"
        assert "headers" not in configs[0]

    @pytest.mark.asyncio
    async def test_api_key_auth_server(
        self,
        service: MCPIntegrationService,
        session: AsyncMock,
        token_manager: MagicMock,
    ):
        server = _make_integration(auth_type=IntegrationAuthType.API_KEY)
        # First call: list servers; second call: get credential
        cred = MagicMock(spec=IntegrationCredential)
        cred.encrypted_data = b"enc"
        cred.encryption_key_id = "key-1"
        session.execute.side_effect = [
            _mock_scalars_result([server]),
            _mock_scalar_result(cred),
        ]
        token_manager.decrypt.return_value = {"api_key": "sk-test"}

        configs = await service.get_active_mcp_servers(TENANT_ID)
        assert len(configs) == 1
        assert configs[0]["headers"] == {"X-API-Key": "sk-test"}

    @pytest.mark.asyncio
    async def test_bearer_token_auth_server(
        self,
        service: MCPIntegrationService,
        session: AsyncMock,
        token_manager: MagicMock,
    ):
        server = _make_integration(auth_type=IntegrationAuthType.BEARER_TOKEN)
        cred = MagicMock(spec=IntegrationCredential)
        cred.encrypted_data = b"enc"
        cred.encryption_key_id = "key-1"
        session.execute.side_effect = [
            _mock_scalars_result([server]),
            _mock_scalar_result(cred),
        ]
        token_manager.decrypt.return_value = {"token": "tok-abc"}

        configs = await service.get_active_mcp_servers(TENANT_ID)
        assert len(configs) == 1
        assert configs[0]["headers"] == {"Authorization": "Bearer tok-abc"}

    @pytest.mark.asyncio
    async def test_oauth_server_skipped(self, service: MCPIntegrationService, session: AsyncMock):
        server = _make_integration(auth_type=IntegrationAuthType.OAUTH)
        session.execute.return_value = _mock_scalars_result([server])

        configs = await service.get_active_mcp_servers(TENANT_ID)
        assert len(configs) == 0

    @pytest.mark.asyncio
    async def test_decryption_error_skips_server(
        self,
        service: MCPIntegrationService,
        session: AsyncMock,
        token_manager: MagicMock,
    ):
        server = _make_integration(auth_type=IntegrationAuthType.API_KEY)
        cred = MagicMock(spec=IntegrationCredential)
        cred.encrypted_data = b"enc"
        cred.encryption_key_id = "key-1"
        session.execute.side_effect = [
            _mock_scalars_result([server]),
            # get_server_credential raises DecryptionError
            _mock_scalar_result(cred),
        ]
        token_manager.decrypt.side_effect = DecryptionError("bad key")

        # update_discovered_tools needs an execute call too
        session.execute.side_effect = [
            _mock_scalars_result([server]),
            _mock_scalar_result(cred),
        ]

        configs = await service.get_active_mcp_servers(TENANT_ID)
        assert len(configs) == 0

    @pytest.mark.asyncio
    async def test_no_credential_stored_skips_server(
        self,
        service: MCPIntegrationService,
        session: AsyncMock,
    ):
        server = _make_integration(auth_type=IntegrationAuthType.API_KEY)
        session.execute.side_effect = [
            _mock_scalars_result([server]),
            _mock_scalar_result(None),  # No credential found
        ]

        configs = await service.get_active_mcp_servers(TENANT_ID)
        assert len(configs) == 0

    @pytest.mark.asyncio
    async def test_malformed_credentials_skips_server(
        self,
        service: MCPIntegrationService,
        session: AsyncMock,
        token_manager: MagicMock,
    ):
        server = _make_integration(auth_type=IntegrationAuthType.API_KEY)
        cred = MagicMock(spec=IntegrationCredential)
        cred.encrypted_data = b"enc"
        cred.encryption_key_id = "key-1"
        session.execute.side_effect = [
            _mock_scalars_result([server]),
            _mock_scalar_result(cred),
        ]
        token_manager.decrypt.return_value = {"wrong_key": "val"}  # Missing api_key

        configs = await service.get_active_mcp_servers(TENANT_ID)
        assert len(configs) == 0

    @pytest.mark.asyncio
    async def test_stdio_transport_server(self, service: MCPIntegrationService, session: AsyncMock):
        server = _make_integration(
            auth_type=IntegrationAuthType.NONE,
            transport="stdio",
        )
        server.oauth_config = {
            **server.oauth_config,
            "transport": "stdio",
            "command": ["python", "server.py"],
            "env": {"KEY": "val"},
        }
        session.execute.return_value = _mock_scalars_result([server])

        configs = await service.get_active_mcp_servers(TENANT_ID)
        assert len(configs) == 1
        assert configs[0]["transport"] == "stdio"
        assert configs[0]["command"] == ["python", "server.py"]
        assert configs[0]["env"] == {"KEY": "val"}


# ---------------------------------------------------------------------------
# _upsert_credential edge cases
# ---------------------------------------------------------------------------


class TestUpsertCredential:
    @pytest.mark.asyncio
    async def test_encrypt_raises_no_keys(
        self,
        service: MCPIntegrationService,
        session: AsyncMock,
        token_manager: MagicMock,
    ):
        server = _make_integration()
        session.execute.return_value = _mock_scalar_result(None)
        token_manager.encrypt.side_effect = NoKeysConfiguredError("no keys")

        with pytest.raises(NoKeysConfiguredError):
            await service._upsert_credential(
                server, IntegrationAuthType.API_KEY, {"api_key": "sk-123"}
            )

    @pytest.mark.asyncio
    async def test_encrypt_raises_value_error(
        self,
        service: MCPIntegrationService,
        session: AsyncMock,
        token_manager: MagicMock,
    ):
        server = _make_integration()
        session.execute.return_value = _mock_scalar_result(None)
        token_manager.encrypt.side_effect = TypeError("not serializable")

        with pytest.raises(ValueError, match="Invalid credential data"):
            await service._upsert_credential(server, IntegrationAuthType.API_KEY, {"bad": object()})

    @pytest.mark.asyncio
    async def test_none_auth_no_existing_credential(
        self,
        service: MCPIntegrationService,
        session: AsyncMock,
    ):
        """Switching to 'none' with no existing credential is a no-op."""
        server = _make_integration()
        session.execute.return_value = _mock_scalar_result(None)

        await service._upsert_credential(server, IntegrationAuthType.NONE, {})
        # No error, nothing soft-deleted

    @pytest.mark.asyncio
    async def test_creates_new_credential(
        self,
        service: MCPIntegrationService,
        session: AsyncMock,
        token_manager: MagicMock,
    ):
        server = _make_integration()
        session.execute.return_value = _mock_scalar_result(None)

        await service._upsert_credential(server, IntegrationAuthType.API_KEY, {"api_key": "sk-123"})
        session.add.assert_called()
