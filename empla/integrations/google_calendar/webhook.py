"""
empla.integrations.google_calendar.webhook - Google Calendar Webhook Parser

Parses Google push notification payloads into normalized (event_type, summary) tuples.

Note: Google Calendar push notifications send most metadata via HTTP headers
(X-Goog-Resource-State, X-Goog-Channel-ID). The JSON body may be minimal.
This parser handles what's available in the body; header-based enrichment
can be added when the webhook endpoint passes headers through.

Ref: https://developers.google.com/calendar/api/guides/push
"""

from __future__ import annotations

from typing import Any

from empla.integrations.webhooks import register_webhook_parser


def parse_google_webhook(payload: dict[str, Any]) -> tuple[str, str]:
    """Extract event type and summary from Google push notification body."""
    resource_type = payload.get("resourceType", "unknown")
    change_type = payload.get("changeType", "unknown")
    return f"{resource_type}.{change_type}", ""


register_webhook_parser("google_calendar", parse_google_webhook, aliases=["google_workspace"])
