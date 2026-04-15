"""
empla.api.v1.schemas.scheduler - Scheduler API Schemas (PR #82)

Read + cancel + user-requested-add contracts over the existing
`WorkingMemory` items with ``content["subtype"] == "scheduled_action"``.
No new storage.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

ScheduledActionSource = Literal["employee", "user_requested"]


class ScheduledActionResponse(BaseModel):
    """One queued scheduled action — shape shown in the dashboard schedule panel."""

    id: UUID = Field(description="Underlying WorkingMemory row id — pass to DELETE to cancel")
    description: str
    scheduled_for: datetime
    recurring: bool = False
    interval_hours: float | None = None
    source: ScheduledActionSource = Field(
        default="employee",
        description="Who asked for it. 'employee' = self-scheduled during BDI; "
        "'user_requested' = user added via the dashboard.",
    )
    created_at: datetime | None = None


class ScheduledActionListResponse(BaseModel):
    """All pending scheduled actions for an employee, sorted by scheduled_for ascending."""

    items: list[ScheduledActionResponse]
    total: int


class ScheduledActionCreateRequest(BaseModel):
    """User-filed scheduled action. Always stored with ``source='user_requested'``."""

    description: str = Field(min_length=1, max_length=500)
    scheduled_for: datetime = Field(description="ISO datetime with timezone (UTC preferred)")
    recurring: bool = False
    interval_hours: float | None = Field(
        default=None,
        ge=0.5,
        le=8760,
        description="Required when recurring=true; between 0.5 and 8760 hours",
    )

    @field_validator("scheduled_for")
    @classmethod
    def _must_have_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError(
                "scheduled_for must include a timezone. "
                "Use ISO format like 2026-04-14T15:00:00Z or +00:00"
            )
        return v

    @field_validator("interval_hours")
    @classmethod
    def _interval_required_when_recurring(cls, v: float | None, info: object) -> float | None:
        # Accessing sibling fields via info.data (Pydantic v2 idiom).
        data = getattr(info, "data", {}) or {}
        if data.get("recurring") and v is None:
            raise ValueError("interval_hours is required when recurring=true")
        return v
