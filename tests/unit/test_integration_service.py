"""
Unit tests for IntegrationService.

Tests cover:
- Integration CRUD operations
- Credential management
- Token revocation flow
- Service account setup
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from empla.models.integration import (
    CredentialType,
    Integration,
    IntegrationAuthType,
    IntegrationCredential,
    IntegrationProvider,
)
from empla.services.integrations.integration_service import (
    IntegrationService,
    RevocationError,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_session():
    """Create a mock async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_token_manager():
    """Create a mock token manager."""
    manager = MagicMock()
    manager.encrypt = MagicMock(return_value=(b"encrypted_data", "key_v1"))
    manager.decrypt = MagicMock(
        return_value={
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }
    )
    manager.refresh_if_needed = AsyncMock(
        return_value={
            "access_token": "refreshed_access_token",
            "refresh_token": "test_refresh_token",
        }
    )
    return manager


@pytest.fixture
def integration_service(mock_session, mock_token_manager):
    """Create IntegrationService with mocked dependencies."""
    return IntegrationService(mock_session, mock_token_manager)


@pytest.fixture
def sample_integration():
    """Create a sample integration for testing."""
    return Integration(
        id=uuid4(),
        tenant_id=uuid4(),
        provider=IntegrationProvider.GOOGLE_WORKSPACE.value,
        auth_type=IntegrationAuthType.USER_OAUTH.value,
        display_name="Google Workspace",
        oauth_config={
            "client_id": "test_client_id",
            "redirect_uri": "https://example.com/callback",
            "scopes": ["email", "calendar"],
        },
        status="active",
        enabled_by=uuid4(),
        enabled_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_credential(sample_integration):
    """Create a sample credential for testing."""
    return IntegrationCredential(
        id=uuid4(),
        tenant_id=sample_integration.tenant_id,
        integration_id=sample_integration.id,
        employee_id=uuid4(),
        credential_type=CredentialType.OAUTH_TOKENS.value,
        encrypted_data=b"encrypted_data",
        encryption_key_id="key_v1",
        token_metadata={"email": "test@example.com"},
        status="active",
        issued_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


# =============================================================================
# Test: create_integration
# =============================================================================


class TestCreateIntegration:
    """Tests for IntegrationService.create_integration()."""

    @pytest.mark.asyncio
    async def test_creates_integration_successfully(self, integration_service, mock_session):
        """Test that create_integration stores correct data."""
        tenant_id = uuid4()
        enabled_by = uuid4()

        result = await integration_service.create_integration(
            tenant_id=tenant_id,
            provider=IntegrationProvider.GOOGLE_WORKSPACE,
            auth_type=IntegrationAuthType.USER_OAUTH,
            display_name="Google Workspace",
            oauth_config={"client_id": "test", "redirect_uri": "https://example.com"},
            enabled_by=enabled_by,
        )

        # Verify session operations
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

        # Verify the integration was created with correct values
        added_integration = mock_session.add.call_args[0][0]
        assert added_integration.tenant_id == tenant_id
        assert added_integration.provider == IntegrationProvider.GOOGLE_WORKSPACE.value
        assert added_integration.auth_type == IntegrationAuthType.USER_OAUTH.value
        assert added_integration.display_name == "Google Workspace"
        assert added_integration.status == "active"
        assert added_integration.enabled_by == enabled_by

    @pytest.mark.asyncio
    async def test_stores_oauth_config(self, integration_service, mock_session):
        """Test that OAuth config is stored correctly."""
        oauth_config = {
            "client_id": "client_123",
            "redirect_uri": "https://app.example.com/callback",
            "scopes": ["email", "calendar", "drive"],
        }

        await integration_service.create_integration(
            tenant_id=uuid4(),
            provider=IntegrationProvider.MICROSOFT_GRAPH,
            auth_type=IntegrationAuthType.USER_OAUTH,
            display_name="Microsoft 365",
            oauth_config=oauth_config,
            enabled_by=uuid4(),
        )

        added_integration = mock_session.add.call_args[0][0]
        assert added_integration.oauth_config == oauth_config


# =============================================================================
# Test: get_integration
# =============================================================================


class TestGetIntegration:
    """Tests for IntegrationService.get_integration()."""

    @pytest.mark.asyncio
    async def test_returns_active_integration(
        self, integration_service, mock_session, sample_integration
    ):
        """Test that get_integration returns active integrations."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_integration
        mock_session.execute.return_value = mock_result

        result = await integration_service.get_integration(
            tenant_id=sample_integration.tenant_id,
            provider=IntegrationProvider.GOOGLE_WORKSPACE,
        )

        assert result == sample_integration

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, integration_service, mock_session):
        """Test that get_integration returns None when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await integration_service.get_integration(
            tenant_id=uuid4(),
            provider=IntegrationProvider.GOOGLE_WORKSPACE,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_filters_by_tenant_and_provider(self, integration_service, mock_session):
        """Test that query filters by tenant_id and provider."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        tenant_id = uuid4()
        await integration_service.get_integration(
            tenant_id=tenant_id,
            provider=IntegrationProvider.MICROSOFT_GRAPH,
        )

        # Verify execute was called (query was built)
        mock_session.execute.assert_called_once()


# =============================================================================
# Test: list_integrations
# =============================================================================


class TestListIntegrations:
    """Tests for IntegrationService.list_integrations()."""

    @pytest.mark.asyncio
    async def test_returns_all_tenant_integrations(
        self, integration_service, mock_session, sample_integration
    ):
        """Test that list_integrations returns all integrations for tenant."""
        integrations = [sample_integration, sample_integration]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = integrations
        mock_session.execute.return_value = mock_result

        result = await integration_service.list_integrations(tenant_id=sample_integration.tenant_id)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none(self, integration_service, mock_session):
        """Test that list_integrations returns empty list when no integrations."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await integration_service.list_integrations(tenant_id=uuid4())

        assert result == []


# =============================================================================
# Test: delete_integration
# =============================================================================


class TestDeleteIntegration:
    """Tests for IntegrationService.delete_integration()."""

    @pytest.mark.asyncio
    async def test_soft_deletes_integration(
        self, integration_service, mock_session, sample_integration
    ):
        """Test that delete_integration soft deletes the integration."""
        # No credentials to revoke
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await integration_service.delete_integration(
            sample_integration, revoke_credentials=True
        )

        assert sample_integration.status == "revoked"
        assert sample_integration.deleted_at is not None
        assert result["fully_revoked"] is True
        assert result["credentials_revoked"] == 0

    @pytest.mark.asyncio
    async def test_revokes_all_credentials_on_delete(
        self, integration_service, mock_session, sample_integration, sample_credential
    ):
        """Test that delete_integration revokes all credentials."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_credential]
        mock_session.execute.return_value = mock_result

        # Mock successful provider revocation
        with patch(
            "empla.services.integrations.integration_service.get_provider"
        ) as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.revoke_token = AsyncMock()
            mock_get_provider.return_value = mock_provider

            result = await integration_service.delete_integration(
                sample_integration, revoke_credentials=True
            )

        assert result["credentials_revoked"] == 1
        assert result["fully_revoked"] is True
        mock_provider.revoke_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_error_on_revocation_failure(
        self, integration_service, mock_session, sample_integration, sample_credential
    ):
        """Test that delete_integration raises error when revocation fails."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_credential]
        mock_session.execute.return_value = mock_result

        # Mock failed provider revocation
        with patch(
            "empla.services.integrations.integration_service.get_provider"
        ) as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.revoke_token = AsyncMock(side_effect=Exception("Provider error"))
            mock_get_provider.return_value = mock_provider

            with pytest.raises(RevocationError) as exc_info:
                await integration_service.delete_integration(
                    sample_integration, revoke_credentials=True
                )

            assert "Provider error" in str(exc_info.value.provider_error)

    @pytest.mark.asyncio
    async def test_force_delete_continues_on_failure(
        self, integration_service, mock_session, sample_integration, sample_credential
    ):
        """Test that force=True allows deletion even when revocation fails."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_credential]
        mock_session.execute.return_value = mock_result

        # Mock failed provider revocation
        with patch(
            "empla.services.integrations.integration_service.get_provider"
        ) as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.revoke_token = AsyncMock(side_effect=Exception("Provider error"))
            mock_get_provider.return_value = mock_provider

            result = await integration_service.delete_integration(
                sample_integration, revoke_credentials=True, force=True
            )

        assert result["fully_revoked"] is False
        assert len(result["credentials_failed"]) == 1
        assert sample_integration.status == "revoked"

    @pytest.mark.asyncio
    async def test_skips_revocation_when_disabled(
        self, integration_service, mock_session, sample_integration
    ):
        """Test that revoke_credentials=False skips revocation."""
        result = await integration_service.delete_integration(
            sample_integration, revoke_credentials=False
        )

        assert sample_integration.status == "revoked"
        assert result["credentials_revoked"] == 0
        # Execute should not be called to fetch credentials
        mock_session.execute.assert_not_called()


# =============================================================================
# Test: revoke_credential
# =============================================================================


class TestRevokeCredential:
    """Tests for IntegrationService.revoke_credential()."""

    @pytest.mark.asyncio
    async def test_revokes_credential_successfully(
        self,
        integration_service,
        mock_session,
        sample_integration,
        sample_credential,
        mock_token_manager,
    ):
        """Test successful credential revocation."""
        with patch(
            "empla.services.integrations.integration_service.get_provider"
        ) as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.revoke_token = AsyncMock()
            mock_get_provider.return_value = mock_provider

            result = await integration_service.revoke_credential(
                sample_credential, sample_integration
            )

        assert result is True
        assert sample_credential.status == "revoked"
        assert sample_credential.deleted_at is not None
        mock_provider.revoke_token.assert_called_once_with("test_access_token")

    @pytest.mark.asyncio
    async def test_marks_revocation_failed_on_provider_error(
        self,
        integration_service,
        mock_session,
        sample_integration,
        sample_credential,
        mock_token_manager,
    ):
        """Test credential marked as revocation_failed when provider fails."""
        with patch(
            "empla.services.integrations.integration_service.get_provider"
        ) as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.revoke_token = AsyncMock(side_effect=Exception("Provider unavailable"))
            mock_get_provider.return_value = mock_provider

            with pytest.raises(RevocationError) as exc_info:
                await integration_service.revoke_credential(sample_credential, sample_integration)

        assert sample_credential.status == "revocation_failed"
        assert "Provider unavailable" in exc_info.value.provider_error

    @pytest.mark.asyncio
    async def test_marks_revocation_failed_on_decryption_error(
        self,
        integration_service,
        mock_session,
        sample_integration,
        sample_credential,
        mock_token_manager,
    ):
        """Test credential marked as revocation_failed when decryption fails."""
        mock_token_manager.decrypt.side_effect = Exception("Decryption failed")

        with patch(
            "empla.services.integrations.integration_service.get_provider"
        ) as mock_get_provider:
            mock_provider = AsyncMock()
            mock_get_provider.return_value = mock_provider

            with pytest.raises(RevocationError) as exc_info:
                await integration_service.revoke_credential(sample_credential, sample_integration)

        assert sample_credential.status == "revocation_failed"
        assert "Decryption failed" in exc_info.value.provider_error

    @pytest.mark.asyncio
    async def test_force_revokes_even_on_error(
        self,
        integration_service,
        mock_session,
        sample_integration,
        sample_credential,
        mock_token_manager,
    ):
        """Test force=True marks credential as revoked even on error."""
        with patch(
            "empla.services.integrations.integration_service.get_provider"
        ) as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.revoke_token = AsyncMock(side_effect=Exception("Error"))
            mock_get_provider.return_value = mock_provider

            result = await integration_service.revoke_credential(
                sample_credential, sample_integration, force=True
            )

        assert result is True
        assert sample_credential.status == "revoked"

    @pytest.mark.asyncio
    async def test_skips_provider_revocation_for_service_accounts(
        self,
        integration_service,
        mock_session,
        sample_integration,
        sample_credential,
        mock_token_manager,
    ):
        """Test that service account keys don't call provider revocation."""
        sample_credential.credential_type = CredentialType.SERVICE_ACCOUNT_KEY.value

        with patch(
            "empla.services.integrations.integration_service.get_provider"
        ) as mock_get_provider:
            mock_provider = AsyncMock()
            mock_get_provider.return_value = mock_provider

            result = await integration_service.revoke_credential(
                sample_credential, sample_integration
            )

        assert result is True
        assert sample_credential.status == "revoked"
        mock_provider.revoke_token.assert_not_called()


# =============================================================================
# Test: setup_service_account
# =============================================================================


class TestSetupServiceAccount:
    """Tests for IntegrationService.setup_service_account()."""

    @pytest.mark.asyncio
    async def test_creates_service_account_credential(
        self, integration_service, mock_session, sample_integration, mock_token_manager
    ):
        """Test that setup_service_account creates encrypted credential."""
        service_account_key = {
            "type": "service_account",
            "project_id": "test-project",
            "client_email": "test@test-project.iam.gserviceaccount.com",
            "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
        }

        result = await integration_service.setup_service_account(
            integration=sample_integration,
            employee_id=uuid4(),
            service_account_key=service_account_key,
        )

        mock_session.add.assert_called_once()
        mock_token_manager.encrypt.assert_called_once_with(service_account_key)

        added_credential = mock_session.add.call_args[0][0]
        assert added_credential.credential_type == CredentialType.SERVICE_ACCOUNT_KEY.value
        assert added_credential.expires_at is None  # Service accounts don't expire
        assert (
            added_credential.token_metadata["service_account_email"]
            == "test@test-project.iam.gserviceaccount.com"
        )
        assert added_credential.token_metadata["project_id"] == "test-project"

    @pytest.mark.asyncio
    async def test_extracts_metadata_from_key(
        self, integration_service, mock_session, sample_integration, mock_token_manager
    ):
        """Test that metadata is extracted from service account key."""
        service_account_key = {
            "client_email": "sa@project.iam.gserviceaccount.com",
            "project_id": "my-project-123",
        }

        await integration_service.setup_service_account(
            integration=sample_integration,
            employee_id=uuid4(),
            service_account_key=service_account_key,
        )

        added_credential = mock_session.add.call_args[0][0]
        assert (
            added_credential.token_metadata["service_account_email"]
            == "sa@project.iam.gserviceaccount.com"
        )
        assert added_credential.token_metadata["project_id"] == "my-project-123"


# =============================================================================
# Test: get_credential_for_employee
# =============================================================================


class TestGetCredentialForEmployee:
    """Tests for IntegrationService.get_credential_for_employee()."""

    @pytest.mark.asyncio
    async def test_returns_credential_with_decrypted_data(
        self,
        integration_service,
        mock_session,
        sample_integration,
        sample_credential,
        mock_token_manager,
    ):
        """Test that get_credential_for_employee returns decrypted data."""
        mock_result = MagicMock()
        mock_result.first.return_value = (sample_integration, sample_credential)
        mock_session.execute.return_value = mock_result

        with patch(
            "empla.services.integrations.integration_service.get_provider"
        ) as mock_get_provider:
            mock_provider = MagicMock()
            mock_get_provider.return_value = mock_provider

            result = await integration_service.get_credential_for_employee(
                tenant_id=sample_integration.tenant_id,
                employee_id=sample_credential.employee_id,
                provider=IntegrationProvider.GOOGLE_WORKSPACE,
            )

        assert result is not None
        integration, credential, data = result
        assert integration == sample_integration
        assert credential == sample_credential
        assert "access_token" in data

    @pytest.mark.asyncio
    async def test_returns_none_when_no_credential(self, integration_service, mock_session):
        """Test that get_credential_for_employee returns None when not found."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await integration_service.get_credential_for_employee(
            tenant_id=uuid4(),
            employee_id=uuid4(),
            provider=IntegrationProvider.GOOGLE_WORKSPACE,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_triggers_auto_refresh_for_oauth_tokens(
        self,
        integration_service,
        mock_session,
        sample_integration,
        sample_credential,
        mock_token_manager,
    ):
        """Test that auto_refresh triggers for OAuth tokens."""
        mock_result = MagicMock()
        mock_result.first.return_value = (sample_integration, sample_credential)
        mock_session.execute.return_value = mock_result

        with patch(
            "empla.services.integrations.integration_service.get_provider"
        ) as mock_get_provider:
            mock_provider = MagicMock()
            mock_get_provider.return_value = mock_provider

            await integration_service.get_credential_for_employee(
                tenant_id=sample_integration.tenant_id,
                employee_id=sample_credential.employee_id,
                provider=IntegrationProvider.GOOGLE_WORKSPACE,
                auto_refresh=True,
            )

        mock_token_manager.refresh_if_needed.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_refresh_when_disabled(
        self,
        integration_service,
        mock_session,
        sample_integration,
        sample_credential,
        mock_token_manager,
    ):
        """Test that auto_refresh=False skips refresh."""
        mock_result = MagicMock()
        mock_result.first.return_value = (sample_integration, sample_credential)
        mock_session.execute.return_value = mock_result

        with patch(
            "empla.services.integrations.integration_service.get_provider"
        ) as mock_get_provider:
            mock_provider = MagicMock()
            mock_get_provider.return_value = mock_provider

            await integration_service.get_credential_for_employee(
                tenant_id=sample_integration.tenant_id,
                employee_id=sample_credential.employee_id,
                provider=IntegrationProvider.GOOGLE_WORKSPACE,
                auto_refresh=False,
            )

        mock_token_manager.refresh_if_needed.assert_not_called()
        mock_token_manager.decrypt.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_last_used_at(
        self,
        integration_service,
        mock_session,
        sample_integration,
        sample_credential,
        mock_token_manager,
    ):
        """Test that last_used_at is updated on access."""
        original_last_used = sample_credential.last_used_at
        mock_result = MagicMock()
        mock_result.first.return_value = (sample_integration, sample_credential)
        mock_session.execute.return_value = mock_result

        with patch(
            "empla.services.integrations.integration_service.get_provider"
        ) as mock_get_provider:
            mock_provider = MagicMock()
            mock_get_provider.return_value = mock_provider

            await integration_service.get_credential_for_employee(
                tenant_id=sample_integration.tenant_id,
                employee_id=sample_credential.employee_id,
                provider=IntegrationProvider.GOOGLE_WORKSPACE,
            )

        assert sample_credential.last_used_at != original_last_used
        mock_session.commit.assert_called()


# =============================================================================
# Test: has_credential
# =============================================================================


class TestHasCredential:
    """Tests for IntegrationService.has_credential()."""

    @pytest.mark.asyncio
    async def test_returns_true_when_credential_exists(self, integration_service, mock_session):
        """Test that has_credential returns True when credential exists."""
        mock_result = MagicMock()
        mock_result.first.return_value = (uuid4(),)  # Credential ID
        mock_session.execute.return_value = mock_result

        result = await integration_service.has_credential(
            employee_id=uuid4(),
            provider=IntegrationProvider.GOOGLE_WORKSPACE,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_credential(self, integration_service, mock_session):
        """Test that has_credential returns False when no credential."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await integration_service.has_credential(
            employee_id=uuid4(),
            provider=IntegrationProvider.GOOGLE_WORKSPACE,
        )

        assert result is False
