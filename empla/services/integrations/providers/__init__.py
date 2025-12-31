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

import logging
from typing import Any

from empla.services.integrations.providers.base import OAuthProvider
from empla.services.integrations.providers.google import GoogleWorkspaceProvider
from empla.services.integrations.providers.microsoft import MicrosoftGraphProvider

logger = logging.getLogger(__name__)

# Provider registry
_PROVIDERS: dict[str, type[OAuthProvider]] = {
    "google_workspace": GoogleWorkspaceProvider,
    "microsoft_graph": MicrosoftGraphProvider,
}


def get_provider(provider_name: str, **kwargs: Any) -> OAuthProvider:
    """
    Get an OAuth provider instance by name.

    Args:
        provider_name: Provider name (e.g., "google_workspace", "microsoft_graph")
        **kwargs: Optional provider-specific arguments (e.g., tenant for Microsoft)

    Returns:
        OAuthProvider instance

    Raises:
        ValueError: If provider_name is None, empty, or not supported

    Example:
        >>> provider = get_provider("google_workspace")
        >>> auth_url = provider.get_authorization_url(...)

        >>> # Microsoft with specific tenant
        >>> provider = get_provider("microsoft_graph", tenant="contoso.onmicrosoft.com")
    """
    # Validate input
    if not provider_name:
        raise ValueError("provider_name must not be None or empty")

    if provider_name not in _PROVIDERS:
        raise ValueError(
            f"Unknown provider: {provider_name}. Supported providers: {list(_PROVIDERS.keys())}"
        )

    provider_class = _PROVIDERS[provider_name]
    provider = provider_class(**kwargs)

    logger.info(
        f"Created OAuth provider instance: {provider_name}",
        extra={"provider": provider_name, "kwargs": list(kwargs.keys())},
    )

    return provider


__all__ = [
    "GoogleWorkspaceProvider",
    "MicrosoftGraphProvider",
    "OAuthProvider",
    "get_provider",
]
