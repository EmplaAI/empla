"""
empla.services.activity_recorder - Hook-based Activity Recording

Registers on BDI lifecycle hooks to automatically record employee
activities. Maps tool calls to event types for the dashboard feed.

Usage:
    >>> recorder = ActivityRecorder(session, tenant_id, employee_id)
    >>> recorder.register(hooks)
    >>> # Activities auto-recorded as hooks fire during BDI cycles
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from empla.core.hooks import (
    HOOK_AFTER_INTENTION_EXECUTION,
    HOOK_AFTER_PERCEPTION,
    HOOK_CYCLE_END,
    HOOK_EMPLOYEE_START,
    HOOK_EMPLOYEE_STOP,
    HOOK_GOAL_ACHIEVED,
    HookRegistry,
)
from empla.models.activity import ActivityEventType, EmployeeActivity

logger = logging.getLogger(__name__)

# Map tool names to activity event types
TOOL_EVENT_MAP: dict[str, str] = {
    "email.send_email": ActivityEventType.EMAIL_SENT,
    "email.reply_to_email": ActivityEventType.EMAIL_SENT,
    "email.forward_email": ActivityEventType.EMAIL_SENT,
    "email.get_unread_emails": ActivityEventType.EMAIL_RECEIVED,
    "calendar.create_event": ActivityEventType.MEETING_SCHEDULED,
    "calendar.get_upcoming_events": ActivityEventType.CALENDAR_CHECKED,
    "calendar.list_events": ActivityEventType.CALENDAR_CHECKED,
    "crm.create_deal": ActivityEventType.DEAL_CREATED,
    "crm.update_deal": ActivityEventType.DEAL_UPDATED,
    "crm.get_pipeline_metrics": ActivityEventType.CRM_CHECKED,
}


class ActivityRecorder:
    """Records employee activities by listening to BDI hooks.

    Translates hook events (perception results, intention executions,
    lifecycle events) into EmployeeActivity rows for the dashboard.

    Args:
        session: Database session for writing activities.
        tenant_id: Tenant ID for multi-tenancy.
        employee_id: Employee performing the activities.
    """

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._employee_id = employee_id

    def register(self, hooks: HookRegistry) -> None:
        """Register activity recording handlers on BDI hooks.

        Args:
            hooks: HookRegistry to register on.
        """
        hooks.register(HOOK_AFTER_PERCEPTION, self._on_perception)
        hooks.register(HOOK_AFTER_INTENTION_EXECUTION, self._on_intention_execution)
        hooks.register(HOOK_CYCLE_END, self._on_cycle_end)
        hooks.register(HOOK_EMPLOYEE_START, self._on_employee_start)
        hooks.register(HOOK_EMPLOYEE_STOP, self._on_employee_stop)
        hooks.register(HOOK_GOAL_ACHIEVED, self._on_goal_achieved)
        logger.debug(
            "ActivityRecorder registered on hooks",
            extra={"employee_id": str(self._employee_id)},
        )

    async def _record(
        self,
        event_type: str,
        description: str,
        data: dict[str, Any] | None = None,
        importance: float = 0.5,
    ) -> None:
        """Record a single activity."""
        try:
            activity = EmployeeActivity(
                tenant_id=self._tenant_id,
                employee_id=self._employee_id,
                event_type=event_type,
                description=description,
                data=data or {},
                importance=max(0.0, min(1.0, importance)),
                occurred_at=datetime.now(UTC),
            )
            self._session.add(activity)
            # No flush/commit here — let the loop's _safe_commit() handle persistence
        except Exception as e:
            logger.warning(
                "Failed to record activity: %s",
                e,
                exc_info=True,
                extra={"event_type": event_type, "employee_id": str(self._employee_id)},
            )

    async def _on_perception(self, **kwargs: Any) -> None:
        """Record perception results."""
        perception_result = kwargs.get("perception_result")
        if perception_result is None:
            return

        obs_count = len(perception_result.observations)
        if obs_count == 0:
            return

        sources = getattr(perception_result, "sources_checked", [])
        await self._record(
            event_type="perception_completed",
            description=f"Checked {len(sources)} sources, found {obs_count} observations",
            data={
                "observation_count": obs_count,
                "sources": sources,
                "opportunities": perception_result.opportunities_detected,
                "problems": perception_result.problems_detected,
            },
            importance=0.3,
        )

    async def _on_intention_execution(self, **kwargs: Any) -> None:
        """Record intention execution and tool calls made."""
        intention = kwargs.get("intention")
        result = kwargs.get("result")
        tool_calls = kwargs.get("tool_calls", [])

        # When the hook only passes result (IntentionResult), extract info from it
        if intention is None and result is not None:
            success = getattr(result, "success", False)
            intention_id = str(getattr(result, "intention_id", ""))
            outcome = getattr(result, "outcome", {}) or {}
            desc = outcome.get("message", "Intention executed")
            # Extract tool names from outcome before recording
            if not tool_calls:
                tool_calls = [{"tool": name} for name in outcome.get("tools_used", [])]
            event_type = (
                ActivityEventType.INTENTION_COMPLETED
                if success
                else ActivityEventType.INTENTION_FAILED
            )
            await self._record(
                event_type=event_type,
                description=f"{'Completed' if success else 'Failed'}: {desc[:200]}",
                data={
                    "intention_id": intention_id,
                    "success": success,
                    "tool_calls_made": len(tool_calls),
                },
                importance=0.7 if success else 0.8,
            )
        elif intention is not None:
            desc = getattr(intention, "description", "Unknown intention")
            success = result.success if result else False
            event_type = (
                ActivityEventType.INTENTION_COMPLETED
                if success
                else ActivityEventType.INTENTION_FAILED
            )
            await self._record(
                event_type=event_type,
                description=f"{'Completed' if success else 'Failed'}: {desc[:200]}",
                data={
                    "intention_id": str(getattr(intention, "id", "")),
                    "success": success,
                    "tool_calls_made": len(tool_calls) if tool_calls else 0,
                },
                importance=0.7 if success else 0.8,
            )

        # Record individual tool-based activities
        for tc in tool_calls or []:
            tool_name = tc.get("tool", "") if isinstance(tc, dict) else getattr(tc, "name", "")
            event_type = TOOL_EVENT_MAP.get(tool_name)
            if event_type:
                await self._record(
                    event_type=event_type,
                    description=f"Tool: {tool_name}",
                    data={"tool": tool_name},
                    importance=0.5,
                )

    async def _on_cycle_end(self, **kwargs: Any) -> None:
        """Commit activities at end of BDI cycle."""
        # Activities are committed by the loop's session commit

    async def _on_employee_start(self, **kwargs: Any) -> None:
        """Record employee start."""
        name = kwargs.get("name", "Unknown")
        await self._record(
            event_type=ActivityEventType.EMPLOYEE_STARTED,
            description=f"Employee {name} started",
            importance=0.9,
        )

    async def _on_employee_stop(self, **kwargs: Any) -> None:
        """Record employee stop."""
        name = kwargs.get("name", "Unknown")
        await self._record(
            event_type=ActivityEventType.EMPLOYEE_STOPPED,
            description=f"Employee {name} stopped",
            importance=0.9,
        )

    async def _on_goal_achieved(self, **kwargs: Any) -> None:
        """Record goal achievement as a max-importance activity event."""
        goal_description = kwargs.get("goal_description", "Unknown goal")
        metric = kwargs.get("metric", "")
        current_value = kwargs.get("current_value")
        target_value = kwargs.get("target_value")
        await self._record(
            event_type=ActivityEventType.GOAL_ACHIEVED,
            description=f"Goal achieved: {goal_description[:200]}",
            data={
                "goal_id": str(kwargs.get("goal_id", "")),
                "metric": metric,
                "current_value": current_value,
                "target_value": target_value,
                "goal_type": kwargs.get("goal_type", ""),
            },
            importance=1.0,
        )


__all__ = ["ActivityRecorder"]
