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
  → find employees that have credentials for this provider
  → EmployeeManager.wake_employee() for each
  → employee loop wakes, drains events, injects as observations

Employee routing:
  Only employees with an active IntegrationCredential for the webhook's
  provider are woken. This is the direct, predictable link: if an employee
  has a credential for HubSpot, they get HubSpot webhooks. Tenant-level
  credentials (employee_id IS NULL) wake all active employees.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Path, Request, status
from sqlalchemy import select

from empla.api.deps import DBSession
from empla.api.v1.schemas.webhook import WebhookEvent, WebhookResponse
from empla.models.employee import Employee
from empla.models.integration import Integration, IntegrationCredential
from empla.services.employee_manager import get_employee_manager

logger = logging.getLogger(__name__)

router = APIRouter()


async def _find_tenant_by_webhook_token(db: DBSession, provider: str, token: str) -> UUID | None:
    """Look up the tenant that owns this webhook token.

    The token is stored in Integration.oauth_config["webhook_token"].
    Uses constant-time comparison to prevent timing side-channel attacks
    (this is the sole auth mechanism on a public endpoint).
    """
    import hmac

    result = await db.execute(
        select(Integration.tenant_id, Integration.oauth_config["webhook_token"].astext).where(
            Integration.provider == provider,
            Integration.status == "active",
            Integration.oauth_config["webhook_token"].astext.is_not(None),
        )
    )
    for tenant_id, stored_token in result.all():
        if hmac.compare_digest(stored_token, token):
            return tenant_id
    return None


async def _find_employees_for_provider(db: DBSession, tenant_id: UUID, provider: str) -> list[UUID]:
    """Find active employees that use this integration provider.

    Routes webhooks to the right employees based on who actually has
    credentials for the provider. Tenant-level credentials (employee_id
    IS NULL) cause all active employees to be woken.
    """
    # Check if there's a tenant-level credential (shared across all employees)
    tenant_cred = await db.execute(
        select(IntegrationCredential.id)
        .join(Integration, IntegrationCredential.integration_id == Integration.id)
        .where(
            Integration.tenant_id == tenant_id,
            Integration.provider == provider,
            IntegrationCredential.employee_id.is_(None),
            IntegrationCredential.status == "active",
            IntegrationCredential.deleted_at.is_(None),
        )
        .limit(1)
    )
    if tenant_cred.scalar_one_or_none() is not None:
        # Tenant-level credential → wake all active employees
        result = await db.execute(
            select(Employee.id).where(
                Employee.tenant_id == tenant_id,
                Employee.status == "active",
                Employee.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    # Employee-level credentials → only wake employees that have them
    result = await db.execute(
        select(IntegrationCredential.employee_id)
        .join(Integration, IntegrationCredential.integration_id == Integration.id)
        .join(Employee, IntegrationCredential.employee_id == Employee.id)
        .where(
            Integration.tenant_id == tenant_id,
            Integration.provider == provider,
            IntegrationCredential.employee_id.is_not(None),
            IntegrationCredential.status == "active",
            IntegrationCredential.deleted_at.is_(None),
            Employee.status == "active",
            Employee.deleted_at.is_(None),
        )
        .distinct()
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
    provider: str = Path(max_length=64, pattern=r"^[a-z][a-z0-9_]*$"),
    x_webhook_token: str = Header(description="Webhook authentication token"),
) -> WebhookResponse:
    """Receive a webhook from an external integration provider.

    This is a public endpoint (no JWT) — external providers authenticate
    via the X-Webhook-Token header (avoids leaking secrets in URL/logs).

    The endpoint:
    1. Validates the token against the Integration table
    2. Parses the provider-specific payload
    3. Wakes employees that have credentials for this provider
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
    from empla.integrations.webhooks import get_webhook_parser

    parser = get_webhook_parser(provider)
    try:
        event_type, summary = parser(raw_payload)
    except Exception:
        logger.warning(
            "Webhook parser failed for provider '%s', falling back to generic",
            provider,
            exc_info=True,
        )
        event_type, summary = "unknown", ""

    # Build normalized event
    event = WebhookEvent(
        provider=provider,
        event_type=event_type,
        summary=summary,
        payload=raw_payload if isinstance(raw_payload, dict) else {"raw": raw_payload},
        received_at=datetime.now(UTC),
    )

    # Find employees that have credentials for this provider
    employee_ids = await _find_employees_for_provider(db, tenant_id, provider)
    if not employee_ids:
        logger.info(
            "Webhook received but no employees with credentials for provider",
            extra={"provider": provider, "tenant_id": str(tenant_id)},
        )
        return WebhookResponse(status="accepted", employees_notified=0)

    manager = get_employee_manager()
    event_dict = event.model_dump(mode="json")
    results = await asyncio.gather(
        *(manager.wake_employee(emp_id, event_dict) for emp_id in employee_ids),
        return_exceptions=True,
    )
    notified = 0
    for emp_id, result in zip(employee_ids, results, strict=True):
        if result is True:
            notified += 1
        elif isinstance(result, Exception):
            logger.error(
                "Unexpected error waking employee %s",
                emp_id,
                exc_info=result,
                extra={"employee_id": str(emp_id), "provider": provider},
            )
        else:
            logger.warning(
                "Failed to wake employee %s (unreachable)",
                emp_id,
                extra={"employee_id": str(emp_id), "provider": provider},
            )

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
