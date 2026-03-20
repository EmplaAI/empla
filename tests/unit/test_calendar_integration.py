"""Tests for Calendar integration tools (native @tool pattern)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from empla.integrations.calendar.tools import router


@pytest.fixture(autouse=True)
async def _init_calendar_router() -> AsyncIterator[None]:
    """Initialize calendar router with test adapter for each test."""
    await router.initialize({"provider": "test"})
    yield
    await router.shutdown()


def _future_iso(hours: int = 1) -> str:
    """Generate an ISO timestamp N hours in the future."""
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


class TestCalendarToolRegistration:
    def test_tools_registered(self) -> None:
        tool_names = [t["name"] for t in router._tools]
        assert "calendar.get_upcoming_events" in tool_names
        assert "calendar.create_event" in tool_names
        assert "calendar.update_event" in tool_names
        assert "calendar.delete_event" in tool_names
        assert "calendar.check_availability" in tool_names

    def test_tool_count(self) -> None:
        assert len(router._tools) == 5


class TestEvents:
    @pytest.mark.asyncio
    async def test_create_and_get_event(self) -> None:
        event = await router.execute_tool(
            "calendar.create_event",
            {
                "title": "Demo Call",
                "start_time": _future_iso(2),
                "end_time": _future_iso(3),
                "attendees": ["client@acme.com"],
            },
        )
        assert event["title"] == "Demo Call"
        assert "id" in event
        assert event["attendees"] == ["client@acme.com"]

        upcoming = await router.execute_tool("calendar.get_upcoming_events", {})
        assert len(upcoming) == 1
        assert upcoming[0]["title"] == "Demo Call"

    @pytest.mark.asyncio
    async def test_empty_calendar(self) -> None:
        events = await router.execute_tool("calendar.get_upcoming_events", {})
        assert events == []

    @pytest.mark.asyncio
    async def test_update_event(self) -> None:
        event = await router.execute_tool(
            "calendar.create_event",
            {"title": "Meeting", "start_time": _future_iso(1), "end_time": _future_iso(2)},
        )
        updated = await router.execute_tool(
            "calendar.update_event",
            {"event_id": event["id"], "title": "Updated Meeting"},
        )
        assert updated["title"] == "Updated Meeting"

    @pytest.mark.asyncio
    async def test_update_nonexistent_event(self) -> None:
        with pytest.raises(KeyError, match="not found"):
            await router.execute_tool(
                "calendar.update_event",
                {"event_id": "nonexistent", "title": "X"},
            )

    @pytest.mark.asyncio
    async def test_delete_event(self) -> None:
        event = await router.execute_tool(
            "calendar.create_event",
            {"title": "To Delete", "start_time": _future_iso(1), "end_time": _future_iso(2)},
        )
        result = await router.execute_tool("calendar.delete_event", {"event_id": event["id"]})
        assert result["success"] is True

        events = await router.execute_tool("calendar.get_upcoming_events", {})
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_event(self) -> None:
        with pytest.raises(KeyError, match="not found"):
            await router.execute_tool("calendar.delete_event", {"event_id": "nonexistent"})

    @pytest.mark.asyncio
    async def test_events_beyond_window_excluded(self) -> None:
        """Events further than N days out should not appear in upcoming."""
        # Event 30 days out — beyond 7-day default window
        far_future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        far_end = (datetime.now(UTC) + timedelta(days=30, hours=1)).isoformat()
        await router.execute_tool(
            "calendar.create_event",
            {"title": "Far Future", "start_time": far_future, "end_time": far_end},
        )
        # Event 2 days out — within window
        await router.execute_tool(
            "calendar.create_event",
            {"title": "Soon", "start_time": _future_iso(48), "end_time": _future_iso(49)},
        )

        events = await router.execute_tool("calendar.get_upcoming_events", {"days": 7})
        assert len(events) == 1
        assert events[0]["title"] == "Soon"


class TestAvailability:
    @pytest.mark.asyncio
    async def test_available_slot(self) -> None:
        result = await router.execute_tool(
            "calendar.check_availability",
            {"start_time": _future_iso(10), "end_time": _future_iso(11)},
        )
        assert result["available"] is True
        assert result["conflicts"] == []

    @pytest.mark.asyncio
    async def test_conflicting_slot(self) -> None:
        start = _future_iso(2)
        end = _future_iso(3)
        await router.execute_tool(
            "calendar.create_event",
            {"title": "Existing", "start_time": start, "end_time": end},
        )

        result = await router.execute_tool(
            "calendar.check_availability",
            {"start_time": start, "end_time": end},
        )
        assert result["available"] is False
        assert len(result["conflicts"]) == 1
        assert result["conflicts"][0]["title"] == "Existing"

    @pytest.mark.asyncio
    async def test_invalid_time_format(self) -> None:
        result = await router.execute_tool(
            "calendar.check_availability",
            {"start_time": "not-a-date", "end_time": "also-not"},
        )
        assert result["available"] is False
        assert "error" in result
