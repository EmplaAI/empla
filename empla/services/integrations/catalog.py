"""
empla.services.integrations.catalog - Provider Catalog

Code-based registry of supported integration providers.
Defines metadata (display name, icon, auth type, scopes) for each provider.
Easy to extend: just add a new entry to PROVIDER_CATALOG.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ProviderMeta:
    """Metadata for an integration provider."""

    display_name: str
    description: str
    icon: str
    auth_type: Literal["user_oauth", "service_account"]
    default_scopes: tuple[str, ...]


PROVIDER_CATALOG: dict[str, ProviderMeta] = {
    "google_workspace": ProviderMeta(
        display_name="Google Workspace",
        description="Gmail, Calendar, Drive",
        icon="google",
        auth_type="user_oauth",
        default_scopes=(
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
        ),
    ),
    "microsoft_graph": ProviderMeta(
        display_name="Microsoft 365",
        description="Outlook, Calendar, OneDrive",
        icon="microsoft",
        auth_type="user_oauth",
        default_scopes=(
            "offline_access",
            "Mail.Read",
            "Mail.Send",
            "Calendars.ReadWrite",
            "User.Read",
        ),
    ),
}


def get_provider_meta(provider: str) -> ProviderMeta | None:
    """Look up provider metadata by key."""
    return PROVIDER_CATALOG.get(provider)


def list_providers() -> list[str]:
    """Return all registered provider keys."""
    return list(PROVIDER_CATALOG.keys())
