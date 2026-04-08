"""
empla.integrations.webhooks - Webhook Parser Registry

Each integration registers its own webhook parser here.
The API webhook endpoint looks up parsers by provider name.

Usage — create ``empla/integrations/<name>/webhook.py``:

    from empla.integrations.webhooks import register_webhook_parser

    def parse_my_webhook(payload):
        event_type = payload.get("type", "unknown")
        summary = payload.get("message", "")
        return event_type, summary

    register_webhook_parser("my_provider", parse_my_webhook)

That's it. ``autodiscover_parsers()`` scans ``empla/integrations/*/webhook.py``
automatically — no changes needed outside the integration directory.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from collections.abc import Callable
from pathlib import Path
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
    if provider in _registry:
        logger.warning(
            "register_webhook_parser: overwriting existing parser for '%s'",
            provider,
        )
    _registry[provider] = parser
    for alias in aliases or []:
        if alias in _registry:
            logger.warning(
                "register_webhook_parser: overwriting existing parser for alias '%s'",
                alias,
            )
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


def autodiscover_parsers() -> None:
    """Scan empla/integrations/*/webhook.py and import each module.

    Each webhook.py calls register_webhook_parser() at import time,
    so importing is all that's needed to populate the registry.
    No hardcoded module list — just drop a webhook.py in your
    integration directory and it's discovered automatically.
    """
    integrations_dir = Path(__file__).parent
    for pkg in pkgutil.iter_modules([str(integrations_dir)]):
        if not pkg.ispkg:
            continue
        webhook_path = integrations_dir / pkg.name / "webhook.py"
        if not webhook_path.exists():
            continue
        module_name = f"empla.integrations.{pkg.name}.webhook"
        try:
            importlib.import_module(module_name)
        except Exception:
            logger.warning("Failed to load webhook parser from %s", module_name, exc_info=True)
