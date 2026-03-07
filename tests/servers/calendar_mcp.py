"""
Calendar MCP Server - In-memory calendar for E2E testing.

Implements MCP tools for calendar operations.

Usage:
    python -m tests.servers.calendar_mcp --http --port 9101
"""

import argparse
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# In-memory state
events: dict[str, dict[str, Any]] = {}


def _reset() -> None:
    events.clear()


def get_upcoming_events(hours: int = 24) -> list[dict[str, Any]]:
    """Get events within the next N hours."""
    now = datetime.now(UTC)
    cutoff = now + timedelta(hours=hours)
    upcoming = []
    for event in events.values():
        try:
            start = datetime.fromisoformat(event["start"])
        except (ValueError, KeyError):
            logger.warning("Skipping event with invalid/missing start: %s", event.get("id"))
            continue
        if now <= start <= cutoff:
            upcoming.append(event)
    upcoming.sort(key=lambda e: e["start"])
    return upcoming


def create_event(
    title: str,
    start: str,
    end: str,
    attendees: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new calendar event."""
    event_id = str(uuid4())
    event = {
        "id": event_id,
        "title": title,
        "start": start,
        "end": end,
        "attendees": attendees or [],
        "created_at": datetime.now(UTC).isoformat(),
    }
    events[event_id] = event
    return event


def list_events(date: str | None = None) -> list[dict[str, Any]]:
    """List all events, optionally filtered by date (YYYY-MM-DD)."""
    if date:
        return [e for e in events.values() if e["start"].startswith(date)]
    return list(events.values())


# MCP tool definitions
TOOLS = [
    {
        "name": "get_upcoming_events",
        "description": "Get calendar events within the next N hours.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "default": 24, "description": "Hours to look ahead"},
            },
        },
    },
    {
        "name": "create_event",
        "description": "Create a new calendar event.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Event title"},
                "start": {"type": "string", "description": "Start time (ISO 8601)"},
                "end": {"type": "string", "description": "End time (ISO 8601)"},
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Email addresses of attendees",
                    "default": [],
                },
            },
            "required": ["title", "start", "end"],
        },
    },
    {
        "name": "list_events",
        "description": "List all calendar events, optionally filtered by date.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Filter by date (YYYY-MM-DD). Omit for all events.",
                },
            },
        },
    },
]


def handle_tool_call(name: str, arguments: dict[str, Any]) -> Any:
    """Route MCP tool call to implementation."""
    if name == "get_upcoming_events":
        return get_upcoming_events(hours=arguments.get("hours", 24))
    if name == "create_event":
        return create_event(
            title=arguments["title"],
            start=arguments["start"],
            end=arguments["end"],
            attendees=arguments.get("attendees"),
        )
    if name == "list_events":
        return list_events(date=arguments.get("date"))
    raise ValueError(f"Unknown tool: {name}")


# ============================================================================
# HTTP transport (FastAPI + SSE for MCP)
# ============================================================================


def create_http_app() -> Any:
    """Create FastAPI app with MCP-compatible endpoints."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    mcp_app = FastAPI(title="empla Test Calendar MCP")

    @mcp_app.get("/tools")
    async def list_tools() -> JSONResponse:
        return JSONResponse(content=TOOLS)

    @mcp_app.post("/tools/{tool_name}")
    async def call_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> JSONResponse:
        result = handle_tool_call(tool_name, arguments or {})
        return JSONResponse(content={"result": result})

    @mcp_app.post("/reset")
    async def reset() -> JSONResponse:
        _reset()
        return JSONResponse(content={"status": "reset"})

    @mcp_app.post("/scenario/load")
    async def load_scenario(data: dict[str, Any]) -> JSONResponse:
        for event_data in data.get("events", []):
            if "id" not in event_data:
                event_data["id"] = str(uuid4())
            events[event_data["id"]] = event_data
        return JSONResponse(content={"loaded": len(data.get("events", []))})

    return mcp_app


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="empla Test Calendar MCP Server")
    parser.add_argument("--http", action="store_true", help="Run as HTTP server")
    parser.add_argument("--port", type=int, default=9101)
    args = parser.parse_args()

    if args.http:
        app = create_http_app()
        uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")
    else:
        # STDIO MCP (for future use)
        import sys

        for line in sys.stdin:
            msg_id = None
            try:
                msg = json.loads(line.strip())
                msg_id = msg.get("id")
                if msg.get("method") == "tools/list":
                    result = {"tools": TOOLS}
                elif msg.get("method") == "tools/call":
                    params = msg.get("params", {})
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    handle_tool_call(params["name"], params.get("arguments", {}))
                                ),
                            }
                        ]
                    }
                else:
                    result = {}
                response = {"jsonrpc": "2.0", "id": msg_id, "result": result}
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            except Exception as e:
                sys.stderr.write(f"Error: {e}\n")
                error_response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32603, "message": str(e)},
                }
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()
