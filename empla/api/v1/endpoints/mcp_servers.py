"""
empla.api.v1.endpoints.mcp_servers - MCP Server Management Endpoints

CRUD endpoints for managing MCP server integrations.
Admins can add, configure, test, and remove external MCP servers that
provide tools to all employees in the tenant.
"""

import logging
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from empla.api.deps import CurrentUser, DBSession, RequireAdmin
from empla.api.v1.schemas.mcp_server import (
    MCPServerCreate,
    MCPServerListResponse,
    MCPServerResponse,
    MCPServerTestRequest,
    MCPServerTestResponse,
    MCPServerUpdate,
    MCPToolInfo,
    validate_url_dns_safety,
)
from empla.models.integration import Integration
from empla.services.integrations import NoKeysConfiguredError
from empla.services.integrations.mcp_service import MCPIntegrationService
from empla.services.integrations.token_manager import DecryptionError, get_token_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_service(db: DBSession) -> MCPIntegrationService:
    """Create an MCPIntegrationService with the current DB session.

    Raises:
        HTTPException(503): If encryption keys are not configured.
    """
    try:
        return MCPIntegrationService(db, get_token_manager())
    except NoKeysConfiguredError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Integration service is not configured. Contact your administrator.",
        ) from e


def _server_to_response(server: Integration, has_credentials: bool = False) -> MCPServerResponse:
    """Convert an Integration ORM object to MCPServerResponse."""
    config = server.oauth_config or {}
    tools_raw = config.get("discovered_tools", [])
    tools = [
        MCPToolInfo(name=t.get("name", ""), description=t.get("description", "")) for t in tools_raw
    ]

    return MCPServerResponse(
        id=server.id,
        name=config.get("name", server.provider),
        display_name=server.display_name,
        description=config.get("description", ""),
        transport=config.get("transport", "http"),
        url=config.get("url"),
        command=config.get("command"),
        auth_type=server.auth_type,
        has_credentials=has_credentials,
        status=server.status,
        discovered_tools=tools,
        last_connected_at=config.get("last_connected_at"),
        last_error=config.get("last_error"),
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


@router.get("", response_model=MCPServerListResponse)
async def list_mcp_servers(db: DBSession, auth: CurrentUser) -> MCPServerListResponse:
    """List all MCP servers for the current tenant."""
    service = _get_service(db)
    servers = await service.list_mcp_servers(auth.tenant_id)

    cred_ids = await service.has_credentials_batch([s.id for s in servers])
    items = [_server_to_response(s, s.id in cred_ids) for s in servers]

    return MCPServerListResponse(items=items, total=len(items))


@router.post("", response_model=MCPServerResponse, status_code=status.HTTP_201_CREATED)
async def create_mcp_server(
    body: MCPServerCreate, db: DBSession, auth: RequireAdmin
) -> MCPServerResponse:
    """Create a new MCP server integration (admin only)."""
    if body.url:
        try:
            await validate_url_dns_safety(body.url)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    service = _get_service(db)

    try:
        server = await service.create_mcp_server(
            tenant_id=auth.tenant_id,
            name=body.name,
            display_name=body.display_name,
            description=body.description,
            transport=body.transport,
            url=body.url,
            command=body.command,
            env=body.env,
            auth_type=body.auth_type,
            credentials=body.credentials,
            enabled_by=auth.user_id,
        )
    except IntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"MCP server with name '{body.name}' already exists",
        ) from e

    has_creds = await service.has_credential(server)
    logger.info(
        "Created MCP server via API",
        extra={"server_id": str(server.id), "name": body.name, "tenant_id": str(auth.tenant_id)},
    )
    return _server_to_response(server, has_creds)


@router.post("/test", response_model=MCPServerTestResponse)
async def test_mcp_server_unsaved(
    body: MCPServerTestRequest,
    db: DBSession,  # noqa: ARG001 - required by FastAPI for auth chain
    auth: RequireAdmin,  # noqa: ARG001 - required by FastAPI for auth chain
) -> MCPServerTestResponse:
    """Test an MCP server connection without saving (admin only).

    Connects temporarily, discovers tools, and disconnects.
    """
    if body.url:
        try:
            await validate_url_dns_safety(body.url)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return await _test_connection(
        transport=body.transport,
        url=body.url,
        command=body.command,
        env=body.env,
        auth_type=body.auth_type,
        credentials=body.credentials,
    )


@router.get("/{server_id}", response_model=MCPServerResponse)
async def get_mcp_server(server_id: UUID, db: DBSession, auth: CurrentUser) -> MCPServerResponse:
    """Get a single MCP server by ID."""
    service = _get_service(db)
    server = await service.get_mcp_server(auth.tenant_id, server_id)
    if not server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")

    has_creds = await service.has_credential(server)
    return _server_to_response(server, has_creds)


@router.put("/{server_id}", response_model=MCPServerResponse)
async def update_mcp_server(
    server_id: UUID, body: MCPServerUpdate, db: DBSession, auth: RequireAdmin
) -> MCPServerResponse:
    """Update an MCP server integration (admin only)."""
    if body.url is not None:
        try:
            await validate_url_dns_safety(body.url)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    service = _get_service(db)
    server = await service.get_mcp_server(auth.tenant_id, server_id)
    if not server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")

    try:
        server = await service.update_mcp_server(
            server,
            display_name=body.display_name,
            description=body.description,
            url=body.url,
            command=body.command,
            env=body.env,
            auth_type=body.auth_type,
            credentials=body.credentials,
            status=body.status,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    has_creds = await service.has_credential(server)
    logger.info(
        "Updated MCP server via API",
        extra={"server_id": str(server.id), "tenant_id": str(auth.tenant_id)},
    )
    return _server_to_response(server, has_creds)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(server_id: UUID, db: DBSession, auth: RequireAdmin) -> None:
    """Soft-delete an MCP server integration (admin only)."""
    service = _get_service(db)
    server = await service.get_mcp_server(auth.tenant_id, server_id)
    if not server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")

    await service.delete_mcp_server(server)
    logger.info(
        "Deleted MCP server via API",
        extra={"server_id": str(server.id), "tenant_id": str(auth.tenant_id)},
    )


@router.post("/{server_id}/test-connection", response_model=MCPServerTestResponse)
async def test_mcp_server_connection(
    server_id: UUID, db: DBSession, auth: RequireAdmin
) -> MCPServerTestResponse:
    """Test a saved MCP server's connection and refresh discovered tools (admin only)."""
    service = _get_service(db)
    server = await service.get_mcp_server(auth.tenant_id, server_id)
    if not server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")

    config = server.oauth_config or {}

    # Resolve credentials from DB
    credentials: dict | None = None
    if server.auth_type != "none":
        try:
            credentials = await service.get_server_credential(server)
        except DecryptionError as e:
            logger.error(
                "Failed to decrypt MCP server credentials",
                extra={"server_id": str(server_id)},
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to decrypt server credentials. Contact your administrator.",
            ) from e
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Server requires '{server.auth_type}' authentication but no credentials are stored. "
                "Update the server configuration to add credentials.",
            )

    result = await _test_connection(
        transport=config.get("transport", "http"),
        url=config.get("url"),
        command=config.get("command"),
        env=config.get("env"),
        auth_type=server.auth_type,
        credentials=credentials,
    )

    # Persist discovered tools
    if result.success:
        tools = [{"name": n, "description": ""} for n in result.tool_names]
        await service.update_discovered_tools(server, tools)
    else:
        await service.update_discovered_tools(server, [], error=result.error)

    return result


async def _test_connection(
    *,
    transport: str,
    url: str | None,
    command: list[str] | None,
    env: dict[str, str] | None,
    auth_type: str,
    credentials: dict | None,
) -> MCPServerTestResponse:
    """Connect to an MCP server temporarily, discover tools, disconnect."""
    # Sanitize URL for logging (strip userinfo, query, fragment)
    safe_url: str | None = None
    if url:
        parsed = urlparse(url)
        safe_url = f"{parsed.scheme}://{parsed.hostname}{':' + str(parsed.port) if parsed.port else ''}{parsed.path}"

    # Build headers from credentials
    headers: dict[str, str] = {}
    if auth_type == "oauth":
        return MCPServerTestResponse(
            success=False,
            error="OAuth authentication requires an interactive authorization flow. "
            "Save the server first, then complete the OAuth flow to test.",
        )
    if credentials and auth_type in ("api_key", "bearer_token"):
        from empla.services.integrations.mcp_service import build_auth_headers

        try:
            headers = build_auth_headers(auth_type, credentials)
        except ValueError as e:
            return MCPServerTestResponse(success=False, error=str(e))

    bridge = None
    try:
        from empla.core.tools.mcp_bridge import MCPBridge, MCPServerConfig
        from empla.core.tools.registry import ToolRegistry

        registry = ToolRegistry()
        bridge = MCPBridge(registry)

        config = MCPServerConfig(
            name="__test__",
            transport=transport,
            url=url,
            command=command,
            env=env or {},
            headers=headers,
        )
        tool_names = await bridge.connect(config)
        clean_names = [n.replace("__test__.", "") for n in tool_names]

        return MCPServerTestResponse(
            success=True,
            tools_discovered=len(clean_names),
            tool_names=clean_names,
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.warning(
            "MCP server test connection failed",
            extra={"transport": transport, "url": safe_url, "error": str(e)},
        )
        return MCPServerTestResponse(success=False, error=str(e))
    except ImportError as e:
        logger.error("MCP package not available for test", exc_info=True)
        return MCPServerTestResponse(
            success=False,
            error=f"MCP support not installed: {e}",
        )
    except Exception as e:
        logger.error(
            "Unexpected error during MCP server test",
            extra={"transport": transport, "url": safe_url},
            exc_info=True,
        )
        return MCPServerTestResponse(success=False, error=f"Unexpected error: {type(e).__name__}")
    finally:
        if bridge is not None:
            try:
                await bridge.disconnect("__test__")
            except Exception:
                logger.warning("Error during cleanup after MCP test", exc_info=True)
