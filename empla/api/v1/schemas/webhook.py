"""
empla.api.v1.schemas.webhook - Webhook Event Schemas
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

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
