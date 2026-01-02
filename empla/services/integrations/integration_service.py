"""
empla.services.integrations.integration_service - Integration Management

Manages integration lifecycle:
- Create/update/delete integrations
- Get credentials for employees
- Service account setup
- Credential revocation
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.integration import (
    CredentialType,
    Integration,
    IntegrationAuthType,
    IntegrationCredential,
    IntegrationProvider,
)
from empla.services.integrations.providers import get_provider
from empla.services.integrations.token_manager import TokenManager

logger = logging.getLogger(__name__)


class IntegrationError(Exception):
    """Base exception for integration errors."""


class IntegrationNotFoundError(IntegrationError):
    """Raised when integration is not found."""


class CredentialNotFoundError(IntegrationError):
    """Raised when credential is not found."""


class RevocationError(IntegrationError):
    """Raised when credential revocation fails with provider."""

    def __init__(
        self,
        message: str,
        credential_id: UUID | None = None,
        provider_error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.credential_id = credential_id
        self.provider_error = provider_error


class IntegrationService:
    """
    Manages integration lifecycle.

    Provides CRUD operations for integrations and credentials:
    - Create/list/delete integrations (admin operations)
    - Setup service accounts
    - Get credentials for employees (with auto-refresh)
    - Revoke credentials

    Example:
        >>> service = IntegrationService(session, token_manager)
        >>>
        >>> # Create integration
        >>> integration = await service.create_integration(
        ...     tenant_id=tenant.id,
        ...     provider=IntegrationProvider.GOOGLE_WORKSPACE,
        ...     auth_type=IntegrationAuthType.USER_OAUTH,
        ...     display_name="Google Workspace",
        ...     oauth_config={"client_id": "...", "redirect_uri": "..."},
        ...     enabled_by=user.id,
        ... )
        >>>
        >>> # Get credential for employee
        >>> result = await service.get_credential_for_employee(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     provider=IntegrationProvider.GOOGLE_WORKSPACE,
        ... )
        >>> if result:
        ...     integration, credential, data = result
        ...     access_token = data["access_token"]
    """

    def __init__(
        self,
        session: AsyncSession,
        token_manager: TokenManager,
    ) -> None:
        """
        Initialize integration service.

        Args:
            session: Database session
            token_manager: Token encryption manager
        """
        self.session = session
        self.token_manager = token_manager

    async def create_integration(
        self,
        tenant_id: UUID,
        provider: IntegrationProvider,
        auth_type: IntegrationAuthType,
        display_name: str,
        oauth_config: dict[str, Any],
        enabled_by: UUID,
    ) -> Integration:
        """
        Create a new integration for tenant.

        Args:
            tenant_id: Tenant ID
            provider: Integration provider
            auth_type: Authentication type
            display_name: Human-readable name
            oauth_config: OAuth configuration (client_id, redirect_uri, scopes)
            enabled_by: User creating the integration

        Returns:
            Created integration

        Example:
            >>> integration = await service.create_integration(
            ...     tenant_id=tenant.id,
            ...     provider=IntegrationProvider.GOOGLE_WORKSPACE,
            ...     auth_type=IntegrationAuthType.USER_OAUTH,
            ...     display_name="Google Workspace",
            ...     oauth_config={
            ...         "client_id": "...",
            ...         "redirect_uri": "https://app.empla.ai/oauth/callback",
            ...         "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
            ...     },
            ...     enabled_by=user.id,
            ... )
        """
        integration = Integration(
            tenant_id=tenant_id,
            provider=provider.value,
            auth_type=auth_type.value,
            display_name=display_name,
            oauth_config=oauth_config,
            status="active",
            enabled_by=enabled_by,
            enabled_at=datetime.now(UTC),
        )

        self.session.add(integration)
        await self.session.commit()
        await self.session.refresh(integration)

        logger.info(
            f"Created integration {integration.id} for tenant {tenant_id}",
            extra={
                "integration_id": str(integration.id),
                "tenant_id": str(tenant_id),
                "provider": provider.value,
                "auth_type": auth_type.value,
            },
        )

        return integration

    async def get_integration(
        self,
        tenant_id: UUID,
        provider: IntegrationProvider,
    ) -> Integration | None:
        """
        Get integration by tenant and provider.

        Args:
            tenant_id: Tenant ID
            provider: Integration provider

        Returns:
            Integration or None if not found
        """
        result = await self.session.execute(
            select(Integration).where(
                Integration.tenant_id == tenant_id,
                Integration.provider == provider.value,
                Integration.status == "active",
                Integration.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_integrations(
        self,
        tenant_id: UUID,
    ) -> list[Integration]:
        """
        List all integrations for tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            List of integrations
        """
        result = await self.session.execute(
            select(Integration).where(
                Integration.tenant_id == tenant_id,
                Integration.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def delete_integration(
        self,
        integration: Integration,
        revoke_credentials: bool = True,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Delete an integration and optionally revoke all credentials.

        This method attempts to revoke all credentials with their providers
        before deleting the integration. If any revocation fails, the behavior
        depends on the `force` parameter.

        Args:
            integration: Integration to delete
            revoke_credentials: Whether to revoke credentials with provider
            force: If True, delete the integration even if some credential
                   revocations fail. If False (default), raise RevocationError
                   if any credential fails to revoke.

        Returns:
            Dict with deletion results:
            - integration_id: UUID of deleted integration
            - credentials_revoked: Number of successfully revoked credentials
            - credentials_failed: List of credential IDs that failed to revoke
            - fully_revoked: True if all credentials were successfully revoked

        Raises:
            RevocationError: If any credential fails to revoke and force=False.
                            The error contains the credential_id of the first failure.

        Example:
            >>> # Normal deletion - fails if any revocation fails
            >>> result = await service.delete_integration(integration)
            >>> if result["fully_revoked"]:
            ...     print("All credentials revoked")
            >>>
            >>> # Force deletion - deletes even if revocations fail
            >>> result = await service.delete_integration(integration, force=True)
            >>> for cred_id in result["credentials_failed"]:
            ...     print(f"Warning: Credential {cred_id} may still be valid at provider")
        """
        credentials_revoked = 0
        credentials_failed: list[UUID] = []
        first_error: RevocationError | None = None

        if revoke_credentials:
            # Get all credentials
            result = await self.session.execute(
                select(IntegrationCredential).where(
                    IntegrationCredential.integration_id == integration.id,
                    IntegrationCredential.deleted_at.is_(None),
                )
            )
            credentials = list(result.scalars().all())

            # Revoke each credential
            for credential in credentials:
                try:
                    await self.revoke_credential(credential, integration)
                    credentials_revoked += 1
                except RevocationError as e:
                    credentials_failed.append(credential.id)
                    if first_error is None:
                        first_error = e
                    logger.error(
                        f"Failed to revoke credential {credential.id}: {e}",
                        extra={
                            "credential_id": str(credential.id),
                            "integration_id": str(integration.id),
                            "provider_error": e.provider_error,
                        },
                    )
                except Exception as e:
                    credentials_failed.append(credential.id)
                    if first_error is None:
                        first_error = RevocationError(
                            message=str(e),
                            credential_id=credential.id,
                            provider_error=str(e),
                        )
                    logger.error(
                        f"Unexpected error revoking credential {credential.id}: {e}",
                        extra={"credential_id": str(credential.id)},
                        exc_info=True,
                    )

        # Check if we should proceed with deletion
        if credentials_failed and not force:
            logger.error(
                f"Integration deletion aborted: {len(credentials_failed)} credentials "
                f"failed to revoke",
                extra={
                    "integration_id": str(integration.id),
                    "failed_credentials": [str(c) for c in credentials_failed],
                },
            )
            if first_error:
                raise first_error
            raise RevocationError(
                message=f"Failed to revoke {len(credentials_failed)} credentials",
                credential_id=credentials_failed[0] if credentials_failed else None,
            )

        # Soft delete integration
        integration.status = "revoked"
        integration.deleted_at = datetime.now(UTC)
        await self.session.commit()

        fully_revoked = len(credentials_failed) == 0

        if fully_revoked:
            logger.info(
                f"Deleted integration {integration.id} with {credentials_revoked} "
                "credentials successfully revoked",
                extra={
                    "integration_id": str(integration.id),
                    "credentials_revoked": credentials_revoked,
                },
            )
        else:
            logger.warning(
                f"Force deleted integration {integration.id}: "
                f"{credentials_revoked} revoked, {len(credentials_failed)} failed. "
                "Some tokens may still be valid at provider!",
                extra={
                    "integration_id": str(integration.id),
                    "credentials_revoked": credentials_revoked,
                    "credentials_failed": [str(c) for c in credentials_failed],
                },
            )

        return {
            "integration_id": integration.id,
            "credentials_revoked": credentials_revoked,
            "credentials_failed": credentials_failed,
            "fully_revoked": fully_revoked,
        }

    async def setup_service_account(
        self,
        integration: Integration,
        employee_id: UUID,
        service_account_key: dict[str, Any],
    ) -> IntegrationCredential:
        """
        Set up service account credentials for an employee.

        Args:
            integration: Integration configuration
            employee_id: Employee to configure
            service_account_key: Service account key JSON (from Google/Azure)

        Returns:
            Created credential

        Example:
            >>> import json
            >>> with open("service-account-key.json") as f:
            ...     key = json.load(f)
            >>> credential = await service.setup_service_account(
            ...     integration=integration,
            ...     employee_id=employee.id,
            ...     service_account_key=key,
            ... )
        """
        # Encrypt the service account key
        encrypted, key_id = self.token_manager.encrypt(service_account_key)

        # Extract metadata from key
        metadata = {}
        if "client_email" in service_account_key:
            metadata["service_account_email"] = service_account_key["client_email"]
        if "project_id" in service_account_key:
            metadata["project_id"] = service_account_key["project_id"]

        credential = IntegrationCredential(
            tenant_id=integration.tenant_id,
            integration_id=integration.id,
            employee_id=employee_id,
            credential_type=CredentialType.SERVICE_ACCOUNT_KEY.value,
            encrypted_data=encrypted,
            encryption_key_id=key_id,
            token_metadata=metadata,
            status="active",
            issued_at=datetime.now(UTC),
            expires_at=None,  # Service account keys don't expire
        )

        self.session.add(credential)
        await self.session.commit()
        await self.session.refresh(credential)

        logger.info(
            f"Set up service account for employee {employee_id}",
            extra={
                "credential_id": str(credential.id),
                "employee_id": str(employee_id),
                "service_account_email": metadata.get("service_account_email"),
            },
        )

        return credential

    async def get_credential_for_employee(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        provider: IntegrationProvider,
        auto_refresh: bool = True,
    ) -> tuple[Integration, IntegrationCredential, dict[str, Any]] | None:
        """
        Get credential for employee, refreshing if needed.

        This is the main method for capabilities to get credentials.
        Automatically refreshes tokens if they're expiring soon.

        Args:
            tenant_id: Tenant ID
            employee_id: Employee ID
            provider: Integration provider
            auto_refresh: Whether to auto-refresh expiring tokens

        Returns:
            Tuple of (integration, credential, decrypted_data) or None

        Example:
            >>> result = await service.get_credential_for_employee(
            ...     tenant_id=tenant.id,
            ...     employee_id=employee.id,
            ...     provider=IntegrationProvider.GOOGLE_WORKSPACE,
            ... )
            >>> if result:
            ...     integration, credential, data = result
            ...     access_token = data["access_token"]
        """
        # Query for integration and credential
        result = await self.session.execute(
            select(Integration, IntegrationCredential).where(
                Integration.tenant_id == tenant_id,
                Integration.provider == provider.value,
                Integration.status == "active",
                Integration.deleted_at.is_(None),
                IntegrationCredential.integration_id == Integration.id,
                IntegrationCredential.employee_id == employee_id,
                IntegrationCredential.status == "active",
                IntegrationCredential.deleted_at.is_(None),
            )
        )
        row = result.first()

        if not row:
            return None

        integration, credential = row

        # Get provider for potential refresh
        oauth_provider = get_provider(integration.provider)

        # Decrypt and potentially refresh
        if auto_refresh and credential.credential_type == CredentialType.OAUTH_TOKENS.value:
            data = await self.token_manager.refresh_if_needed(
                credential=credential,
                integration=integration,
                session=self.session,
                provider=oauth_provider,
            )
        else:
            data = self.token_manager.decrypt(
                credential.encrypted_data,
                credential.encryption_key_id,
            )

        # Update last_used_at
        credential.last_used_at = datetime.now(UTC)
        await self.session.commit()

        return integration, credential, data

    async def get_credential_by_id(
        self,
        credential_id: UUID,
    ) -> tuple[Integration, IntegrationCredential, dict[str, Any]] | None:
        """
        Get credential by ID.

        Args:
            credential_id: Credential ID

        Returns:
            Tuple of (integration, credential, decrypted_data) or None
        """
        credential = await self.session.get(IntegrationCredential, credential_id)
        if not credential or credential.deleted_at:
            return None

        integration = await self.session.get(Integration, credential.integration_id)
        if not integration or integration.deleted_at:
            return None

        data = self.token_manager.decrypt(
            credential.encrypted_data,
            credential.encryption_key_id,
        )

        return integration, credential, data

    async def revoke_credential(
        self,
        credential: IntegrationCredential,
        integration: Integration,
        force: bool = False,
    ) -> bool:
        """
        Revoke a credential.

        Attempts to revoke the token with the provider. Only marks the credential
        as revoked if provider revocation succeeds. If it fails, marks as
        'revocation_failed' to indicate the token may still be valid at the provider.

        Args:
            credential: Credential to revoke
            integration: Integration configuration
            force: If True, mark as revoked even if provider revocation fails.
                   Use only for cleanup when token is known to be invalid.

        Returns:
            True if fully revoked (provider + local), False if provider revocation
            failed and credential is marked as revocation_failed.

        Raises:
            RevocationError: If revocation fails and force=False

        Note:
            Credentials marked 'revocation_failed' should be investigated:
            - The token may still be valid at the provider
            - Manual intervention may be required
            - Consider retrying revocation later
        """
        # Get provider
        provider = get_provider(integration.provider)
        provider_revocation_succeeded = True
        provider_error: str | None = None

        # Decrypt to get tokens
        try:
            data = self.token_manager.decrypt(
                credential.encrypted_data,
                credential.encryption_key_id,
            )

            # Revoke with provider (OAuth tokens only)
            if credential.credential_type == CredentialType.OAUTH_TOKENS.value:
                access_token = data.get("access_token")
                if access_token:
                    try:
                        await provider.revoke_token(access_token)
                        logger.info(
                            f"Successfully revoked token with provider for credential {credential.id}",
                            extra={
                                "credential_id": str(credential.id),
                                "provider": integration.provider,
                            },
                        )
                    except Exception as e:
                        provider_revocation_succeeded = False
                        provider_error = str(e)
                        logger.error(
                            f"Failed to revoke token with provider: {e}",
                            extra={
                                "credential_id": str(credential.id),
                                "provider": integration.provider,
                                "error": str(e),
                            },
                            exc_info=True,
                        )

        except Exception as e:
            provider_revocation_succeeded = False
            provider_error = f"Decryption failed: {e}"
            logger.error(
                f"Failed to decrypt credential for revocation: {e}",
                extra={
                    "credential_id": str(credential.id),
                    "error": str(e),
                },
                exc_info=True,
            )

        # Determine final status based on provider revocation result
        if provider_revocation_succeeded or force:
            credential.status = "revoked"
            credential.deleted_at = datetime.now(UTC)
            await self.session.commit()

            logger.info(
                f"Revoked credential {credential.id}",
                extra={
                    "credential_id": str(credential.id),
                    "employee_id": str(credential.employee_id),
                    "forced": force and not provider_revocation_succeeded,
                },
            )
            return True
        # Mark as revocation_failed - token may still be valid at provider
        credential.status = "revocation_failed"
        await self.session.commit()

        logger.warning(
            f"Credential {credential.id} marked as revocation_failed - "
            "token may still be valid at provider",
            extra={
                "credential_id": str(credential.id),
                "employee_id": str(credential.employee_id),
                "provider_error": provider_error,
            },
        )

        raise RevocationError(
            message=f"Failed to revoke credential with provider: {provider_error}",
            credential_id=credential.id,
            provider_error=provider_error,
        )

    async def list_credentials_for_employee(
        self,
        employee_id: UUID,
    ) -> list[tuple[Integration, IntegrationCredential]]:
        """
        List all credentials for an employee.

        Args:
            employee_id: Employee ID

        Returns:
            List of (integration, credential) tuples
        """
        result = await self.session.execute(
            select(Integration, IntegrationCredential).where(
                IntegrationCredential.employee_id == employee_id,
                IntegrationCredential.deleted_at.is_(None),
                Integration.id == IntegrationCredential.integration_id,
                Integration.deleted_at.is_(None),
            )
        )
        return list(result.all())

    async def has_credential(
        self,
        employee_id: UUID,
        provider: IntegrationProvider,
    ) -> bool:
        """
        Check if employee has active credential for provider.

        Args:
            employee_id: Employee ID
            provider: Integration provider

        Returns:
            True if active credential exists
        """
        result = await self.session.execute(
            select(IntegrationCredential.id).where(
                IntegrationCredential.employee_id == employee_id,
                IntegrationCredential.status == "active",
                IntegrationCredential.deleted_at.is_(None),
                Integration.id == IntegrationCredential.integration_id,
                Integration.provider == provider.value,
                Integration.status == "active",
                Integration.deleted_at.is_(None),
            )
        )
        return result.first() is not None
