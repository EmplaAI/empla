"""
empla.services.integrations.utils - Shared Integration Utilities

Common utility functions used across integration services.
"""

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from empla.models.integration import Integration


class ClientSecretNotConfiguredError(ValueError):
    """Raised when OAuth client secret is not configured."""

    def __init__(self, provider: str, env_key: str) -> None:
        self.provider = provider
        self.env_key = env_key
        super().__init__(
            f"Client secret not configured for {provider}. Set {env_key} environment variable."
        )


def get_oauth_client_secret(integration: "Integration") -> str:
    """
    Get OAuth client secret from secure storage.

    Client secrets are stored in environment variables (dev) or
    secrets manager (production), NOT in the database.

    Args:
        integration: Integration configuration

    Returns:
        Client secret string

    Raises:
        ClientSecretNotConfiguredError: If client secret is not configured

    Example:
        >>> secret = get_oauth_client_secret(integration)
        >>> # Uses OAUTH_GOOGLE_WORKSPACE_CLIENT_SECRET for google_workspace
    """
    # Environment variable format: OAUTH_<PROVIDER>_CLIENT_SECRET
    # e.g., OAUTH_GOOGLE_WORKSPACE_CLIENT_SECRET, OAUTH_MICROSOFT_GRAPH_CLIENT_SECRET
    provider_key = integration.provider.upper()
    env_key = f"OAUTH_{provider_key}_CLIENT_SECRET"
    secret = os.getenv(env_key)

    if not secret:
        raise ClientSecretNotConfiguredError(integration.provider, env_key)

    return secret
