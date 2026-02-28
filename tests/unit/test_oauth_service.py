"""
Unit tests for OAuthService.

Tests cover:
- Authorization URL generation with PKCE
- OAuth state management
- Callback handling and token exchange
- Expired state cleanup
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from empla.models.integration import (
    Integration,
    IntegrationAuthType,
    IntegrationCredential,
    IntegrationOAuthState,
    IntegrationProvider,
)
from empla.services.integrations.oauth_service import (
    InvalidStateError,
    OAuthService,
    TokenExchangeError,
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
    session.delete = AsyncMock()
    return session


@pytest.fixture
def mock_token_manager():
    """Create a mock token manager."""
    manager = MagicMock()
    manager.encrypt = MagicMock(return_value=(b"encrypted_data", "key_v1"))
    return manager


@pytest.fixture
def oauth_service(mock_session, mock_token_manager):
    """Create OAuthService with mocked dependencies."""
    return OAuthService(mock_session, mock_token_manager)


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
            "redirect_uri": "https://app.example.com/oauth/callback",
            "scopes": ["email", "calendar"],
        },
        use_platform_credentials=False,
        status="active",
        enabled_by=uuid4(),
        enabled_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_oauth_state(sample_integration):
    """Create a sample OAuth state for testing."""
    return IntegrationOAuthState(
        id=uuid4(),
        tenant_id=sample_integration.tenant_id,
        state="test_state_token_abc123",
        integration_id=sample_integration.id,
        employee_id=uuid4(),
        initiated_by=uuid4(),
        redirect_uri="/dashboard/integrations",
        code_verifier="test_code_verifier_xyz",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )


# =============================================================================
# Test: generate_authorization_url
# =============================================================================


class TestGenerateAuthorizationUrl:
    """Tests for OAuthService.generate_authorization_url()."""

    @pytest.mark.asyncio
    async def test_generates_url_with_state(self, oauth_service, mock_session, sample_integration):
        """Test that authorization URL includes state parameter."""
        with patch("empla.services.integrations.oauth_service.get_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.get_default_scopes.return_value = ["email"]
            mock_provider.get_authorization_url.return_value = (
                "https://accounts.google.com/o/oauth2/v2/auth?state=abc123"
            )
            mock_get_provider.return_value = mock_provider

            url, state = await oauth_service.generate_authorization_url(
                integration=sample_integration,
                employee_id=uuid4(),
                user_id=uuid4(),
            )

        assert url is not None
        assert state is not None
        assert len(state) > 20  # State should be reasonably long

    @pytest.mark.asyncio
    async def test_stores_state_in_database(self, oauth_service, mock_session, sample_integration):
        """Test that OAuth state is stored in database."""
        with patch("empla.services.integrations.oauth_service.get_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.get_default_scopes.return_value = ["email"]
            mock_provider.get_authorization_url.return_value = "https://example.com"
            mock_get_provider.return_value = mock_provider

            await oauth_service.generate_authorization_url(
                integration=sample_integration,
                employee_id=uuid4(),
                user_id=uuid4(),
            )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

        # Verify the state object was created correctly
        added_state = mock_session.add.call_args[0][0]
        assert isinstance(added_state, IntegrationOAuthState)
        assert added_state.integration_id == sample_integration.id
        assert added_state.expires_at > datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_includes_pkce_by_default(self, oauth_service, mock_session, sample_integration):
        """Test that PKCE is used by default."""
        with patch("empla.services.integrations.oauth_service.get_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.get_default_scopes.return_value = ["email"]
            mock_provider.get_authorization_url.return_value = "https://example.com"
            mock_get_provider.return_value = mock_provider

            await oauth_service.generate_authorization_url(
                integration=sample_integration,
                employee_id=uuid4(),
                user_id=uuid4(),
                use_pkce=True,
            )

        # Verify code_challenge was passed to provider
        call_kwargs = mock_provider.get_authorization_url.call_args[1]
        assert call_kwargs.get("code_challenge") is not None

        # Verify code_verifier was stored
        added_state = mock_session.add.call_args[0][0]
        assert added_state.code_verifier is not None

    @pytest.mark.asyncio
    async def test_skips_pkce_when_disabled(self, oauth_service, mock_session, sample_integration):
        """Test that PKCE can be disabled."""
        with patch("empla.services.integrations.oauth_service.get_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.get_default_scopes.return_value = ["email"]
            mock_provider.get_authorization_url.return_value = "https://example.com"
            mock_get_provider.return_value = mock_provider

            await oauth_service.generate_authorization_url(
                integration=sample_integration,
                employee_id=uuid4(),
                user_id=uuid4(),
                use_pkce=False,
            )

        # Verify code_challenge was NOT passed to provider
        call_kwargs = mock_provider.get_authorization_url.call_args[1]
        assert call_kwargs.get("code_challenge") is None

        # Verify code_verifier was NOT stored
        added_state = mock_session.add.call_args[0][0]
        assert added_state.code_verifier is None

    @pytest.mark.asyncio
    async def test_uses_custom_redirect_after(
        self, oauth_service, mock_session, sample_integration
    ):
        """Test that custom redirect_after is stored."""
        with patch("empla.services.integrations.oauth_service.get_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.get_default_scopes.return_value = ["email"]
            mock_provider.get_authorization_url.return_value = "https://example.com"
            mock_get_provider.return_value = mock_provider

            await oauth_service.generate_authorization_url(
                integration=sample_integration,
                employee_id=uuid4(),
                user_id=uuid4(),
                redirect_after="/custom/path",
            )

        added_state = mock_session.add.call_args[0][0]
        assert added_state.redirect_uri == "/custom/path"

    @pytest.mark.asyncio
    async def test_uses_scopes_from_integration(
        self, oauth_service, mock_session, sample_integration
    ):
        """Test that scopes from integration config are used."""
        with patch("empla.services.integrations.oauth_service.get_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.get_authorization_url.return_value = "https://example.com"
            mock_get_provider.return_value = mock_provider

            await oauth_service.generate_authorization_url(
                integration=sample_integration,
                employee_id=uuid4(),
                user_id=uuid4(),
            )

        call_kwargs = mock_provider.get_authorization_url.call_args[1]
        assert call_kwargs["scopes"] == ["email", "calendar"]


# =============================================================================
# Test: handle_callback
# =============================================================================


class TestHandleCallback:
    """Tests for OAuthService.handle_callback()."""

    @pytest.fixture(autouse=True)
    def _set_client_secret_env(self, monkeypatch):
        """Set the OAuth client secret env var for all callback tests."""
        monkeypatch.setenv("OAUTH_GOOGLE_WORKSPACE_CLIENT_SECRET", "test_secret")

    @pytest.mark.asyncio
    async def test_validates_state_successfully(
        self, oauth_service, mock_session, sample_integration, sample_oauth_state
    ):
        """Test successful state validation."""
        # Setup mocks
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_oauth_state
        mock_session.execute.return_value = mock_result
        mock_session.get.return_value = sample_integration

        with patch("empla.services.integrations.oauth_service.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.exchange_code = AsyncMock(
                return_value={
                    "access_token": "test_access_token",
                    "refresh_token": "test_refresh_token",
                    "expires_in": 3600,
                }
            )
            mock_provider.get_user_info = AsyncMock(
                return_value={"email": "test@example.com", "name": "Test User"}
            )
            mock_get_provider.return_value = mock_provider

            credential, redirect = await oauth_service.handle_callback(
                state=sample_oauth_state.state,
                code="authorization_code_123",
            )

        assert credential is not None
        assert redirect == sample_oauth_state.redirect_uri

    @pytest.mark.asyncio
    async def test_raises_error_for_invalid_state(self, oauth_service, mock_session):
        """Test that invalid state raises InvalidStateError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(InvalidStateError) as exc_info:
            await oauth_service.handle_callback(
                state="invalid_state",
                code="authorization_code",
            )

        assert "Invalid or expired" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_raises_error_for_expired_state(
        self, oauth_service, mock_session, sample_oauth_state
    ):
        """Test that expired state raises InvalidStateError."""
        # State is expired (query will return None due to expiry check)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(InvalidStateError):
            await oauth_service.handle_callback(
                state=sample_oauth_state.state,
                code="authorization_code",
            )

    @pytest.mark.asyncio
    async def test_raises_error_when_integration_not_found(
        self, oauth_service, mock_session, sample_oauth_state
    ):
        """Test error when integration is not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_oauth_state
        mock_session.execute.return_value = mock_result
        mock_session.get.return_value = None  # Integration not found

        with pytest.raises(InvalidStateError) as exc_info:
            await oauth_service.handle_callback(
                state=sample_oauth_state.state,
                code="authorization_code",
            )

        assert "Integration not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_raises_error_on_token_exchange_failure(
        self, oauth_service, mock_session, sample_integration, sample_oauth_state
    ):
        """Test that token exchange failure raises TokenExchangeError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_oauth_state
        mock_session.execute.return_value = mock_result
        mock_session.get.return_value = sample_integration

        with patch("empla.services.integrations.oauth_service.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.exchange_code = AsyncMock(side_effect=Exception("Provider error"))
            mock_get_provider.return_value = mock_provider

            with pytest.raises(TokenExchangeError) as exc_info:
                await oauth_service.handle_callback(
                    state=sample_oauth_state.state,
                    code="authorization_code",
                )

        assert "Provider error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_encrypts_and_stores_tokens(
        self,
        oauth_service,
        mock_session,
        mock_token_manager,
        sample_integration,
        sample_oauth_state,
    ):
        """Test that tokens are encrypted and stored."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            sample_oauth_state,
            None,
        ]  # First for state, second for existing credential
        mock_session.execute.return_value = mock_result
        mock_session.get.return_value = sample_integration

        tokens = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
        }

        with patch("empla.services.integrations.oauth_service.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.exchange_code = AsyncMock(return_value=tokens)
            mock_provider.get_user_info = AsyncMock(return_value={})
            mock_get_provider.return_value = mock_provider

            await oauth_service.handle_callback(
                state=sample_oauth_state.state,
                code="authorization_code",
            )

        mock_token_manager.encrypt.assert_called_once_with(tokens)

    @pytest.mark.asyncio
    async def test_updates_existing_credential(
        self,
        oauth_service,
        mock_session,
        mock_token_manager,
        sample_integration,
        sample_oauth_state,
    ):
        """Test that existing credential is updated instead of created."""
        # Create existing credential
        existing_credential = IntegrationCredential(
            id=uuid4(),
            tenant_id=sample_integration.tenant_id,
            integration_id=sample_integration.id,
            employee_id=sample_oauth_state.employee_id,
            credential_type="oauth_tokens",
            encrypted_data=b"old_data",
            encryption_key_id="key_v0",
            status="active",
            issued_at=datetime.now(UTC) - timedelta(days=1),
        )

        # First call returns oauth_state, second call returns existing credential
        mock_state_result = MagicMock()
        mock_state_result.scalar_one_or_none.return_value = sample_oauth_state

        mock_cred_result = MagicMock()
        mock_cred_result.scalar_one_or_none.return_value = existing_credential

        mock_session.execute.side_effect = [mock_state_result, mock_cred_result]
        mock_session.get.return_value = sample_integration

        with patch("empla.services.integrations.oauth_service.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.exchange_code = AsyncMock(
                return_value={
                    "access_token": "new_access_token",
                    "expires_in": 3600,
                }
            )
            mock_provider.get_user_info = AsyncMock(return_value={})
            mock_get_provider.return_value = mock_provider

            credential, _ = await oauth_service.handle_callback(
                state=sample_oauth_state.state,
                code="authorization_code",
            )

        # Should update existing credential, not add new
        assert credential == existing_credential
        assert existing_credential.encrypted_data == b"encrypted_data"
        assert existing_credential.encryption_key_id == "key_v1"
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_deletes_used_state(
        self, oauth_service, mock_session, sample_integration, sample_oauth_state
    ):
        """Test that OAuth state is deleted after use."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [sample_oauth_state, None]
        mock_session.execute.return_value = mock_result
        mock_session.get.return_value = sample_integration

        with patch("empla.services.integrations.oauth_service.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.exchange_code = AsyncMock(
                return_value={"access_token": "test", "expires_in": 3600}
            )
            mock_provider.get_user_info = AsyncMock(return_value={})
            mock_get_provider.return_value = mock_provider

            await oauth_service.handle_callback(
                state=sample_oauth_state.state,
                code="authorization_code",
            )

        mock_session.delete.assert_called_once_with(sample_oauth_state)

    @pytest.mark.asyncio
    async def test_stores_user_metadata(
        self, oauth_service, mock_session, sample_integration, sample_oauth_state
    ):
        """Test that user metadata is stored in credential."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [sample_oauth_state, None]
        mock_session.execute.return_value = mock_result
        mock_session.get.return_value = sample_integration

        user_info = {
            "email": "user@example.com",
            "name": "Test User",
        }

        with patch("empla.services.integrations.oauth_service.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.exchange_code = AsyncMock(
                return_value={
                    "access_token": "test",
                    "expires_in": 3600,
                    "scope": "email calendar",
                }
            )
            mock_provider.get_user_info = AsyncMock(return_value=user_info)
            mock_get_provider.return_value = mock_provider

            await oauth_service.handle_callback(
                state=sample_oauth_state.state,
                code="authorization_code",
            )

        # Verify credential was added with metadata
        added_credential = mock_session.add.call_args[0][0]
        assert added_credential.token_metadata["email"] == "user@example.com"
        assert added_credential.token_metadata["name"] == "Test User"
        assert added_credential.token_metadata["scopes"] == ["email", "calendar"]

    @pytest.mark.asyncio
    async def test_handles_user_info_failure_gracefully(
        self, oauth_service, mock_session, sample_integration, sample_oauth_state
    ):
        """Test that user info failure doesn't break the flow."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [sample_oauth_state, None]
        mock_session.execute.return_value = mock_result
        mock_session.get.return_value = sample_integration

        with patch("empla.services.integrations.oauth_service.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.exchange_code = AsyncMock(
                return_value={"access_token": "test", "expires_in": 3600}
            )
            mock_provider.get_user_info = AsyncMock(side_effect=Exception("User info failed"))
            mock_get_provider.return_value = mock_provider

            # Should not raise
            credential, _ = await oauth_service.handle_callback(
                state=sample_oauth_state.state,
                code="authorization_code",
            )

        assert credential is not None


# =============================================================================
# Test: cleanup_expired_states
# =============================================================================


class TestCleanupExpiredStates:
    """Tests for OAuthService.cleanup_expired_states()."""

    @pytest.mark.asyncio
    async def test_deletes_expired_states(self, oauth_service, mock_session):
        """Test that expired states are deleted."""
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        count = await oauth_service.cleanup_expired_states()

        assert count == 5
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_expired(self, oauth_service, mock_session):
        """Test that zero is returned when no expired states."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        count = await oauth_service.cleanup_expired_states()

        assert count == 0
