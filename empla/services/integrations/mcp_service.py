"""
empla.services.integrations.mcp_service - MCP Server Integration Service

CRUD operations for MCP server configurations stored as integrations.
MCP servers are represented as Integration rows with integration_type='mcp_server'.
Credentials (API keys, bearer tokens, OAuth client secrets) are stored
encrypted in IntegrationCredential with employee_id=NULL (tenant-level).
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.integration import Integration, IntegrationCredential
from empla.services.integrations.key_provider import NoKeysConfiguredError
from empla.services.integrations.token_manager import DecryptionError, TokenManager

logger = logging.getLogger(__name__)


def _resolve_credential_type(auth_type: str) -> str:
    """Map auth_type to the credential_type stored in IntegrationCredential."""
    if auth_type == "api_key":
        return "api_key"
    if auth_type == "oauth":
        return "oauth_tokens"
    return "bearer_token"


def build_auth_headers(auth_type: str, cred_data: dict[str, Any]) -> dict[str, str]:
    """Build HTTP auth headers from decrypted credential data.

    Raises:
        ValueError: If the credential data is missing the expected key.
    """
    headers: dict[str, str] = {}
    if auth_type == "api_key":
        api_key = cred_data.get("api_key")
        if not api_key:
            raise ValueError("api_key auth configured but credential data has no 'api_key' key")
        headers["X-API-Key"] = api_key
    elif auth_type == "bearer_token":
        token = cred_data.get("token")
        if not token:
            raise ValueError("bearer_token auth configured but credential data has no 'token' key")
        headers["Authorization"] = f"Bearer {token}"
    return headers


class MCPIntegrationService:
    """Manages MCP server integrations for a tenant."""

    def __init__(self, session: AsyncSession, token_manager: TokenManager) -> None:
        self.session = session
        self.token_manager = token_manager

    async def list_mcp_servers(self, tenant_id: UUID) -> list[Integration]:
        """List all MCP server integrations for a tenant."""
        result = await self.session.execute(
            select(Integration)
            .where(
                Integration.tenant_id == tenant_id,
                Integration.integration_type == "mcp_server",
                Integration.deleted_at.is_(None),
            )
            .order_by(Integration.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_mcp_server(self, tenant_id: UUID, server_id: UUID) -> Integration | None:
        """Get a single MCP server integration by ID."""
        result = await self.session.execute(
            select(Integration).where(
                Integration.id == server_id,
                Integration.tenant_id == tenant_id,
                Integration.integration_type == "mcp_server",
                Integration.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create_mcp_server(
        self,
        *,
        tenant_id: UUID,
        name: str,
        display_name: str,
        description: str,
        transport: str,
        url: str | None,
        command: list[str] | None,
        env: dict[str, str] | None,
        auth_type: str,
        credentials: dict[str, Any] | None,
        enabled_by: UUID | None,
    ) -> Integration:
        """Create an MCP server integration with optional encrypted credentials."""
        oauth_config: dict[str, Any] = {
            "transport": transport,
            "name": name,
            "description": description,
            "discovered_tools": [],
            "last_connected_at": None,
            "last_error": None,
        }
        if transport == "http" and url:
            oauth_config["url"] = url
        elif transport == "stdio" and command:
            oauth_config["command"] = command
            if env:
                oauth_config["env"] = env

        integration = Integration(
            tenant_id=tenant_id,
            integration_type="mcp_server",
            provider=name,
            auth_type=auth_type,
            display_name=display_name,
            oauth_config=oauth_config,
            use_platform_credentials=False,
            status="active",
            enabled_by=enabled_by,
            enabled_at=datetime.now(UTC),
        )
        self.session.add(integration)
        await self.session.flush()

        # Store encrypted credentials if provided
        if credentials and auth_type != "none":
            credential_type = _resolve_credential_type(auth_type)

            try:
                encrypted, key_id = self.token_manager.encrypt(credentials)
            except NoKeysConfiguredError:
                raise
            except Exception as e:
                raise ValueError(f"Failed to encrypt credentials: {e}") from e
            cred = IntegrationCredential(
                tenant_id=tenant_id,
                integration_id=integration.id,
                employee_id=None,
                credential_type=credential_type,
                encrypted_data=encrypted,
                encryption_key_id=key_id,
                token_metadata={"auth_type": auth_type},
                status="active",
                issued_at=datetime.now(UTC),
            )
            self.session.add(cred)

        await self.session.commit()
        await self.session.refresh(integration)

        logger.info(
            "Created MCP server integration",
            extra={
                "server_id": str(integration.id),
                "name": name,
                "transport": transport,
                "auth_type": auth_type,
            },
        )
        return integration

    async def update_mcp_server(
        self,
        server: Integration,
        *,
        display_name: str | None = None,
        description: str | None = None,
        url: str | None = None,
        command: list[str] | None = None,
        env: dict[str, str] | None = None,
        auth_type: str | None = None,
        credentials: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> Integration:
        """Update an MCP server integration."""
        config = dict(server.oauth_config)

        if display_name is not None:
            server.display_name = display_name
        if description is not None:
            config["description"] = description
        if url is not None:
            config["url"] = url
        if command is not None:
            config["command"] = command
        if env is not None:
            config["env"] = env
        if status is not None:
            server.status = status

        server.oauth_config = config

        # Update auth_type and credentials if changed
        if auth_type is not None:
            server.auth_type = auth_type

        if credentials is not None:
            effective_auth = auth_type or server.auth_type
            await self._upsert_credential(server, effective_auth, credentials)

        await self.session.commit()
        await self.session.refresh(server)

        logger.info(
            "Updated MCP server integration",
            extra={"server_id": str(server.id), "name": server.provider},
        )
        return server

    async def _upsert_credential(
        self,
        server: Integration,
        auth_type: str,
        credentials: dict[str, Any],
    ) -> None:
        """Create or update tenant-level credential for an MCP server."""
        # Find existing tenant-level credential
        result = await self.session.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.integration_id == server.id,
                IntegrationCredential.employee_id.is_(None),
                IntegrationCredential.deleted_at.is_(None),
            )
        )
        existing = result.scalar_one_or_none()

        if auth_type == "none":
            # Remove credential if switching to no auth
            if existing:
                existing.deleted_at = datetime.now(UTC)
            return

        credential_type = _resolve_credential_type(auth_type)

        try:
            encrypted, key_id = self.token_manager.encrypt(credentials)
        except Exception as e:
            raise ValueError(f"Failed to encrypt credentials: {e}") from e

        if existing:
            existing.credential_type = credential_type
            existing.encrypted_data = encrypted
            existing.encryption_key_id = key_id
            existing.token_metadata = {"auth_type": auth_type}
            existing.status = "active"
        else:
            cred = IntegrationCredential(
                tenant_id=server.tenant_id,
                integration_id=server.id,
                employee_id=None,
                credential_type=credential_type,
                encrypted_data=encrypted,
                encryption_key_id=key_id,
                token_metadata={"auth_type": auth_type},
                status="active",
                issued_at=datetime.now(UTC),
            )
            self.session.add(cred)

    async def delete_mcp_server(self, server: Integration) -> None:
        """Soft-delete an MCP server integration and its credentials."""
        now = datetime.now(UTC)
        server.deleted_at = now
        server.status = "revoked"

        # Soft-delete tenant-level credentials
        result = await self.session.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.integration_id == server.id,
                IntegrationCredential.deleted_at.is_(None),
            )
        )
        for cred in result.scalars().all():
            cred.deleted_at = now

        await self.session.commit()

        logger.info(
            "Deleted MCP server integration",
            extra={"server_id": str(server.id), "name": server.provider},
        )

    async def update_discovered_tools(
        self,
        server: Integration,
        tools: list[dict[str, str]],
        error: str | None = None,
    ) -> None:
        """Update discovered tools and connection status after a test."""
        config = dict(server.oauth_config)
        config["discovered_tools"] = tools
        config["last_connected_at"] = (
            datetime.now(UTC).isoformat() if not error else config.get("last_connected_at")
        )
        config["last_error"] = error
        server.oauth_config = config

        await self.session.commit()
        await self.session.refresh(server)

    async def get_server_credential(self, server: Integration) -> dict[str, Any] | None:
        """Decrypt and return the tenant-level credential for an MCP server.

        Returns:
            Decrypted credential dict, or None if no credential exists.

        Raises:
            DecryptionError: If the credential exists but cannot be decrypted.
        """
        result = await self.session.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.integration_id == server.id,
                IntegrationCredential.employee_id.is_(None),
                IntegrationCredential.deleted_at.is_(None),
                IntegrationCredential.status == "active",
            )
        )
        cred = result.scalar_one_or_none()
        if not cred:
            return None

        return self.token_manager.decrypt(cred.encrypted_data, cred.encryption_key_id)

    async def has_credential(self, server: Integration) -> bool:
        """Check if an MCP server has a tenant-level credential."""
        result = await self.session.execute(
            select(IntegrationCredential.id).where(
                IntegrationCredential.integration_id == server.id,
                IntegrationCredential.employee_id.is_(None),
                IntegrationCredential.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_active_mcp_servers(self, tenant_id: UUID) -> list[dict[str, Any]]:
        """Get active MCP servers with decrypted configs for employee runtime.

        Returns a list of dicts suitable for constructing MCPServerConfig objects,
        with auth headers pre-computed from decrypted credentials.
        """
        servers = await self.list_mcp_servers(tenant_id)
        configs: list[dict[str, Any]] = []

        for server in servers:
            if server.status != "active":
                continue

            config = dict(server.oauth_config)
            entry: dict[str, Any] = {
                "name": config.get("name", server.provider),
                "transport": config.get("transport", "http"),
            }

            if entry["transport"] == "http":
                entry["url"] = config.get("url")
            elif entry["transport"] == "stdio":
                entry["command"] = config.get("command")
                entry["env"] = config.get("env", {})

            # Resolve auth headers from credentials
            headers: dict[str, str] = {}
            if server.auth_type in ("api_key", "bearer_token"):
                try:
                    cred_data = await self.get_server_credential(server)
                except DecryptionError:
                    logger.error(
                        "Skipping MCP server due to credential decryption failure",
                        extra={"server_id": str(server.id), "name": server.provider},
                        exc_info=True,
                    )
                    await self.update_discovered_tools(
                        server, [], error="Credential decryption failed"
                    )
                    continue
                if cred_data:
                    try:
                        headers = build_auth_headers(server.auth_type, cred_data)
                    except ValueError:
                        logger.error(
                            "Skipping MCP server due to malformed credentials",
                            extra={"server_id": str(server.id), "name": server.provider},
                            exc_info=True,
                        )
                        await self.update_discovered_tools(
                            server, [], error="Credential data malformed"
                        )
                        continue

            if headers:
                entry["headers"] = headers

            configs.append(entry)

        return configs
