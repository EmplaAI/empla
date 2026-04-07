"""
empla.integrations.webhooks - Webhook Parser Registry

Each integration registers its own webhook parser here.
The API webhook endpoint looks up parsers by provider name.

Usage in an integration module:

    from empla.integrations.webhooks import register_webhook_parser

    def parse_my_webhook(payload):
        event_type = payload.get("type", "unknown")
        summary = payload.get("message", "")
        return event_type, summary

    register_webhook_parser("my_provider", parse_my_webhook)

The webhook endpoint calls:

    from empla.integrations.webhooks import get_webhook_parser
    parser = get_webhook_parser(provider)  # returns parse func or generic fallback
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Type: (payload: dict | list) -> (event_type: str, summary: str)
WebhookParser = Callable[[Any], tuple[str, str]]

_registry: dict[str, WebhookParser] = {}


def register_webhook_parser(
    provider: str,
    parser: WebhookParser,
    *,
    aliases: list[str] | None = None,
) -> None:
    """Register a webhook parser for a provider.

    Args:
        provider: Primary provider name (e.g. "hubspot").
        parser: Callable that takes raw payload and returns (event_type, summary).
        aliases: Optional additional provider names that use the same parser
            (e.g. ["google_workspace"] for google_calendar).
    """
    _registry[provider] = parser
    for alias in aliases or []:
        _registry[alias] = parser


def get_webhook_parser(provider: str) -> WebhookParser:
    """Get the parser for a provider, falling back to the generic parser."""
    return _registry.get(provider, _parse_generic)


def _parse_generic(payload: Any) -> tuple[str, str]:
    """Fallback parser for providers without a registered parser."""
    if isinstance(payload, dict):
        return payload.get("event_type", "unknown"), payload.get("summary", "")
    return "unknown", ""


def list_registered_providers() -> list[str]:
    """List all providers with registered webhook parsers."""
    return sorted(_registry.keys())
