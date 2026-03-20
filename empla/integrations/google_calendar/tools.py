"""
empla.integrations.google_calendar.tools - Google Calendar Tools

Direct Google Calendar API v3 integration via httpx. OAuth token from config.

API docs: https://developers.google.com/calendar/api/v3/reference

Example:
    >>> from empla.integrations.google_calendar.tools import router
    >>> await router.initialize({"access_token": "ya29.xxx"})
    >>> events = await router.execute_tool("google_calendar.get_upcoming_events", {})
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from empla.integrations.router import IntegrationRouter

logger = logging.getLogger(__name__)

GCAL_API = "https://www.googleapis.com/calendar/v3"

# Module-level state set during initialize().
# NOTE: Single-tenant per process (runner spawns one process per employee).
_client: httpx.AsyncClient | None = None
_calendar_id: str = "primary"


def _api() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("Google Calendar not initialized. Call router.initialize() first.")
    return _client


def _cal_path(suffix: str = "") -> str:
    """Build a calendar-scoped API path with URL-encoded calendar ID."""
    safe_id = quote(_calendar_id, safe="")
    return f"/calendars/{safe_id}{suffix}"


async def _call(method: str, path: str, operation: str, **kwargs: Any) -> dict[str, Any]:
    """Make an API call with error handling and logging."""
    logger.debug("google_calendar.%s: %s %s", operation, method.upper(), path)
    try:
        client = _api()
        resp = await getattr(client, method)(path, **kwargs)
        if resp.status_code >= 400:
            # Log status + path only — response body may contain PII
            logger.error(
                "Google Calendar API error in %s: %s %s",
                operation,
                resp.status_code,
                path,
                extra={"operation": operation, "status": resp.status_code},
            )
        resp.raise_for_status()
        # DELETE returns 204 with no body
        if resp.status_code == 204:
            return {}
        return resp.json()
    except httpx.HTTPStatusError:
        raise
    except httpx.TimeoutException as e:
        logger.error("Google Calendar timeout in %s: %s", operation, e)
        raise
    except httpx.ConnectError as e:
        logger.error("Google Calendar unreachable in %s: %s", operation, e)
        raise
    except Exception as e:
        logger.error("Google Calendar unexpected error in %s: %s", operation, e, exc_info=True)
        raise


async def _gcal_init(**config: Any) -> None:
    global _client, _calendar_id  # noqa: PLW0603
    # Close previous client if re-initializing (e.g., token refresh)
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            logger.debug("Previous Google Calendar client close failed (may already be closed)")
    token = config.get("access_token")
    if not token:
        raise ValueError("Google Calendar requires 'access_token' in config")
    _calendar_id = config.get("calendar_id", "primary")
    _client = httpx.AsyncClient(
        base_url=GCAL_API,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30.0,
    )
    logger.info("Google Calendar connector initialized (calendar: %s)", _calendar_id)


async def _gcal_shutdown() -> None:
    global _client  # noqa: PLW0603
    if _client:
        try:
            await _client.aclose()
        except Exception:
            logger.debug("Google Calendar client close failed during shutdown")
        finally:
            _client = None
        logger.info("Google Calendar connector shut down")


router = IntegrationRouter("google_calendar", on_init=_gcal_init, on_shutdown=_gcal_shutdown)


# ============================================================================
# Events
# ============================================================================


@router.tool()
async def get_upcoming_events(days: int = 7, limit: int = 20) -> list[dict]:
    """Get upcoming calendar events within the next N days."""
    now = datetime.now(UTC)
    data = await _call(
        "get",
        _cal_path("/events"),
        "get_upcoming_events",
        params={
            "timeMin": now.isoformat(),
            "timeMax": (now + timedelta(days=days)).isoformat(),
            "maxResults": min(limit, 250),
            "singleEvents": "true",
            "orderBy": "startTime",
        },
    )
    return [
        {
            "id": e["id"],
            "title": e.get("summary", "(no title)"),
            "start_time": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date", ""),
            "end_time": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date", ""),
            "description": e.get("description"),
            "location": e.get("location"),
            "attendees": [a.get("email", "") for a in e.get("attendees", [])],
        }
        for e in data.get("items", [])
    ]


@router.tool()
async def create_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    attendees: list[str] | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    """Create a new calendar event. Times in ISO 8601 format."""
    body: dict[str, Any] = {
        "summary": title,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]

    data = await _call("post", _cal_path("/events"), "create_event", json=body)
    return {
        "id": data["id"],
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "link": data.get("htmlLink"),
    }


@router.tool()
async def update_event(
    event_id: str,
    title: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Update an existing calendar event."""
    body: dict[str, Any] = {}
    if title is not None:
        body["summary"] = title
    if start_time is not None:
        body["start"] = {"dateTime": start_time}
    if end_time is not None:
        body["end"] = {"dateTime": end_time}
    if description is not None:
        body["description"] = description
    if not body:
        raise ValueError("No fields to update")

    safe_id = quote(event_id, safe="")
    await _call("patch", _cal_path(f"/events/{safe_id}"), "update_event", json=body)
    return {"id": event_id, "updated": list(body.keys())}


@router.tool()
async def delete_event(event_id: str) -> dict[str, Any]:
    """Delete a calendar event."""
    safe_id = quote(event_id, safe="")
    await _call("delete", _cal_path(f"/events/{safe_id}"), "delete_event")
    return {"success": True, "deleted_id": event_id}


@router.tool()
async def check_availability(start_time: str, end_time: str) -> dict[str, Any]:
    """Check if a time slot is free (no conflicting events)."""
    data = await _call(
        "post",
        "/freeBusy",
        "check_availability",
        json={
            "timeMin": start_time,
            "timeMax": end_time,
            "items": [{"id": _calendar_id}],
        },
    )
    busy_periods = data.get("calendars", {}).get(_calendar_id, {}).get("busy", [])
    return {
        "available": len(busy_periods) == 0,
        "conflicts": busy_periods,
    }
