"""
empla.api.v1.endpoints.webhooks - External Webhook Receiver

Public endpoints that receive webhooks from integration providers
(HubSpot, Google Calendar, etc.) and wake the relevant employee
subprocesses so they process the event in their next BDI cycle.

Authentication: X-Webhook-Token header (per-tenant, stored in
Integration.oauth_config["webhook_token"]). Provider-specific HMAC
signature verification can be added per provider.

Flow:
  External provider → POST /api/v1/webhooks/{provider} (X-Webhook-Token header)
  → validate token against Integration table
  → find active employees for that tenant
  → EmployeeManager.wake_employee() for each
  → employee loop wakes, drains events, injects as observations
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from empla.api.deps import DBSession
from empla.api.v1.schemas.webhook import WebhookEvent, WebhookResponse
from empla.models.employee import Employee
from empla.models.integration import Integration
from empla.services.employee_manager import get_employee_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# Provider-specific event type extractors.
# Each returns (event_type, summary) from the raw payload.
_PROVIDER_PARSERS: dict[str, Any] = {}


def _parse_hubspot(payload: dict[str, Any] | list[Any]) -> tuple[str, str]:
    """Extract event type and summary from HubSpot webhook payload."""
    # HubSpot sends an array of events; take the first
    events = payload if isinstance(payload, list) else [payload]
    if not events:
        return "unknown", ""
    event = events[0] if isinstance(events[0], dict) else {}
    sub_type = event.get("subscriptionType", "unknown")
    object_id = event.get("objectId", "")
    return sub_type, f"objectId={object_id}" if object_id else ""


def _parse_google(payload: dict[str, Any]) -> tuple[str, str]:
    """Extract event type and summary from Google push notification."""
    resource_type = payload.get("resourceType", "unknown")
    change_type = payload.get("changeType", "unknown")
    return f"{resource_type}.{change_type}", ""


def _parse_generic(payload: dict[str, Any]) -> tuple[str, str]:
    """Fallback parser for unknown providers."""
    return payload.get("event_type", "unknown"), payload.get("summary", "")


_PROVIDER_PARSERS = {
    "hubspot": _parse_hubspot,
    "google_workspace": _parse_google,
    "google_calendar": _parse_google,
}


async def _find_tenant_by_webhook_token(db: DBSession, provider: str, token: str) -> UUID | None:
    """Look up the tenant that owns this webhook token.

    The token is stored in Integration.oauth_config["webhook_token"].
    Returns the tenant_id or None if not found.
    """
    # Use JSONB containment to find the integration with this webhook_token
    result = await db.execute(
        select(Integration.tenant_id).where(
            Integration.provider == provider,
            Integration.oauth_config["webhook_token"].astext == token,
            Integration.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def _find_active_employees(db: DBSession, tenant_id: UUID) -> list[UUID]:
    """Find all active employees for a tenant."""
    result = await db.execute(
        select(Employee.id).where(
            Employee.tenant_id == tenant_id,
            Employee.status == "active",
            Employee.deleted_at.is_(None),
        )
    )
    return list(result.scalars().all())


@router.post(
    "/{provider}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
)
async def receive_webhook(
    db: DBSession,
    request: Request,
    provider: str,
    x_webhook_token: str = Header(description="Webhook authentication token"),
) -> WebhookResponse:
    """Receive a webhook from an external integration provider.

    This is a public endpoint (no JWT) — external providers authenticate
    via the X-Webhook-Token header (avoids leaking secrets in URL/logs).

    The endpoint:
    1. Validates the token against the Integration table
    2. Parses the provider-specific payload
    3. Wakes all active employees for the tenant
    """
    # Validate webhook token
    tenant_id = await _find_tenant_by_webhook_token(db, provider, x_webhook_token)
    if tenant_id is None:
        logger.warning(
            "Webhook received with invalid token",
            extra={"provider": provider},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token",
        )

    # Parse raw payload — fail loudly so providers retry on malformed bodies
    try:
        raw_payload = await request.json()
    except Exception as exc:
        logger.warning(
            "Failed to parse webhook payload as JSON",
            exc_info=True,
            extra={"provider": provider},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    # Extract event type and summary using provider-specific parser
    parser = _PROVIDER_PARSERS.get(provider, _parse_generic)
    event_type, summary = parser(raw_payload)

    # Build normalized event
    event = WebhookEvent(
        provider=provider,
        event_type=event_type,
        summary=summary,
        payload=raw_payload if isinstance(raw_payload, dict) else {"raw": raw_payload},
        received_at=datetime.now(UTC),
    )

    # Find active employees for this tenant and wake them
    employee_ids = await _find_active_employees(db, tenant_id)
    if not employee_ids:
        logger.info(
            "Webhook received but no active employees for tenant",
            extra={"provider": provider, "tenant_id": str(tenant_id)},
        )
        return WebhookResponse(status="accepted", employees_notified=0)

    manager = get_employee_manager()
    event_dict = event.model_dump(mode="json")
    notified = 0
    for emp_id in employee_ids:
        if await manager.wake_employee(emp_id, event_dict):
            notified += 1

    if notified == 0 and employee_ids:
        logger.error(
            "Webhook accepted but ALL employee wake attempts failed — event may be lost",
            extra={
                "provider": provider,
                "event_type": event_type,
                "tenant_id": str(tenant_id),
                "employees_found": len(employee_ids),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No employees reachable",
        )

    logger.info(
        "Webhook processed",
        extra={
            "provider": provider,
            "event_type": event_type,
            "tenant_id": str(tenant_id),
            "employees_found": len(employee_ids),
            "employees_notified": notified,
        },
    )

    return WebhookResponse(status="accepted", employees_notified=notified)
