"""
empla.integrations.hubspot.webhook - HubSpot Webhook Parser

Parses HubSpot webhook payloads into normalized (event_type, summary) tuples.
HubSpot sends an array of subscription events; we extract the first.

Ref: https://developers.hubspot.com/docs/api/webhooks
"""

from __future__ import annotations

from typing import Any

from empla.integrations.webhooks import register_webhook_parser


def parse_hubspot_webhook(payload: dict[str, Any] | list[Any]) -> tuple[str, str]:
    """Extract event type and summary from HubSpot webhook payload.

    HubSpot sends an array of events per delivery. We take the first
    event and extract subscriptionType + objectId.
    """
    events = payload if isinstance(payload, list) else [payload]
    if not events:
        return "unknown", ""
    event = events[0] if isinstance(events[0], dict) else {}
    sub_type = event.get("subscriptionType", "unknown")
    object_id = event.get("objectId", "")
    return sub_type, f"objectId={object_id}" if object_id else ""


register_webhook_parser("hubspot", parse_hubspot_webhook)
