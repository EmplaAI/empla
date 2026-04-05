"""Tests for CredentialInjector — OAuth credential resolution and injection."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from empla.services.integrations.credential_injector import CredentialInjector


@pytest.fixture
def employee_id() -> UUID:
    return uuid4()


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


def _make_credential(
    *,
    employee_id: UUID,
    tenant_id: UUID,
    provider: str = "google_workspace",
    status: str = "active",
    expires_at: datetime | None = None,
    encrypted_data: bytes = b"encrypted",
    encryption_key_id: str = "v1",
) -> MagicMock:
    """Create a mock IntegrationCredential."""
    cred = MagicMock()
    cred.id = uuid4()
    cred.employee_id = employee_id
    cred.tenant_id = tenant_id
    cred.status = status
    cred.expires_at = expires_at or (datetime.now(UTC) + timedelta(hours=1))
    cred.encrypted_data = encrypted_data
    cred.encryption_key_id = encryption_key_id
    cred.last_refreshed_at = None

    integration = MagicMock()
    integration.id = uuid4()
    integration.provider = provider
    integration.status = "active"
    cred.integration = integration

    return cred


def _make_token_manager(
    decrypted_data: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock TokenManager."""
    tm = MagicMock()
    data = decrypted_data or {"access_token": "ya29.test_token", "refresh_token": "1//refresh"}
    tm.decrypt.return_value = data
    tm.encrypt.return_value = (b"re-encrypted", "v1")
    return tm


class TestGetCredentials:
    @pytest.mark.asyncio
    async def test_returns_credentials_by_provider(
        self, employee_id: UUID, tenant_id: UUID
    ) -> None:
        cred = _make_credential(
            employee_id=employee_id, tenant_id=tenant_id, provider="google_workspace"
        )
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cred]
        session.execute.return_value = result_mock

        tm = _make_token_manager()
        injector = CredentialInjector(session, tm)

        creds = await injector.get_credentials(employee_id, tenant_id)

        assert "google_workspace" in creds
        assert creds["google_workspace"]["access_token"] == "ya29.test_token"
        tm.decrypt.assert_called_once_with(b"encrypted", "v1")

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_credentials(
        self, employee_id: UUID, tenant_id: UUID
    ) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute.return_value = result_mock

        tm = _make_token_manager()
        injector = CredentialInjector(session, tm)

        creds = await injector.get_credentials(employee_id, tenant_id)
        assert creds == {}

    @pytest.mark.asyncio
    async def test_skips_credential_with_no_integration(
        self, employee_id: UUID, tenant_id: UUID
    ) -> None:
        cred = _make_credential(employee_id=employee_id, tenant_id=tenant_id)
        cred.integration = None  # Orphaned credential

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cred]
        session.execute.return_value = result_mock

        tm = _make_token_manager()
        injector = CredentialInjector(session, tm)

        creds = await injector.get_credentials(employee_id, tenant_id)
        assert creds == {}

    @pytest.mark.asyncio
    async def test_handles_decryption_failure_gracefully(
        self, employee_id: UUID, tenant_id: UUID
    ) -> None:
        cred = _make_credential(employee_id=employee_id, tenant_id=tenant_id)
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cred]
        session.execute.return_value = result_mock

        tm = _make_token_manager()
        tm.decrypt.side_effect = Exception("Decryption failed")
        injector = CredentialInjector(session, tm)

        creds = await injector.get_credentials(employee_id, tenant_id)
        assert creds == {}  # Graceful — no credentials, no crash


class TestGetAccessToken:
    @pytest.mark.asyncio
    async def test_returns_token_string(self, employee_id: UUID, tenant_id: UUID) -> None:
        cred = _make_credential(
            employee_id=employee_id, tenant_id=tenant_id, provider="google_workspace"
        )
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cred]
        session.execute.return_value = result_mock

        tm = _make_token_manager()
        injector = CredentialInjector(session, tm)

        token = await injector.get_access_token(employee_id, tenant_id, "google_workspace")
        assert token == "ya29.test_token"

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_provider(
        self, employee_id: UUID, tenant_id: UUID
    ) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute.return_value = result_mock

        tm = _make_token_manager()
        injector = CredentialInjector(session, tm)

        token = await injector.get_access_token(employee_id, tenant_id, "hubspot")
        assert token is None


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_refreshes_near_expiry_token(self, employee_id: UUID, tenant_id: UUID) -> None:
        """Token expiring in 2 minutes should trigger refresh."""
        cred = _make_credential(
            employee_id=employee_id,
            tenant_id=tenant_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=2),  # Within 5-min buffer
        )
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cred]
        session.execute.return_value = result_mock

        tm = _make_token_manager({"access_token": "old_token", "refresh_token": "1//refresh"})

        with (
            patch("empla.services.integrations.providers.get_provider") as mock_get_provider,
            patch("empla.services.integrations.utils.get_effective_oauth_config") as mock_config,
            patch("empla.services.integrations.utils.get_effective_client_secret") as mock_secret,
        ):
            mock_provider = AsyncMock()
            mock_provider.refresh_token.return_value = {
                "access_token": "new_token",
                "expires_in": 3600,
            }
            mock_get_provider.return_value = mock_provider
            mock_config.return_value = {"client_id": "test_client"}
            mock_secret.return_value = "test_secret"

            injector = CredentialInjector(session, tm)
            creds = await injector.get_credentials(employee_id, tenant_id)

            assert creds["google_workspace"]["access_token"] == "new_token"
            mock_provider.refresh_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_stale_token_on_refresh_failure(
        self, employee_id: UUID, tenant_id: UUID
    ) -> None:
        """If refresh fails, still return the old token (graceful degradation)."""
        cred = _make_credential(
            employee_id=employee_id,
            tenant_id=tenant_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=2),
        )
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cred]
        session.execute.return_value = result_mock

        tm = _make_token_manager({"access_token": "stale_token", "refresh_token": "1//refresh"})

        with patch("empla.services.integrations.providers.get_provider") as mock_get_provider:
            mock_get_provider.side_effect = Exception("Provider unavailable")

            injector = CredentialInjector(session, tm)
            creds = await injector.get_credentials(employee_id, tenant_id)

            # Should still return the stale token
            assert creds["google_workspace"]["access_token"] == "stale_token"

    @pytest.mark.asyncio
    async def test_uses_stale_token_when_provider_refresh_raises(
        self, employee_id: UUID, tenant_id: UUID
    ) -> None:
        """If provider.refresh_token() raises, still return stale token."""
        cred = _make_credential(
            employee_id=employee_id,
            tenant_id=tenant_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=2),
        )
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cred]
        session.execute.return_value = result_mock

        tm = _make_token_manager({"access_token": "stale_token", "refresh_token": "1//refresh"})

        with (
            patch("empla.services.integrations.providers.get_provider") as mock_get_provider,
            patch("empla.services.integrations.utils.get_effective_oauth_config") as mock_config,
            patch("empla.services.integrations.utils.get_effective_client_secret") as mock_secret,
        ):
            mock_provider = AsyncMock()
            mock_provider.refresh_token.side_effect = Exception("OAuth server down")
            mock_get_provider.return_value = mock_provider
            mock_config.return_value = {"client_id": "cid"}
            mock_secret.return_value = "csec"

            injector = CredentialInjector(session, tm)
            creds = await injector.get_credentials(employee_id, tenant_id)

            assert creds["google_workspace"]["access_token"] == "stale_token"
            mock_provider.refresh_token.assert_called_once()
            session.rollback.assert_awaited()  # Session rolled back after failure

    @pytest.mark.asyncio
    async def test_no_refresh_when_token_not_near_expiry(
        self, employee_id: UUID, tenant_id: UUID
    ) -> None:
        """Token with 30 minutes left should NOT be refreshed."""
        cred = _make_credential(
            employee_id=employee_id,
            tenant_id=tenant_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cred]
        session.execute.return_value = result_mock

        tm = _make_token_manager()
        injector = CredentialInjector(session, tm)
        creds = await injector.get_credentials(employee_id, tenant_id)

        assert creds["google_workspace"]["access_token"] == "ya29.test_token"
        # encrypt should NOT be called (no refresh happened)
        tm.encrypt.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_refresh_token_returns_stale(self, employee_id: UUID, tenant_id: UUID) -> None:
        """Credential with no refresh_token should return stale token without attempting refresh."""
        cred = _make_credential(
            employee_id=employee_id,
            tenant_id=tenant_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=2),  # Within buffer
        )
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cred]
        session.execute.return_value = result_mock

        # No refresh_token in decrypted data
        tm = _make_token_manager({"access_token": "token_without_refresh"})
        injector = CredentialInjector(session, tm)
        creds = await injector.get_credentials(employee_id, tenant_id)

        assert creds["google_workspace"]["access_token"] == "token_without_refresh"
        tm.encrypt.assert_not_called()  # No refresh attempted

    @pytest.mark.asyncio
    async def test_no_expires_at_skips_refresh(self, employee_id: UUID, tenant_id: UUID) -> None:
        """Credential with no expires_at (e.g., API key) should not attempt refresh."""
        cred = _make_credential(
            employee_id=employee_id,
            tenant_id=tenant_id,
        )
        cred.expires_at = None  # Non-expiring token

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cred]
        session.execute.return_value = result_mock

        tm = _make_token_manager()
        injector = CredentialInjector(session, tm)
        creds = await injector.get_credentials(employee_id, tenant_id)

        assert creds["google_workspace"]["access_token"] == "ya29.test_token"
        tm.encrypt.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_persists_new_token(self, employee_id: UUID, tenant_id: UUID) -> None:
        """After refresh, encrypted data and expiry should be updated on the credential."""
        cred = _make_credential(
            employee_id=employee_id,
            tenant_id=tenant_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=2),
        )
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cred]
        session.execute.return_value = result_mock

        tm = _make_token_manager({"access_token": "old", "refresh_token": "1//r"})

        with (
            patch("empla.services.integrations.providers.get_provider") as mock_get_provider,
            patch("empla.services.integrations.utils.get_effective_oauth_config") as mock_config,
            patch("empla.services.integrations.utils.get_effective_client_secret") as mock_secret,
        ):
            mock_provider = AsyncMock()
            mock_provider.refresh_token.return_value = {
                "access_token": "new",
                "expires_in": 7200,
            }
            mock_get_provider.return_value = mock_provider
            mock_config.return_value = {"client_id": "cid"}
            mock_secret.return_value = "csec"

            injector = CredentialInjector(session, tm)
            await injector.get_credentials(employee_id, tenant_id)

            # Verify persistence
            tm.encrypt.assert_called_once()
            encrypted_data = tm.encrypt.call_args[0][0]
            assert encrypted_data["access_token"] == "new"
            assert cred.encrypted_data == b"re-encrypted"
            assert cred.encryption_key_id == "v1"
            assert cred.last_refreshed_at is not None
            assert cred.expires_at is not None
            session.flush.assert_awaited_once()
