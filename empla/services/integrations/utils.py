"""
empla.services.integrations.utils - Shared Integration Utilities

Common utility functions used across integration services.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from empla.models.integration import Integration
    from empla.services.integrations.token_manager import TokenManager


class ClientSecretNotConfiguredError(ValueError):
    """Raised when OAuth client secret is not configured.

    This covers both tenant credentials (env var missing) and platform
    credentials (PlatformOAuthApp row missing or disabled).
    """

    def __init__(self, provider: str, source: str) -> None:
        self.provider = provider
        self.source = source
        super().__init__(f"Client secret not configured for {provider}. Source: {source}")


def get_oauth_client_secret(integration: Integration) -> str:
    """
    Get OAuth client secret from secure storage (env-var based, for tenant credentials).

    Args:
        integration: Integration configuration

    Returns:
        Client secret string

    Raises:
        ClientSecretNotConfiguredError: If client secret is not configured
    """
    provider_key = integration.provider.upper()
    env_key = f"OAUTH_{provider_key}_CLIENT_SECRET"
    secret = os.getenv(env_key)

    if not secret:
        raise ClientSecretNotConfiguredError(integration.provider, f"env:{env_key}")

    return secret


async def get_effective_oauth_config(
    integration: Integration,
    session: AsyncSession,
    token_manager: TokenManager,
) -> dict[str, Any]:
    """Resolve OAuth config: integration-level or platform-level.

    When ``integration.use_platform_credentials`` is True, the client_id,
    redirect_uri, and scopes are pulled from the matching PlatformOAuthApp
    row instead of the integration's own ``oauth_config``.

    Returns:
        When using platform credentials, dict with keys: client_id,
        redirect_uri, scopes. When using tenant credentials, returns
        the raw ``integration.oauth_config`` dict.
    """
    if not integration.use_platform_credentials:
        raw = integration.oauth_config
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                raw = None
        if not raw or not isinstance(raw, dict):
            raise ClientSecretNotConfiguredError(
                integration.provider,
                "integration.oauth_config is missing or malformed",
            )
        return dict(raw)

    from empla.services.integrations.platform_service import PlatformOAuthAppService

    platform_svc = PlatformOAuthAppService(session, token_manager)
    app = await platform_svc.get_app(integration.provider)
    if not app:
        raise ClientSecretNotConfiguredError(
            integration.provider,
            f"db:PlatformOAuthApp[{integration.provider}]",
        )
    return {
        "client_id": app.client_id,
        "redirect_uri": app.redirect_uri,
        "scopes": list(app.default_scopes),
    }


async def get_effective_client_secret(
    integration: Integration,
    session: AsyncSession,
    token_manager: TokenManager,
) -> str:
    """Resolve client secret: env-var (tenant) or encrypted DB (platform).

    Returns:
        Decrypted client secret string.
    """
    if not integration.use_platform_credentials:
        return get_oauth_client_secret(integration)

    from empla.services.integrations.platform_service import PlatformOAuthAppService

    platform_svc = PlatformOAuthAppService(session, token_manager)
    app = await platform_svc.get_app(integration.provider)
    if not app:
        raise ClientSecretNotConfiguredError(
            integration.provider,
            f"db:PlatformOAuthApp[{integration.provider}]",
        )
    return platform_svc.decrypt_client_secret(app)
