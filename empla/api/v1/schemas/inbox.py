"""
empla.api.v1.schemas.inbox - Inbox API schemas

The inbox body is a list of typed content blocks, not plain text. Each
block is one of a small, well-defined set of kinds — ``text``,
``cost_breakdown``, ``link``, ``stat``, ``list`` — and the dashboard
picks a React component per ``kind``. New kinds get added here; unknown
kinds render as a JSON preview on the frontend with a "update your
dashboard" hint (forward-compat).

Why blocks instead of markdown:
    The cost hard-stop posts ``[text, cost_breakdown, link]`` so the
    user sees the full cost breakdown INSIDE the message, not behind a
    click. Rendering a typed cost_breakdown block as a formatted table
    is cleaner than parsing markdown, and it lets the dashboard evolve
    the presentation (sort columns, highlight spikes) without the
    employee changing anything.

The runtime writer is :func:`empla.services.inbox_service.post_to_inbox`;
every block passes through Pydantic validation + the 10kB body-size cap
before landing in the DB.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Priority tiers. Kept in sync with the DB CHECK constraint on
# ``inbox_messages.priority``. Adding a tier requires migrating the CHECK.
InboxPriority = Literal["urgent", "normal", "off"]

# Allowed block kinds. Frontend maps each to a React component.
# "text" — simple paragraph/list of paragraphs
# "cost_breakdown" — per-cycle cost table (used by the cost hard-stop)
# "link" — labeled link to a dashboard route or external URL
# "stat" — single labeled value (e.g., "Pipeline coverage: 2.1x")
# "list" — bulleted/numbered list of label/value pairs
InboxBlockKind = Literal["text", "cost_breakdown", "link", "stat", "list"]


class InboxBlock(BaseModel):
    """One typed content block in an inbox message body.

    Shape-per-kind conventions (the ``data`` dict is loosely typed here
    so the schema stays forward-compat when new kinds land, but the
    dashboard renderers assume specific shapes):

    - ``text``: ``{"content": str}`` — plain text, newlines preserved,
      no HTML (rendered via React text nodes, never
      ``dangerouslySetInnerHTML``).
    - ``cost_breakdown``:
      ``{"cycles": [{"cycle": int, "cost_usd": float, "phase": str}],
         "total_usd": float, "window": str}``
    - ``link``: ``{"label": str, "url": str, "icon": str | None}``.
      External URLs pass through as-is; internal routes can be
      ``/employees/...``. The dashboard sanitizes href.
    - ``stat``: ``{"label": str, "value": str,
      "trend": "up" | "down" | "flat" | None}``.
    - ``list``: ``{"items": [{"label": str, "value": str | None}]}``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: InboxBlockKind
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def _data_size_guard(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Reject blocks whose data payload exceeds 4kB on its own.

        The full-message 10kB cap is enforced in the service (sum of all
        block payload sizes), but single-block bombs (e.g., a 1MB text
        body) should fail fast at schema validation.
        """
        import json

        size = len(json.dumps(v, default=str))
        if size > 4096:
            raise ValueError(
                f"Block data payload is {size} bytes; max is 4096 (4kB). "
                "Split long content across multiple blocks."
            )
        return v


class InboxMessageResponse(BaseModel):
    """Response shape for a single inbox message."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    employee_id: UUID
    priority: InboxPriority
    subject: str
    blocks: list[dict[str, Any]] = Field(
        description="Typed InboxBlock objects. Frontend renders per 'kind'."
    )
    read_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InboxListResponse(BaseModel):
    """Paginated list of inbox messages + unread count for the badge."""

    items: list[InboxMessageResponse]
    total: int
    unread_count: int = Field(
        description=(
            "Total unread messages in the tenant (not just on this page). "
            "The sidebar badge uses this; no extra request needed."
        )
    )
    page: int
    page_size: int
    pages: int


class InboxMarkReadRequest(BaseModel):
    """Body is empty — mark-read is idempotent POST without payload."""

    model_config = ConfigDict(extra="forbid")
