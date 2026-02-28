"""
empla.services.integrations.oauth_service - OAuth Flow Management

Handles OAuth 2.0 authorization flows:
- Authorization URL generation with PKCE
- Callback handling and token exchange
- State management (CSRF protection)
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.integration import (
    Integration,
    IntegrationCredential,
    IntegrationOAuthState,
)
from empla.services.integrations.providers import get_provider
from empla.services.integrations.providers.google import generate_pkce_pair
from empla.services.integrations.token_manager import TokenManager

logger = logging.getLogger(__name__)


class OAuthError(Exception):
    """Base exception for OAuth errors."""


class InvalidStateError(OAuthError):
    """Raised when OAuth state is invalid or expired."""


class TokenExchangeError(OAuthError):
    """Raised when token exchange fails."""


class OAuthService:
    """
    Handles OAuth 2.0 authorization flows.

    Manages the complete OAuth lifecycle:
    1. Generate authorization URL with state and PKCE
    2. Handle callback with state validation
    3. Exchange code for tokens
    4. Store encrypted credentials

    Example:
        >>> service = OAuthService(session, token_manager)
        >>> auth_url, state = await service.generate_authorization_url(
        ...     integration=integration,
        ...     employee_id=employee.id,
        ...     user_id=user.id,
        ... )
        >>> # Redirect user to auth_url
        >>> # After callback:
        >>> credential, redirect = await service.handle_callback(
        ...     state="...",
        ...     code="...",
        ... )
    """

    # OAuth state expiry (10 minutes)
    STATE_EXPIRY_MINUTES = 10

    def __init__(
        self,
        session: AsyncSession,
        token_manager: TokenManager,
    ) -> None:
        """
        Initialize OAuth service.

        Args:
            session: Database session
            token_manager: Token encryption manager
        """
        self.session = session
        self.token_manager = token_manager

    async def generate_authorization_url(
        self,
        integration: Integration,
        employee_id: UUID,
        user_id: UUID,
        redirect_after: str | None = None,
        use_pkce: bool = True,
    ) -> tuple[str, str]:
        """
        Generate OAuth authorization URL.

        Creates an authorization URL with state (CSRF protection) and
        optionally PKCE. Stores state in database for validation.

        Args:
            integration: Integration to authorize
            employee_id: Employee to authorize for
            user_id: User initiating the flow
            redirect_after: Where to redirect after callback
            use_pkce: Whether to use PKCE (recommended)

        Returns:
            Tuple of (authorization_url, state)

        Example:
            >>> url, state = await service.generate_authorization_url(
            ...     integration=integration,
            ...     employee_id=employee.id,
            ...     user_id=user.id,
            ...     redirect_after="/dashboard/integrations",
            ... )
        """
        # Generate secure state
        state = secrets.token_urlsafe(32)

        # Generate PKCE pair if enabled
        code_verifier = None
        code_challenge = None
        if use_pkce:
            code_verifier, code_challenge = generate_pkce_pair()

        # Get provider
        provider = get_provider(integration.provider)

        # Resolve effective config (platform or tenant)
        from empla.services.integrations.utils import get_effective_oauth_config

        effective_config = await get_effective_oauth_config(
            integration, self.session, self.token_manager
        )

        # Get scopes from effective config
        scopes = effective_config.get("scopes", provider.get_default_scopes())

        # Build authorization URL
        auth_url = provider.get_authorization_url(
            client_id=effective_config["client_id"],
            redirect_uri=effective_config["redirect_uri"],
            scopes=scopes,
            state=state,
            code_challenge=code_challenge,
        )

        # Store state for validation
        oauth_state = IntegrationOAuthState(
            tenant_id=integration.tenant_id,
            state=state,
            integration_id=integration.id,
            employee_id=employee_id,
            initiated_by=user_id,
            redirect_uri=redirect_after or "/",
            code_verifier=code_verifier,
            expires_at=datetime.now(UTC) + timedelta(minutes=self.STATE_EXPIRY_MINUTES),
        )
        self.session.add(oauth_state)
        await self.session.commit()

        logger.info(
            f"Generated OAuth authorization URL for employee {employee_id}",
            extra={
                "employee_id": str(employee_id),
                "integration_id": str(integration.id),
                "provider": integration.provider,
                "use_pkce": use_pkce,
            },
        )

        return auth_url, state

    async def handle_callback(
        self,
        state: str,
        code: str,
    ) -> tuple[IntegrationCredential, str]:
        """
        Handle OAuth callback.

        Validates state, exchanges code for tokens, and stores encrypted credential.

        Args:
            state: State parameter from callback
            code: Authorization code from callback

        Returns:
            Tuple of (credential, redirect_uri)

        Raises:
            InvalidStateError: If state is invalid or expired
            TokenExchangeError: If token exchange fails
        """
        # Validate state
        result = await self.session.execute(
            select(IntegrationOAuthState).where(
                IntegrationOAuthState.state == state,
                IntegrationOAuthState.expires_at > datetime.now(UTC),
            )
        )
        oauth_state = result.scalar_one_or_none()

        if not oauth_state:
            logger.warning(f"Invalid or expired OAuth state: {state[:8]}...")
            raise InvalidStateError("Invalid or expired OAuth state")

        # Get integration
        integration = await self.session.get(Integration, oauth_state.integration_id)
        if not integration:
            raise InvalidStateError("Integration not found")

        # Get provider
        provider = get_provider(integration.provider)

        # Resolve effective config (platform or tenant)
        from empla.services.integrations.utils import (
            get_effective_client_secret,
            get_effective_oauth_config,
        )

        effective_config = await get_effective_oauth_config(
            integration, self.session, self.token_manager
        )
        client_secret = await get_effective_client_secret(
            integration, self.session, self.token_manager
        )

        try:
            # Exchange code for tokens
            tokens = await provider.exchange_code(
                code=code,
                client_id=effective_config["client_id"],
                client_secret=client_secret,
                redirect_uri=effective_config["redirect_uri"],
                code_verifier=oauth_state.code_verifier,
            )
        except Exception as e:
            logger.error(
                f"Token exchange failed: {e}",
                extra={
                    "integration_id": str(integration.id),
                    "provider": integration.provider,
                },
            )
            raise TokenExchangeError(f"Token exchange failed: {e}") from e

        # Get user info from token
        try:
            user_info = await provider.get_user_info(tokens["access_token"])
        except Exception as e:
            logger.error(
                "Failed to get user info after token exchange",
                extra={
                    "integration_id": str(integration.id),
                    "provider": integration.provider,
                    "error": str(e),
                },
                exc_info=True,
            )
            user_info = {"_user_info_error": str(e)}

        # Encrypt and store credential
        encrypted, key_id = self.token_manager.encrypt(tokens)

        # Check for existing credential (update instead of create)
        existing_result = await self.session.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.employee_id == oauth_state.employee_id,
                IntegrationCredential.integration_id == oauth_state.integration_id,
                IntegrationCredential.deleted_at.is_(None),
            )
        )
        existing_credential = existing_result.scalar_one_or_none()

        token_metadata: dict[str, Any] = {
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "scopes": tokens.get("scope", "").split() if tokens.get("scope") else [],
        }
        if "_user_info_error" in user_info:
            token_metadata["_user_info_error"] = user_info["_user_info_error"]

        if existing_credential:
            # Update existing credential
            existing_credential.encrypted_data = encrypted
            existing_credential.encryption_key_id = key_id
            existing_credential.token_metadata = token_metadata
            existing_credential.status = "active"
            existing_credential.issued_at = datetime.now(UTC)
            existing_credential.expires_at = datetime.now(UTC) + timedelta(
                seconds=tokens.get("expires_in", 3600)
            )
            existing_credential.last_refreshed_at = None
            credential = existing_credential
        else:
            # Create new credential
            credential = IntegrationCredential(
                tenant_id=integration.tenant_id,
                integration_id=integration.id,
                employee_id=oauth_state.employee_id,
                credential_type="oauth_tokens",
                encrypted_data=encrypted,
                encryption_key_id=key_id,
                token_metadata=token_metadata,
                status="active",
                issued_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(seconds=tokens.get("expires_in", 3600)),
            )
            self.session.add(credential)

        # Delete used state
        await self.session.delete(oauth_state)
        await self.session.commit()
        await self.session.refresh(credential)

        logger.info(
            f"OAuth credential created/updated for employee {credential.employee_id}",
            extra={
                "credential_id": str(credential.id),
                "employee_id": str(credential.employee_id),
                "provider": integration.provider,
                "email": user_info.get("email"),
            },
        )

        return credential, oauth_state.redirect_uri

    async def cleanup_expired_states(self) -> int:
        """
        Clean up expired OAuth states.

        Should be called periodically (e.g., every hour) to remove
        expired state records.

        Returns:
            Number of states deleted
        """
        from sqlalchemy import delete

        result = await self.session.execute(
            delete(IntegrationOAuthState).where(
                IntegrationOAuthState.expires_at <= datetime.now(UTC)
            )
        )
        await self.session.commit()

        count = result.rowcount
        if count > 0:
            logger.info(f"Cleaned up {count} expired OAuth states")

        return count
