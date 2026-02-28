"""
empla.services.integrations - Integration & OAuth Service Layer

This package provides services for managing third-party integrations:
- OAuth flow handling (authorization, callback, token exchange)
- Token encryption and secure storage
- Automatic token refresh
- Multi-provider support (Google Workspace, Microsoft Graph)

Usage:
    >>> from empla.services.integrations import (
    ...     IntegrationService,
    ...     OAuthService,
    ...     TokenManager,
    ... )
    >>>
    >>> # Get credentials for an employee
    >>> service = IntegrationService(session, token_manager)
    >>> result = await service.get_credential_for_employee(
    ...     tenant_id=tenant.id,
    ...     employee_id=employee.id,
    ...     provider=IntegrationProvider.GOOGLE_WORKSPACE,
    ... )
    >>> if result:
    ...     integration, credential, data = result
    ...     access_token = data["access_token"]
"""

from empla.services.integrations.integration_service import (
    CredentialNotFoundError,
    IntegrationError,
    IntegrationNotFoundError,
    IntegrationService,
    RevocationError,
)
from empla.services.integrations.key_provider import (
    EnvironmentKeyProvider,
    KeyNotFoundError,
    KeyProvider,
    KeyProviderError,
    NoKeysConfiguredError,
    generate_encryption_key,
    get_key_provider,
    set_key_provider,
)
from empla.services.integrations.oauth_service import (
    InvalidStateError,
    OAuthError,
    OAuthService,
    TokenExchangeError,
)
from empla.services.integrations.platform_service import PlatformOAuthAppService
from empla.services.integrations.token_manager import (
    DecryptionError,
    RefreshError,
    TokenManager,
    TokenManagerError,
    get_token_manager,
    set_token_manager,
)
from empla.services.integrations.utils import (
    ClientSecretNotConfiguredError,
    get_effective_client_secret,
    get_effective_oauth_config,
    get_oauth_client_secret,
)

__all__ = [
    "ClientSecretNotConfiguredError",
    "CredentialNotFoundError",
    "DecryptionError",
    "EnvironmentKeyProvider",
    "IntegrationError",
    "IntegrationNotFoundError",
    "IntegrationService",
    "InvalidStateError",
    "KeyNotFoundError",
    "KeyProvider",
    "KeyProviderError",
    "NoKeysConfiguredError",
    "OAuthError",
    "OAuthService",
    "PlatformOAuthAppService",
    "RefreshError",
    "RevocationError",
    "TokenExchangeError",
    "TokenManager",
    "TokenManagerError",
    "generate_encryption_key",
    "get_effective_client_secret",
    "get_effective_oauth_config",
    "get_key_provider",
    "get_oauth_client_secret",
    "get_token_manager",
    "set_key_provider",
    "set_token_manager",
]
