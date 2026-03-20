"""
empla.integrations.calendar.tools - Calendar Integration Tools

Defines calendar tools using the IntegrationRouter pattern.
Provides event management, availability checking, and scheduling.

Example:
    >>> from empla.integrations.calendar.tools import router
    >>> await router.initialize({"provider": "test"})
    >>> result = await router.execute_tool("calendar.get_upcoming_events", {})
"""

from empla.integrations.calendar.adapter import create_calendar_adapter
from empla.integrations.router import IntegrationRouter

router = IntegrationRouter("calendar", adapter_factory=create_calendar_adapter)


@router.tool()
async def get_upcoming_events(days: int = 7, limit: int = 20) -> list[dict]:
    """Get upcoming calendar events within the next N days."""
    return await router.adapter.get_upcoming_events(days=days, limit=limit)


@router.tool()
async def create_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    attendees: list[str] | None = None,
    location: str | None = None,
) -> dict:
    """Create a new calendar event. Times in ISO 8601 format."""
    return await router.adapter.create_event(
        title=title,
        start_time=start_time,
        end_time=end_time,
        description=description,
        attendees=attendees,
        location=location,
    )


@router.tool()
async def update_event(
    event_id: str,
    title: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    description: str | None = None,
) -> dict:
    """Update an existing calendar event."""
    return await router.adapter.update_event(
        event_id=event_id,
        title=title,
        start_time=start_time,
        end_time=end_time,
        description=description,
    )


@router.tool()
async def delete_event(event_id: str) -> dict:
    """Delete a calendar event."""
    return await router.adapter.delete_event(event_id=event_id)


@router.tool()
async def check_availability(
    start_time: str,
    end_time: str,
) -> dict:
    """Check if a time slot is available (no conflicting events)."""
    return await router.adapter.check_availability(start_time=start_time, end_time=end_time)
