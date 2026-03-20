"""
empla.services.integrations.credential_injector - OAuth Credential Resolution

Resolves fresh OAuth tokens for an employee's integrations at runtime.
Used by the runner to provide MCP servers with valid credentials before
the employee loop starts.

Architecture:
  Runner startup
       │
       ▼
  CredentialInjector.get_credentials(employee_id, tenant_id)
  ├── Query IntegrationCredential for the employee
  ├── Decrypt via TokenManager
  ├── Refresh if near-expiry (within 5 min)
  └── Return {provider: {access_token, refresh_token, ...}}
       │
       ▼
  Runner injects access_token into MCP server OAUTH_ACCESS_TOKEN env var

This keeps credential logic centralized — tools never touch the DB or
encryption directly.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from empla.models.integration import (
    CredentialType,
    Integration,
    IntegrationCredential,
    IntegrationStatus,
)
from empla.services.integrations.token_manager import TokenManager

logger = logging.getLogger(__name__)


class CredentialInjector:
    """
    Resolves fresh OAuth credentials for an employee's integrations.

    Centralizes all credential access: decryption, refresh, and mapping
    to provider names. Called by the runner at startup to resolve tokens
    before launching the employee loop.

    Example:
        >>> injector = CredentialInjector(session, token_manager)
        >>> creds = await injector.get_credentials(employee_id, tenant_id)
        >>> # creds = {"google_workspace": {"access_token": "ya29...", ...}}
        >>> google_token = creds.get("google_workspace", {}).get("access_token")
    """

    def __init__(
        self,
        session: AsyncSession,
        token_manager: TokenManager,
        refresh_buffer_minutes: int = 5,
    ) -> None:
        self._session = session
        self._tm = token_manager
        self._refresh_buffer = refresh_buffer_minutes

    async def get_credentials(
        self,
        employee_id: UUID,
        tenant_id: UUID,
    ) -> dict[str, dict[str, Any]]:
        """
        Get fresh credentials for all active integrations of an employee.

        Returns a dict keyed by provider name (e.g., "google_workspace")
        with decrypted token data as values. Tokens are refreshed if
        within the buffer window of expiry.

        Args:
            employee_id: The employee whose credentials to resolve
            tenant_id: Tenant for scoping queries

        Returns:
            Dict mapping provider name to credential data.
            Empty dict if no credentials found.

        Note:
            Token refreshes use flush() (not commit) so the caller owns
            the transaction. If a refresh fails, the session is rolled back
            which undoes all prior flushes in the same session. This means
            credential resolution is all-or-nothing per call. The caller
            should commit after this method returns.
        """
        stmt = (
            select(IntegrationCredential)
            .join(
                Integration,
                IntegrationCredential.integration_id == Integration.id,
            )
            .where(
                IntegrationCredential.tenant_id == tenant_id,
                IntegrationCredential.employee_id == employee_id,
                IntegrationCredential.status == "active",
                IntegrationCredential.credential_type == CredentialType.OAUTH_TOKENS,
                Integration.status == IntegrationStatus.ACTIVE,
            )
            .order_by(IntegrationCredential.created_at.desc())
            .options(selectinload(IntegrationCredential.integration))
        )

        result = await self._session.execute(stmt)
        credentials = result.scalars().all()

        if not credentials:
            logger.debug(
                "No active credentials found for employee %s",
                employee_id,
                extra={"employee_id": str(employee_id), "tenant_id": str(tenant_id)},
            )
            return {}

        creds_by_provider: dict[str, dict[str, Any]] = {}

        for cred in credentials:
            integration = cred.integration
            if integration is None:
                logger.warning(
                    "Credential %s has no associated integration — possible orphaned record",
                    cred.id,
                    extra={
                        "credential_id": str(cred.id),
                        "employee_id": str(employee_id),
                        "tenant_id": str(tenant_id),
                    },
                )
                continue

            provider = str(integration.provider)

            # Skip if we already resolved a credential for this provider.
            # Query is ORDER BY created_at DESC, so first seen = newest.
            if provider in creds_by_provider:
                continue

            try:
                data = await self._resolve_credential(cred, integration)
                creds_by_provider[provider] = data
                logger.debug(
                    "Resolved credential for provider %s (employee %s)",
                    provider,
                    employee_id,
                    extra={
                        "employee_id": str(employee_id),
                        "provider": provider,
                        "expires_at": str(cred.expires_at),
                    },
                )
            except Exception:
                logger.error(
                    "Failed to resolve credential for provider %s — "
                    "employee will not have %s credentials this cycle",
                    provider,
                    provider,
                    exc_info=True,
                    extra={
                        "employee_id": str(employee_id),
                        "provider": provider,
                        "credential_id": str(cred.id),
                    },
                )

        return creds_by_provider

    async def get_access_token(
        self,
        employee_id: UUID,
        tenant_id: UUID,
        provider: str,
    ) -> str | None:
        """
        Get a fresh access token for a specific provider.

        Convenience method for tools that just need the access token string.

        Args:
            employee_id: Employee ID
            tenant_id: Tenant ID
            provider: Provider name (e.g., "google_workspace")

        Returns:
            Access token string, or None if unavailable.
        """
        creds = await self.get_credentials(employee_id, tenant_id)
        provider_creds = creds.get(provider, {})
        token = provider_creds.get("access_token")
        if token is None:
            logger.debug(
                "No access_token available for provider %s (employee %s), provider_found=%s",
                provider,
                employee_id,
                provider in creds,
                extra={"employee_id": str(employee_id), "provider": provider},
            )
        return token

    async def _resolve_credential(
        self,
        credential: IntegrationCredential,
        integration: Integration,
    ) -> dict[str, Any]:
        """Decrypt credential data and refresh the token if it expires within the buffer window."""
        data = self._tm.decrypt(
            credential.encrypted_data,
            credential.encryption_key_id,
        )

        if credential.expires_at:
            threshold = datetime.now(UTC) + timedelta(minutes=self._refresh_buffer)
            if credential.expires_at <= threshold:
                data = await self._refresh_token(credential, integration, data)

        return data

    async def _refresh_token(
        self,
        credential: IntegrationCredential,
        integration: Integration,
        current_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Refresh an expiring token."""
        refresh_token = current_data.get("refresh_token")
        if not refresh_token:
            logger.error(
                "Cannot refresh credential %s (provider: %s) — no refresh_token present. "
                "Integration will stop working when token expires at %s. "
                "A human must re-authenticate.",
                credential.id,
                str(integration.provider),
                credential.expires_at,
                extra={
                    "credential_id": str(credential.id),
                    "provider": str(integration.provider),
                },
            )
            return current_data  # Return stale token, let the API call fail naturally

        try:
            from empla.services.integrations.providers import get_provider
            from empla.services.integrations.utils import (
                get_effective_client_secret,
                get_effective_oauth_config,
            )

            provider_impl = get_provider(str(integration.provider))
            effective_config = await get_effective_oauth_config(
                integration, self._session, self._tm
            )
            client_secret = await get_effective_client_secret(integration, self._session, self._tm)

            new_tokens = await provider_impl.refresh_token(
                refresh_token=refresh_token,
                client_id=effective_config["client_id"],
                client_secret=client_secret,
            )

            # Merge new tokens into a copy (don't mutate the decrypted dict in place)
            merged = {**current_data, **new_tokens}

            encrypted, key_id = self._tm.encrypt(merged)
            credential.encrypted_data = encrypted
            credential.encryption_key_id = key_id
            credential.last_refreshed_at = datetime.now(UTC)

            expires_in = new_tokens.get("expires_in")
            if expires_in is None:
                expires_in = 3600
                logger.info(
                    "Provider %s did not return expires_in, defaulting to %ds",
                    str(integration.provider),
                    expires_in,
                    extra={"credential_id": str(credential.id)},
                )
            credential.expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

            await self._session.flush()  # Push changes without committing — caller owns transaction

            logger.info(
                "Refreshed token for credential %s (provider: %s, new expiry: %s)",
                credential.id,
                str(integration.provider),
                credential.expires_at,
                extra={
                    "credential_id": str(credential.id),
                    "provider": str(integration.provider),
                },
            )

            return merged

        except Exception:
            # Rollback to clear any dirty session state from the failed flush
            try:
                await self._session.rollback()
            except Exception:
                logger.debug("Session rollback after refresh failure also failed", exc_info=True)

            logger.error(
                "Token refresh failed for credential %s (provider: %s) — "
                "returning stale token that may already be expired",
                credential.id,
                str(integration.provider),
                exc_info=True,
                extra={
                    "credential_id": str(credential.id),
                    "provider": str(integration.provider),
                },
            )
            return current_data  # Graceful degradation — use current token
