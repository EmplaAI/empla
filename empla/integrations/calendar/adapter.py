"""
empla.integrations.calendar.adapter - Calendar Adapter Layer

Abstracts calendar provider differences behind a common interface.

Supported providers:
- "test" — In-memory calendar for development and testing
- "google" — Google Calendar (future, requires OAuth)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

logger = logging.getLogger(__name__)


class CalendarAdapter(Protocol):
    """Protocol for calendar adapters."""

    async def get_upcoming_events(self, days: int = 7, limit: int = 20) -> list[dict[str, Any]]: ...
    async def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str | None,
        attendees: list[str] | None,
        location: str | None,
    ) -> dict[str, Any]: ...
    async def update_event(
        self,
        event_id: str,
        title: str | None,
        start_time: str | None,
        end_time: str | None,
        description: str | None,
    ) -> dict[str, Any]: ...
    async def delete_event(self, event_id: str) -> dict[str, Any]: ...
    async def check_availability(self, start_time: str, end_time: str) -> dict[str, Any]: ...
    async def shutdown(self) -> None: ...


class InMemoryCalendarAdapter:
    """In-memory calendar for development and testing."""

    def __init__(self) -> None:
        self._events: dict[str, dict[str, Any]] = {}

    async def get_upcoming_events(self, days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        cutoff = now + timedelta(days=days)
        upcoming = []
        for event in self._events.values():
            try:
                start = datetime.fromisoformat(event["start_time"])
                if now <= start <= cutoff:
                    upcoming.append(event)
            except (ValueError, KeyError):
                continue
        upcoming.sort(key=lambda e: e.get("start_time", ""))
        return upcoming[:limit]

    async def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str | None = None,
        attendees: list[str] | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        event_id = str(uuid4())
        event = {
            "id": event_id,
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
            "description": description,
            "attendees": attendees or [],
            "location": location,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._events[event_id] = event
        return event

    async def update_event(
        self,
        event_id: str,
        title: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        if event_id not in self._events:
            raise KeyError(f"Event {event_id} not found")
        event = self._events[event_id]
        if title is not None:
            event["title"] = title
        if start_time is not None:
            event["start_time"] = start_time
        if end_time is not None:
            event["end_time"] = end_time
        if description is not None:
            event["description"] = description
        return event

    async def delete_event(self, event_id: str) -> dict[str, Any]:
        if event_id not in self._events:
            raise KeyError(f"Event {event_id} not found")
        del self._events[event_id]
        return {"success": True, "deleted_id": event_id}

    async def check_availability(self, start_time: str, end_time: str) -> dict[str, Any]:
        try:
            req_start = datetime.fromisoformat(start_time)
            req_end = datetime.fromisoformat(end_time)
        except ValueError:
            return {"available": False, "error": "Invalid time format"}

        conflicts = []
        for event in self._events.values():
            try:
                ev_start = datetime.fromisoformat(event["start_time"])
                ev_end = datetime.fromisoformat(event["end_time"])
                if ev_start < req_end and ev_end > req_start:
                    conflicts.append({"id": event["id"], "title": event["title"]})
            except (ValueError, KeyError):
                continue

        return {
            "available": len(conflicts) == 0,
            "conflicts": conflicts,
        }

    async def shutdown(self) -> None:
        pass


def create_calendar_adapter(**config: Any) -> CalendarAdapter:
    """Factory for calendar adapters based on config."""
    provider = config.get("provider", "test")
    if provider == "test":
        return InMemoryCalendarAdapter()
    # Future: Google Calendar, Microsoft Outlook adapters
    raise ValueError(f"Unknown calendar provider: '{provider}'. Supported: 'test'")
