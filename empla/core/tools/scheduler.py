"""
empla.core.tools.scheduler - Scheduled Actions Tools

Tools for the LLM to schedule future work for itself. The employee calls
schedule_action during execution when it decides "I should check on this
later" — fully agentic, the LLM decides when and what to schedule.

Inspired by OpenClaw's cron tool: the agent schedules its own future work,
due actions are injected as observations (not auto-executed), and the agent
decides how to act on them.

Storage: working memory items (item_type="scheduled_action"). No new tables.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from empla.core.tools.decorator import tool

logger = logging.getLogger(__name__)


@tool(
    name="schedule_action",
    description=(
        "Schedule a future action for yourself. Use this when you need to "
        "follow up on something later, check on a result, or perform recurring work. "
        "Examples: 'Follow up with Acme Corp in 3 hours', 'Check pipeline every Monday at 9am'."
    ),
    category="scheduling",
    tags=["schedule", "reminder", "follow-up", "cron"],
)
async def schedule_action(
    description: str,
    hours_from_now: float = 0,
    scheduled_at: str = "",
    recurring: bool = False,
    interval_hours: float = 24,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Schedule an action for the future.

    Args:
        description: What to do when the action fires (e.g., "Follow up with Acme Corp on deal status").
        hours_from_now: Schedule this many hours from now (e.g., 3 for "in 3 hours"). Ignored if scheduled_at is set.
        scheduled_at: Specific ISO datetime to schedule at (e.g., "2026-03-27T15:00:00Z"). Overrides hours_from_now.
        recurring: If True, the action repeats at interval_hours after each execution.
        interval_hours: For recurring actions, hours between executions (default 24).
        context: Extra context to remember (e.g., {"deal_id": "123", "contact": "john@acme.com"}).

    Returns:
        Confirmation dict with action_id and scheduled_for time.
    """
    now = datetime.now(UTC)

    # Input validation — these values come from the LLM
    if hours_from_now < 0:
        return {"error": "hours_from_now must be non-negative"}
    if hours_from_now > 8760:
        return {"error": "hours_from_now cannot exceed 8760 (1 year)"}
    if recurring and interval_hours < 0.5:
        return {"error": "interval_hours must be at least 0.5 (30 minutes)"}
    if recurring and interval_hours > 8760:
        return {"error": "interval_hours cannot exceed 8760 (1 year)"}

    if scheduled_at:
        try:
            schedule_time = datetime.fromisoformat(scheduled_at)
        except ValueError:
            return {
                "error": f"Invalid datetime format: {scheduled_at}. Use ISO format like 2026-03-27T15:00:00Z"
            }
    elif hours_from_now > 0:
        schedule_time = now + timedelta(hours=hours_from_now)
    else:
        return {"error": "Provide either hours_from_now > 0 or a scheduled_at datetime"}

    action_id = str(uuid4())

    # Return the action data — the caller (ToolRouter) stores it in working memory
    return {
        "action_id": action_id,
        "description": description,
        "scheduled_for": schedule_time.isoformat(),
        "recurring": recurring,
        "interval_hours": interval_hours if recurring else None,
        "context": context or {},
        "created_at": now.isoformat(),
        "status": "scheduled",
        "_store_as_scheduled_action": True,  # Signal to ToolRouter to persist
    }


@tool(
    name="list_scheduled_actions",
    description="List your pending scheduled actions. See what you've scheduled for the future.",
    category="scheduling",
    tags=["schedule", "list"],
)
async def list_scheduled_actions() -> dict[str, Any]:
    """List all pending scheduled actions.

    Returns:
        Dict with list of pending actions.
    """
    # The actual list is populated by the caller with working memory data
    return {"_list_scheduled_actions": True}


@tool(
    name="cancel_scheduled_action",
    description="Cancel a previously scheduled action by its ID.",
    category="scheduling",
    tags=["schedule", "cancel"],
)
async def cancel_scheduled_action(
    action_id: str,
) -> dict[str, Any]:
    """Cancel a scheduled action.

    Args:
        action_id: The ID of the action to cancel (from schedule_action result).

    Returns:
        Confirmation of cancellation.
    """
    return {"action_id": action_id, "_cancel_scheduled_action": True}
