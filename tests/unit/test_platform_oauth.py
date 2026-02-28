"""
Unit tests for PlatformOAuthApp model, service, and get_effective_oauth_config.

Tests cover:
- PlatformOAuthApp CRUD operations
- Client secret encryption/decryption round-trip
- get_effective_oauth_config — platform vs tenant resolution
- get_effective_client_secret — platform vs env-var resolution
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from empla.models.integration import (
    Integration,
    IntegrationAuthType,
    IntegrationProvider,
    PlatformOAuthApp,
)
from empla.services.integrations.catalog import (
    PROVIDER_CATALOG,
    get_provider_meta,
    list_providers,
)
from empla.services.integrations.platform_service import PlatformOAuthAppService
from empla.services.integrations.utils import (
    ClientSecretNotConfiguredError,
    get_effective_client_secret,
    get_effective_oauth_config,
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
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def mock_token_manager():
    """Create a mock token manager that round-trips data."""
    manager = MagicMock()
    manager.encrypt = MagicMock(return_value=(b"encrypted_secret", "key_v1"))
    manager.decrypt = MagicMock(return_value={"client_secret": "my_super_secret"})
    return manager


@pytest.fixture
def platform_service(mock_session, mock_token_manager):
    return PlatformOAuthAppService(mock_session, mock_token_manager)


@pytest.fixture
def sample_platform_app():
    return PlatformOAuthApp(
        id=uuid4(),
        provider="google_workspace",
        client_id="platform_client_id",
        encrypted_client_secret=b"encrypted_secret",
        encryption_key_id="key_v1",
        redirect_uri="https://api.empla.ai/v1/integrations/callback",
        default_scopes=["email", "calendar"],
        status="active",
    )


@pytest.fixture
def tenant_integration():
    return Integration(
        id=uuid4(),
        tenant_id=uuid4(),
        provider=IntegrationProvider.GOOGLE_WORKSPACE.value,
        auth_type=IntegrationAuthType.USER_OAUTH.value,
        display_name="Google Workspace",
        oauth_config={
            "client_id": "tenant_client_id",
            "redirect_uri": "https://tenant.example.com/callback",
            "scopes": ["email"],
        },
        use_platform_credentials=False,
        status="active",
        enabled_by=uuid4(),
        enabled_at=datetime.now(UTC),
    )


@pytest.fixture
def platform_integration():
    return Integration(
        id=uuid4(),
        tenant_id=uuid4(),
        provider=IntegrationProvider.GOOGLE_WORKSPACE.value,
        auth_type=IntegrationAuthType.USER_OAUTH.value,
        display_name="Google Workspace",
        oauth_config={},
        use_platform_credentials=True,
        status="active",
        enabled_by=uuid4(),
        enabled_at=datetime.now(UTC),
    )


# =============================================================================
# Provider Catalog Tests
# =============================================================================


class TestProviderCatalog:
    def test_catalog_has_google_workspace(self):
        assert "google_workspace" in PROVIDER_CATALOG

    def test_catalog_has_microsoft_graph(self):
        assert "microsoft_graph" in PROVIDER_CATALOG

    def test_get_provider_meta_returns_meta(self):
        meta = get_provider_meta("google_workspace")
        assert meta is not None
        assert meta.display_name == "Google Workspace"
        assert meta.icon == "google"
        assert meta.auth_type == "user_oauth"

    def test_get_provider_meta_returns_none_for_unknown(self):
        assert get_provider_meta("nonexistent") is None

    def test_list_providers(self):
        providers = list_providers()
        assert "google_workspace" in providers
        assert "microsoft_graph" in providers


# =============================================================================
# PlatformOAuthAppService Tests
# =============================================================================


class TestPlatformOAuthAppService:
    @pytest.mark.asyncio
    async def test_create_app(self, platform_service, mock_session, mock_token_manager):
        mock_session.refresh = AsyncMock()

        await platform_service.create_app(
            provider="google_workspace",
            client_id="test_client",
            client_secret="test_secret",
            redirect_uri="https://example.com/callback",
            scopes=["email"],
        )

        mock_token_manager.encrypt.assert_called_once_with({"client_secret": "test_secret"})
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_app_returns_result(
        self, platform_service, mock_session, sample_platform_app
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_platform_app
        mock_session.execute.return_value = mock_result

        result = await platform_service.get_app("google_workspace")
        assert result == sample_platform_app

    @pytest.mark.asyncio
    async def test_get_app_returns_none_when_missing(self, platform_service, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await platform_service.get_app("nonexistent")
        assert result is None

    def test_decrypt_client_secret(self, platform_service, mock_token_manager, sample_platform_app):
        result = platform_service.decrypt_client_secret(sample_platform_app)
        assert result == "my_super_secret"
        mock_token_manager.decrypt.assert_called_once_with(
            sample_platform_app.encrypted_client_secret,
            sample_platform_app.encryption_key_id,
        )

    @pytest.mark.asyncio
    async def test_delete_app(self, platform_service, mock_session, sample_platform_app):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_platform_app
        mock_session.execute.return_value = mock_result

        await platform_service.delete_app("google_workspace")
        mock_session.delete.assert_called_once_with(sample_platform_app)
        mock_session.commit.assert_called_once()


# =============================================================================
# get_effective_oauth_config Tests
# =============================================================================


class TestGetEffectiveOAuthConfig:
    @pytest.mark.asyncio
    async def test_tenant_credentials_returns_own_config(
        self, tenant_integration, mock_session, mock_token_manager
    ):
        config = await get_effective_oauth_config(
            tenant_integration, mock_session, mock_token_manager
        )
        assert config["client_id"] == "tenant_client_id"
        assert config["redirect_uri"] == "https://tenant.example.com/callback"

    @pytest.mark.asyncio
    async def test_platform_credentials_returns_platform_config(
        self, platform_integration, mock_session, mock_token_manager, sample_platform_app
    ):
        # Mock the platform service lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_platform_app
        mock_session.execute.return_value = mock_result

        config = await get_effective_oauth_config(
            platform_integration, mock_session, mock_token_manager
        )
        assert config["client_id"] == "platform_client_id"
        assert config["redirect_uri"] == "https://api.empla.ai/v1/integrations/callback"
        assert config["scopes"] == ["email", "calendar"]

    @pytest.mark.asyncio
    async def test_platform_credentials_raises_when_no_app(
        self, platform_integration, mock_session, mock_token_manager
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ClientSecretNotConfiguredError):
            await get_effective_oauth_config(platform_integration, mock_session, mock_token_manager)


# =============================================================================
# get_effective_client_secret Tests
# =============================================================================


class TestGetEffectiveClientSecret:
    @pytest.mark.asyncio
    async def test_tenant_secret_from_env(
        self, tenant_integration, mock_session, mock_token_manager
    ):
        with patch.dict(
            "os.environ",
            {"OAUTH_GOOGLE_WORKSPACE_CLIENT_SECRET": "env_secret"},
        ):
            secret = await get_effective_client_secret(
                tenant_integration, mock_session, mock_token_manager
            )
            assert secret == "env_secret"

    @pytest.mark.asyncio
    async def test_platform_secret_from_db(
        self, platform_integration, mock_session, mock_token_manager, sample_platform_app
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_platform_app
        mock_session.execute.return_value = mock_result

        secret = await get_effective_client_secret(
            platform_integration, mock_session, mock_token_manager
        )
        assert secret == "my_super_secret"
