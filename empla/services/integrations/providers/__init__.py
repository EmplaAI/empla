"""
empla.services.integrations.providers - OAuth Provider Implementations

This package contains provider-specific OAuth implementations:
- GoogleWorkspaceProvider: Google OAuth 2.0 with Gmail, Calendar, etc.
- MicrosoftGraphProvider: Microsoft OAuth 2.0 with Outlook, Calendar, etc.

Each provider implements the OAuthProvider protocol for consistent behavior.

Usage:
    >>> from empla.services.integrations.providers import (
    ...     get_provider,
    ...     GoogleWorkspaceProvider,
    ... )
    >>>
    >>> provider = get_provider("google_workspace")
    >>> auth_url = provider.get_authorization_url(
    ...     client_id="...",
    ...     redirect_uri="https://app.empla.ai/oauth/callback",
    ...     scopes=["https://www.googleapis.com/auth/gmail.modify"],
    ...     state="random-state",
    ... )
"""

from empla.services.integrations.providers.base import OAuthProvider
from empla.services.integrations.providers.google import GoogleWorkspaceProvider
from empla.services.integrations.providers.microsoft import MicrosoftGraphProvider

# Provider registry
_PROVIDERS: dict[str, type[OAuthProvider]] = {
    "google_workspace": GoogleWorkspaceProvider,
    "microsoft_graph": MicrosoftGraphProvider,
}


def get_provider(provider_name: str) -> OAuthProvider:
    """
    Get an OAuth provider instance by name.

    Args:
        provider_name: Provider name (e.g., "google_workspace", "microsoft_graph")

    Returns:
        OAuthProvider instance

    Raises:
        ValueError: If provider is not supported

    Example:
        >>> provider = get_provider("google_workspace")
        >>> auth_url = provider.get_authorization_url(...)
    """
    if provider_name not in _PROVIDERS:
        raise ValueError(
            f"Unknown provider: {provider_name}. Supported providers: {list(_PROVIDERS.keys())}"
        )

    return _PROVIDERS[provider_name]()


__all__ = [
    "GoogleWorkspaceProvider",
    "MicrosoftGraphProvider",
    "OAuthProvider",
    "get_provider",
]
