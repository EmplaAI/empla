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
import secrets
import time as _time
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request, status
from sqlalchemy import func, select

from empla.api.deps import CurrentUser, DBSession
from empla.api.v1.schemas.webhook import (
    WebhookAuditEvent,
    WebhookEvent,
    WebhookEventListResponse,
    WebhookResponse,
    WebhookTokenCreateRequest,
    WebhookTokenInfo,
    WebhookTokenIssued,
)
from empla.models.audit import AuditLog
from empla.models.employee import Employee
from empla.models.integration import Integration, IntegrationCredential
from empla.services.employee_manager import get_employee_manager

# 5-minute grace window for the previous token after rotation. Tuned so a
# webhook provider that's about to retry a delivery with the old token
# doesn't get a 401 in the seconds after the dashboard rotates.
_TOKEN_ROTATION_GRACE_SECONDS = 300

logger = logging.getLogger(__name__)

router = APIRouter()


async def _find_tenant_by_webhook_token(
    db: DBSession, provider: str, token: str
) -> tuple[UUID, UUID] | None:
    """Look up the tenant + integration that owns this webhook token.

    Tokens live in ``Integration.oauth_config``. After a rotation the
    previous token is preserved for ``_TOKEN_ROTATION_GRACE_SECONDS`` so
    in-flight deliveries don't 401. Uses constant-time comparison to
    prevent timing side-channel attacks (this is the sole auth mechanism
    on a public endpoint).
    """
    import hmac

    result = await db.execute(
        select(
            Integration.id,
            Integration.tenant_id,
            Integration.oauth_config,
        ).where(
            Integration.provider == provider,
            Integration.status == "active",
            Integration.oauth_config["webhook_token"].astext.is_not(None),
        )
    )
    now = _time.time()
    for integration_id, tenant_id, oauth_config in result.all():
        stored = (oauth_config or {}).get("webhook_token")
        if stored and hmac.compare_digest(str(stored), token):
            return tenant_id, integration_id
        # Grace-window match against the previous token
        prev = (oauth_config or {}).get("webhook_token_prev")
        rotated_at = (oauth_config or {}).get("rotated_at")
        if (
            prev
            and rotated_at is not None
            and (now - float(rotated_at)) < _TOKEN_ROTATION_GRACE_SECONDS
            and hmac.compare_digest(str(prev), token)
        ):
            return tenant_id, integration_id
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
    match = await _find_tenant_by_webhook_token(db, provider, x_webhook_token)
    if match is None:
        logger.warning(
            "Webhook received with invalid token",
            extra={"provider": provider},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token",
        )
    tenant_id, integration_id = match

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

    # Persist a row to AuditLog so the dashboard event feed can show it.
    # Best-effort: if this write fails, the webhook still succeeded for the
    # employee — log and swallow rather than 500 the provider.
    try:
        db.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_type="webhook",
                actor_id=integration_id,
                action_type=f"webhook_{provider}_{event_type}",
                resource_type="webhook",
                resource_id=None,
                details={
                    "provider": provider,
                    "event_type": event_type,
                    "summary": summary,
                    # Cap payload size in audit log — large payloads bloat
                    # the row + the dashboard query response.
                    "payload": _truncate_payload(raw_payload),
                    "routed_to_employees": [str(e) for e in employee_ids],
                    "employees_notified": notified,
                },
            )
        )
        await db.commit()
    except Exception:
        logger.warning(
            "Failed to write webhook audit log row (event still delivered)",
            exc_info=True,
            extra={"provider": provider, "tenant_id": str(tenant_id)},
        )

    return WebhookResponse(status="accepted", employees_notified=notified)


def _truncate_payload(payload: object, max_chars: int = 4000) -> object:
    """Bound how much webhook payload we persist into AuditLog."""
    import json as _json

    try:
        encoded = _json.dumps(payload)
    except (TypeError, ValueError):
        return {"_truncated": "non-serializable payload"}
    if len(encoded) <= max_chars:
        return payload
    return {
        "_truncated": True,
        "_original_size": len(encoded),
        "_excerpt": encoded[:max_chars],
    }


# =========================================================================
# Token management (PR #81) — JWT-protected, tenant-scoped
# =========================================================================


async def _get_integration(db: DBSession, integration_id: UUID, tenant_id: UUID) -> Integration:
    """Fetch an integration row enforcing tenant ownership, 404 otherwise."""
    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.tenant_id == tenant_id,
            Integration.deleted_at.is_(None),
        )
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )
    return integration


def _token_info(integration: Integration) -> WebhookTokenInfo:
    """Build the public-facing info object — never includes the token value."""
    cfg = integration.oauth_config or {}
    rotated_at = cfg.get("rotated_at")
    rotated_at_dt = (
        datetime.fromtimestamp(float(rotated_at), tz=UTC) if rotated_at is not None else None
    )
    grace_active = (
        rotated_at is not None
        and cfg.get("webhook_token_prev") is not None
        and (_time.time() - float(rotated_at)) < _TOKEN_ROTATION_GRACE_SECONDS
    )
    return WebhookTokenInfo(
        integration_id=str(integration.id),
        provider=integration.provider,
        has_token=bool(cfg.get("webhook_token")),
        rotated_at=rotated_at_dt,
        grace_window_active=grace_active,
    )


@router.post(
    "/tokens",
    response_model=WebhookTokenIssued,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook_token(
    db: DBSession,
    auth: CurrentUser,
    body: WebhookTokenCreateRequest,
) -> WebhookTokenIssued:
    """Generate a fresh webhook token for an integration. Returns it ONCE."""
    try:
        integration_id = UUID(body.integration_id)
    except (ValueError, AttributeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid integration_id",
        ) from e

    integration = await _get_integration(db, integration_id, auth.tenant_id)
    token = secrets.token_urlsafe(32)

    # Mutate the JSONB blob in place. Pydantic-typed ORM models with JSONB
    # need the assignment to a fresh dict so SQLAlchemy notices the change.
    cfg = dict(integration.oauth_config or {})
    cfg["webhook_token"] = token
    cfg.pop("webhook_token_prev", None)
    cfg.pop("rotated_at", None)
    integration.oauth_config = cfg
    await db.commit()

    return WebhookTokenIssued(
        integration_id=str(integration.id),
        provider=integration.provider,
        token=token,
        rotated_at=None,
    )


@router.post(
    "/tokens/{integration_id}/rotate",
    response_model=WebhookTokenIssued,
)
async def rotate_webhook_token(
    db: DBSession,
    auth: CurrentUser,
    integration_id: UUID,
) -> WebhookTokenIssued:
    """
    Rotate the webhook token. The PREVIOUS token is preserved for
    ``_TOKEN_ROTATION_GRACE_SECONDS`` (5 minutes) so in-flight webhook
    deliveries don't 401 mid-rotation.
    """
    integration = await _get_integration(db, integration_id, auth.tenant_id)
    cfg = dict(integration.oauth_config or {})
    old = cfg.get("webhook_token")
    if not old:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No webhook token to rotate. POST /webhooks/tokens to create one.",
        )

    new_token = secrets.token_urlsafe(32)
    now = _time.time()
    cfg["webhook_token"] = new_token
    cfg["webhook_token_prev"] = old
    cfg["rotated_at"] = now
    integration.oauth_config = cfg
    await db.commit()

    return WebhookTokenIssued(
        integration_id=str(integration.id),
        provider=integration.provider,
        token=new_token,
        rotated_at=datetime.fromtimestamp(now, tz=UTC),
    )


@router.delete(
    "/tokens/{integration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_webhook_token(
    db: DBSession,
    auth: CurrentUser,
    integration_id: UUID,
) -> None:
    """Drop both current and previous tokens. Webhooks for this integration
    will start returning 401 immediately."""
    integration = await _get_integration(db, integration_id, auth.tenant_id)
    cfg = dict(integration.oauth_config or {})
    if not (cfg.get("webhook_token") or cfg.get("webhook_token_prev")):
        return  # already empty — idempotent
    cfg.pop("webhook_token", None)
    cfg.pop("webhook_token_prev", None)
    cfg.pop("rotated_at", None)
    integration.oauth_config = cfg
    await db.commit()


@router.get(
    "/tokens",
    response_model=list[WebhookTokenInfo],
)
async def list_webhook_tokens(
    db: DBSession,
    auth: CurrentUser,
) -> list[WebhookTokenInfo]:
    """List webhook-token state for every integration in this tenant.

    Token values are NEVER included — only existence + rotation state.
    """
    result = await db.execute(
        select(Integration)
        .where(
            Integration.tenant_id == auth.tenant_id,
            Integration.deleted_at.is_(None),
        )
        .order_by(Integration.provider, Integration.created_at.desc())
    )
    return [_token_info(i) for i in result.scalars().all()]


# =========================================================================
# Webhook event feed (PR #81) — reads AuditLog rows where actor_type='webhook'
# =========================================================================


def _parse_audit_event(row: AuditLog) -> WebhookAuditEvent:
    details = row.details or {}
    return WebhookAuditEvent(
        id=str(row.id),
        integration_id=str(row.actor_id),
        provider=str(details.get("provider", "unknown")),
        event_type=str(details.get("event_type", "unknown")),
        summary=str(details.get("summary", "") or ""),
        employees_notified=int(details.get("employees_notified", 0) or 0),
        occurred_at=row.occurred_at,
    )


@router.get(
    "/events",
    response_model=WebhookEventListResponse,
)
async def list_webhook_events(
    db: DBSession,
    auth: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    provider: Annotated[str | None, Query(max_length=64, pattern=r"^[a-z][a-z0-9_]*$")] = None,
) -> WebhookEventListResponse:
    """List webhook events received for this tenant, newest first."""
    base = select(AuditLog).where(
        AuditLog.tenant_id == auth.tenant_id,
        AuditLog.actor_type == "webhook",
        AuditLog.deleted_at.is_(None),
    )
    if provider:
        # Filter by JSONB key — uses the action_type prefix as a cheap
        # pre-filter (action_type is "webhook_<provider>_<event_type>").
        base = base.where(AuditLog.action_type.like(f"webhook_{provider}_%"))

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0

    query = (
        base.order_by(AuditLog.occurred_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    result = await db.execute(query)
    rows = list(result.scalars().all())

    pages = (total + page_size - 1) // page_size if total > 0 else 1
    return WebhookEventListResponse(
        items=[_parse_audit_event(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )
