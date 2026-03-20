"""Tests for Google Calendar connector — mocked HTTP calls."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from empla.integrations.google_calendar import tools as gcal_mod
from empla.integrations.google_calendar.tools import router


def _mock_response(json_data: dict, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.text = str(json_data)
    resp.raise_for_status = MagicMock()
    if status >= 400:
        request = MagicMock()
        request.url = "https://www.googleapis.com/test"
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status}", request=request, response=resp
        )
    return resp


def _future_iso(hours: int = 1) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


@pytest.fixture(autouse=True)
async def _init_gcal() -> AsyncIterator[None]:
    mock_client = AsyncMock()
    gcal_mod._client = mock_client
    gcal_mod._calendar_id = "primary"
    yield
    gcal_mod._client = None


@pytest.fixture
def client() -> AsyncMock:
    assert gcal_mod._client is not None
    return gcal_mod._client


class TestInitialization:
    @pytest.mark.asyncio
    async def test_init_requires_access_token(self) -> None:
        gcal_mod._client = None
        with pytest.raises(ValueError, match="access_token"):
            await router.initialize({})


class TestEvents:
    @pytest.mark.asyncio
    async def test_get_upcoming_events(self, client: AsyncMock) -> None:
        client.get.return_value = _mock_response(
            {
                "items": [
                    {
                        "id": "ev1",
                        "summary": "Demo Call",
                        "start": {"dateTime": _future_iso(2)},
                        "end": {"dateTime": _future_iso(3)},
                        "description": "Product demo",
                        "attendees": [{"email": "client@acme.com"}],
                    },
                ]
            }
        )
        events = await router.execute_tool("google_calendar.get_upcoming_events", {})
        assert len(events) == 1
        assert events[0]["title"] == "Demo Call"
        assert events[0]["attendees"] == ["client@acme.com"]

    @pytest.mark.asyncio
    async def test_create_event(self, client: AsyncMock) -> None:
        client.post.return_value = _mock_response(
            {
                "id": "new-event-1",
                "htmlLink": "https://calendar.google.com/event?eid=xxx",
            }
        )
        event = await router.execute_tool(
            "google_calendar.create_event",
            {"title": "Strategy Meeting", "start_time": _future_iso(2), "end_time": _future_iso(3)},
        )
        assert event["id"] == "new-event-1"
        assert event["link"] is not None

    @pytest.mark.asyncio
    async def test_update_event(self, client: AsyncMock) -> None:
        client.patch.return_value = _mock_response({"id": "ev1"})
        result = await router.execute_tool(
            "google_calendar.update_event",
            {"event_id": "ev1", "title": "Updated Meeting"},
        )
        assert result["id"] == "ev1"
        assert "summary" in result["updated"]

    @pytest.mark.asyncio
    async def test_update_event_no_fields_raises(self) -> None:
        with pytest.raises(ValueError, match="No fields"):
            await router.execute_tool("google_calendar.update_event", {"event_id": "ev1"})

    @pytest.mark.asyncio
    async def test_delete_event(self, client: AsyncMock) -> None:
        client.delete.return_value = _mock_response({}, status=204)
        result = await router.execute_tool("google_calendar.delete_event", {"event_id": "ev1"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_http_error_propagates(self, client: AsyncMock) -> None:
        client.get.return_value = _mock_response({"error": {"message": "Not found"}}, status=404)
        with pytest.raises(httpx.HTTPStatusError):
            await router.execute_tool("google_calendar.get_upcoming_events", {})


class TestAvailability:
    @pytest.mark.asyncio
    async def test_available_slot(self, client: AsyncMock) -> None:
        client.post.return_value = _mock_response({"calendars": {"primary": {"busy": []}}})
        result = await router.execute_tool(
            "google_calendar.check_availability",
            {"start_time": _future_iso(10), "end_time": _future_iso(11)},
        )
        assert result["available"] is True

    @pytest.mark.asyncio
    async def test_busy_slot(self, client: AsyncMock) -> None:
        client.post.return_value = _mock_response(
            {
                "calendars": {
                    "primary": {"busy": [{"start": _future_iso(10), "end": _future_iso(11)}]}
                }
            }
        )
        result = await router.execute_tool(
            "google_calendar.check_availability",
            {"start_time": _future_iso(10), "end_time": _future_iso(11)},
        )
        assert result["available"] is False
        assert len(result["conflicts"]) == 1


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_shutdown_closes_client(self) -> None:
        mock_client = AsyncMock()
        gcal_mod._client = mock_client
        await gcal_mod._gcal_shutdown()
        mock_client.aclose.assert_awaited_once()
        assert gcal_mod._client is None

    @pytest.mark.asyncio
    async def test_custom_calendar_id(self) -> None:
        gcal_mod._client = None
        with patch("empla.integrations.google_calendar.tools.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = AsyncMock()
            await router.initialize(
                {"access_token": "tok", "calendar_id": "work@group.calendar.google.com"}
            )
            assert gcal_mod._calendar_id == "work@group.calendar.google.com"


class TestNetworkErrors:
    @pytest.mark.asyncio
    async def test_timeout_propagates(self, client: AsyncMock) -> None:
        client.get.side_effect = httpx.TimeoutException("timed out")
        with pytest.raises(httpx.TimeoutException):
            await router.execute_tool("google_calendar.get_upcoming_events", {})

    @pytest.mark.asyncio
    async def test_connect_error_propagates(self, client: AsyncMock) -> None:
        client.get.side_effect = httpx.ConnectError("unreachable")
        with pytest.raises(httpx.ConnectError):
            await router.execute_tool("google_calendar.get_upcoming_events", {})
