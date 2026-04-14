"""
empla.api.v1.endpoints.tools - Per-Employee Tool Catalog + Health

Read-only endpoints that proxy to the runner subprocess's HealthServer
(empla.runner.health). No new in-process state — this re-uses the same
``EmployeeManager.get_health_port`` lookup that ``/wake`` uses (PR #74).

If the employee runner is offline, the endpoints return 503 with a
machine-readable reason rather than 500 — the dashboard renders a
"Employee not running" empty state instead of a generic error.
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from empla.api.deps import CurrentUser, DBSession
from empla.api.v1.schemas.tools import (
    BlockedToolsResponse,
    IntegrationHealthResponse,
    ToolCatalogResponse,
)
from empla.models.employee import Employee
from empla.services.employee_manager import get_employee_manager

logger = logging.getLogger(__name__)

router = APIRouter()

_PROXY_TIMEOUT_SECONDS = 5.0

# Tool names are namespaced ("integration.tool_name") and the only chars
# allowed in our integration registries are A-Z, a-z, 0-9, underscore,
# dot, and hyphen. The strict allowlist also blocks ?, #, %, /, \, ..
# and other characters that could change URL semantics when interpolated
# into the proxy URL or fool the runner's path-prefix dispatch.
_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]+$")
# `blocked` would collide with the runner's /tools/blocked route — reserved.
_RESERVED_TOOL_NAMES = {"blocked"}


async def _verify_employee(db: DBSession, employee_id: UUID, tenant_id: UUID) -> None:
    """Verify employee exists and belongs to tenant."""
    result = await db.execute(
        select(Employee.id).where(
            Employee.id == employee_id,
            Employee.tenant_id == tenant_id,
            Employee.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )


async def _proxy_runner_get(request: Request, employee_id: UUID, path: str) -> dict:
    """
    GET ``path`` against the employee runner's health server.

    Uses the long-lived ``app.state.runner_proxy_client`` (set up in the
    FastAPI lifespan) so we don't pay TCP+transport setup per request.
    Sends the per-runner shared secret in the X-Runner-Token header so
    the runner accepts the call (only /health is unauthenticated).
    """
    manager = get_employee_manager()
    port = manager.get_health_port(employee_id)
    if port is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Employee runner is not running — start the employee to see tool data.",
        )

    token = manager.get_health_token(employee_id)
    headers = {"X-Runner-Token": token} if token else {}

    url = f"http://127.0.0.1:{port}{path}"
    # Tests construct endpoints without going through the FastAPI lifespan,
    # so the shared client may be missing — fall back to a per-call client.
    shared = getattr(request.app.state, "runner_proxy_client", None) if request else None
    client = shared if shared is not None else httpx.AsyncClient(timeout=_PROXY_TIMEOUT_SECONDS)
    own_client = shared is None
    try:
        try:
            resp = await client.get(url, headers=headers, timeout=_PROXY_TIMEOUT_SECONDS)
        except httpx.ConnectError as e:
            logger.warning(
                "Tools proxy connection refused for employee %s on port %s: %s",
                employee_id,
                port,
                e,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Employee runner is not reachable.",
            ) from e
        except httpx.TimeoutException as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=f"Employee runner did not respond within {int(_PROXY_TIMEOUT_SECONDS)}s.",
            ) from e
        except httpx.HTTPError as e:
            logger.warning("Tools proxy HTTP error for employee %s: %s", employee_id, e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to reach employee runner.",
            ) from e

        if resp.status_code == 401:
            # Should never happen in production — token is set at runner spawn.
            # Means token mismatch / out-of-band runner. Surface as 502.
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Runner rejected proxy token.",
            )
        if resp.status_code == 503:
            # Runner running but tools introspection not enabled (no tool_router wired)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Tools introspection is not enabled for this runner.",
            )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Runner returned {resp.status_code} for {path}",
            )

        try:
            return resp.json()
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Runner returned malformed JSON.",
            ) from e
    finally:
        if own_client:
            await client.aclose()


# =========================================================================
# Endpoints
# =========================================================================


@router.get("/{employee_id}/tools", response_model=ToolCatalogResponse)
async def list_tools(
    request: Request,
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> ToolCatalogResponse:
    """List the tools this employee can call (proxied from the runner)."""
    await _verify_employee(db, employee_id, auth.tenant_id)
    payload = await _proxy_runner_get(request, employee_id, "/tools")
    return ToolCatalogResponse.model_validate(payload)


@router.get(
    "/{employee_id}/tools/blocked",
    response_model=BlockedToolsResponse,
)
async def list_blocked_tools(
    request: Request,
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> BlockedToolsResponse:
    """List trust-boundary blocks observed in the runner's current cycle."""
    await _verify_employee(db, employee_id, auth.tenant_id)
    payload = await _proxy_runner_get(request, employee_id, "/tools/blocked")
    return BlockedToolsResponse.model_validate(payload)


@router.get(
    "/{employee_id}/tools/{tool_name}/health",
    response_model=IntegrationHealthResponse,
)
async def get_tool_health(
    request: Request,
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
    tool_name: str,
) -> IntegrationHealthResponse:
    """Per-integration health for the integration that owns *tool_name*."""
    if (
        not tool_name
        or not _TOOL_NAME_PATTERN.match(tool_name)
        or tool_name in _RESERVED_TOOL_NAMES
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tool_name",
        )
    await _verify_employee(db, employee_id, auth.tenant_id)
    payload = await _proxy_runner_get(request, employee_id, f"/tools/{tool_name}/health")
    return IntegrationHealthResponse.model_validate(payload)
