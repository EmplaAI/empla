"""
empla.api.v1.schemas.webhook - Webhook Event Schemas
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class WebhookEvent(BaseModel):
    """Normalized event from an external webhook.

    Built by the webhook endpoint after provider-specific parsing
    and sent to employee subprocesses via EmployeeManager.wake_employee().
    """

    provider: str = Field(description="Integration provider (e.g. 'hubspot', 'google_calendar')")
    event_type: str = Field(description="Provider-specific event type (e.g. 'deal.updated')")
    summary: str = Field(default="", description="Human-readable summary for the LLM")
    payload: dict[str, Any] = Field(default_factory=dict, description="Raw event payload")
    received_at: datetime = Field(description="When the webhook was received")


class WebhookResponse(BaseModel):
    """Response to a webhook delivery."""

    status: str = Field(description="'accepted' or 'error'")
    employees_notified: int = Field(default=0, description="Number of employees woken")
    detail: str = Field(default="", description="Error detail if status is 'error'")


# ---------------------------------------------------------------------------
# Token management (PR #81)
# ---------------------------------------------------------------------------


class WebhookTokenInfo(BaseModel):
    """Public-facing token state (token VALUE is never returned after creation)."""

    integration_id: str
    provider: str
    has_token: bool = Field(description="Whether a token is currently set")
    rotated_at: datetime | None = Field(
        default=None,
        description="When the previous token was rotated out (None if never rotated)",
    )
    grace_window_active: bool = Field(
        default=False,
        description="True if the previous token is still accepted (within grace window)",
    )


class WebhookTokenIssued(BaseModel):
    """One-time response containing the freshly-generated token."""

    integration_id: str
    provider: str
    token: str = Field(description="The new webhook token. Save it now — never returned again.")
    rotated_at: datetime | None = None


class WebhookTokenCreateRequest(BaseModel):
    """Body for POST /webhooks/tokens (rejects malformed UUIDs at schema boundary)."""

    integration_id: UUID = Field(description="Integration row to attach the token to")


# ---------------------------------------------------------------------------
# Event feed (PR #81) — reads AuditLog rows where actor_type='webhook'
# ---------------------------------------------------------------------------


class WebhookAuditEvent(BaseModel):
    """One webhook delivery, rendered from an AuditLog row (actor_type='webhook')."""

    id: str
    integration_id: str = Field(description="Integration that received the webhook")
    provider: str
    event_type: str
    summary: str = ""
    employees_notified: int = 0
    occurred_at: datetime


class WebhookEventListResponse(BaseModel):
    """Paginated envelope around WebhookAuditEvent items, newest first."""

    items: list[WebhookAuditEvent]
    total: int
    page: int
    page_size: int
    pages: int
