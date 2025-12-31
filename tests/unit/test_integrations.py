"""
tests/unit/test_integrations.py - Integration Layer Unit Tests

Tests for:
- KeyProvider (encryption key management)
- TokenManager (token encryption/decryption)
- OAuth Providers (URL generation, token exchange)
"""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from empla.services.integrations.key_provider import (
    EnvironmentKeyProvider,
    KeyNotFoundError,
    generate_encryption_key,
)
from empla.services.integrations.providers.google import (
    GoogleWorkspaceProvider,
    generate_pkce_pair,
)
from empla.services.integrations.providers.microsoft import MicrosoftGraphProvider
from empla.services.integrations.token_manager import (
    DecryptionError,
    TokenManager,
)


class TestGenerateEncryptionKey:
    """Tests for encryption key generation."""

    def test_generates_32_byte_key(self):
        """Key should be 32 bytes base64 encoded."""
        key = generate_encryption_key()
        decoded = base64.urlsafe_b64decode(key)
        assert len(decoded) == 32

    def test_generates_unique_keys(self):
        """Each call should generate a unique key."""
        keys = [generate_encryption_key() for _ in range(10)]
        assert len(set(keys)) == 10

    def test_key_is_valid_fernet_key(self):
        """Generated key should work with Fernet."""
        from cryptography.fernet import Fernet

        key = generate_encryption_key()
        # Fernet requires a URL-safe base64-encoded 32-byte key
        fernet = Fernet(key)
        # Should be able to encrypt/decrypt
        message = b"test message"
        encrypted = fernet.encrypt(message)
        decrypted = fernet.decrypt(encrypted)
        assert decrypted == message


class TestEnvironmentKeyProvider:
    """Tests for EnvironmentKeyProvider."""

    def test_loads_key_from_env(self):
        """Should load encryption key from environment."""
        key = generate_encryption_key()
        with patch.dict(
            "os.environ",
            {"ENCRYPTION_KEY_ID": "key_v1", "ENCRYPTION_KEY_V1": key},
        ):
            provider = EnvironmentKeyProvider()
            assert provider.get_current_key_id() == "key_v1"
            assert provider.get_key("key_v1") == key.encode()

    def test_supports_multiple_keys(self):
        """Should support multiple key versions for rotation."""
        key1 = generate_encryption_key()
        key2 = generate_encryption_key()
        with patch.dict(
            "os.environ",
            {
                "ENCRYPTION_KEY_ID": "key_v2",
                "ENCRYPTION_KEY_V1": key1,
                "ENCRYPTION_KEY_V2": key2,
            },
        ):
            provider = EnvironmentKeyProvider()
            assert provider.get_current_key_id() == "key_v2"
            assert provider.get_key("key_v1") == key1.encode()
            assert provider.get_key("key_v2") == key2.encode()
            assert set(provider.list_key_ids()) == {"key_v1", "key_v2"}

    def test_raises_key_not_found(self):
        """Should raise KeyNotFoundError for unknown key ID."""
        key = generate_encryption_key()
        with patch.dict(
            "os.environ",
            {"ENCRYPTION_KEY_ID": "key_v1", "ENCRYPTION_KEY_V1": key},
        ):
            provider = EnvironmentKeyProvider()
            with pytest.raises(KeyNotFoundError):
                provider.get_key("key_v99")

    def test_development_mode_auto_generates_key(self):
        """In dev mode without keys, should auto-generate a temporary key."""
        # Use clear=True to fully isolate environment - no ENCRYPTION_KEY* vars present
        with patch.dict(
            "os.environ",
            {"EMPLA_ENV": "development"},
            clear=True,
        ):
            provider = EnvironmentKeyProvider()
            # Should have a key (auto-generated)
            key_id = provider.get_current_key_id()
            assert key_id is not None
            key = provider.get_key(key_id)
            assert key is not None


class TestTokenManager:
    """Tests for TokenManager encryption/decryption."""

    @pytest.fixture
    def token_manager(self):
        """Create token manager with test key."""
        key = generate_encryption_key()
        with patch.dict(
            "os.environ",
            {"ENCRYPTION_KEY_ID": "key_v1", "ENCRYPTION_KEY_V1": key},
        ):
            provider = EnvironmentKeyProvider()
            return TokenManager(provider)

    def test_encrypt_decrypt_roundtrip(self, token_manager):
        """Should encrypt and decrypt data correctly."""
        original = {
            "access_token": "ya29.abc123",
            "refresh_token": "1//0efg456",
            "expires_in": 3600,
        }

        encrypted, key_id = token_manager.encrypt(original)
        assert key_id == "key_v1"
        assert encrypted != json.dumps(original).encode()

        decrypted = token_manager.decrypt(encrypted, key_id)
        assert decrypted == original

    def test_encryption_is_non_deterministic(self, token_manager):
        """Same data should produce different ciphertext each time."""
        data = {"token": "secret123"}
        encrypted1, _ = token_manager.encrypt(data)
        encrypted2, _ = token_manager.encrypt(data)
        assert encrypted1 != encrypted2

    def test_decrypt_wrong_key_fails(self, token_manager):
        """Decryption with wrong key should fail."""
        data = {"token": "secret123"}
        encrypted, _ = token_manager.encrypt(data)

        with pytest.raises(DecryptionError):
            token_manager.decrypt(encrypted, "key_v99")

    def test_decrypt_corrupted_data_fails(self, token_manager):
        """Decryption of corrupted data should fail."""
        with pytest.raises(DecryptionError):
            token_manager.decrypt(b"corrupted_data", "key_v1")


class TestPKCE:
    """Tests for PKCE code verifier/challenge generation."""

    def test_generates_verifier_and_challenge(self):
        """Should generate both verifier and challenge."""
        verifier, challenge = generate_pkce_pair()
        assert len(verifier) > 40  # Should be ~43 chars
        assert len(challenge) > 40

    def test_verifier_and_challenge_are_different(self):
        """Verifier and challenge should not be the same."""
        verifier, challenge = generate_pkce_pair()
        assert verifier != challenge

    def test_challenge_is_sha256_of_verifier(self):
        """Challenge should be BASE64URL(SHA256(verifier))."""
        import hashlib

        verifier, challenge = generate_pkce_pair()

        # Compute expected challenge
        digest = hashlib.sha256(verifier.encode()).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

        assert challenge == expected

    def test_generates_unique_pairs(self):
        """Each call should generate unique pair."""
        pairs = [generate_pkce_pair() for _ in range(10)]
        verifiers = [p[0] for p in pairs]
        assert len(set(verifiers)) == 10


class TestGoogleWorkspaceProvider:
    """Tests for Google Workspace OAuth provider."""

    @pytest.fixture
    def provider(self):
        return GoogleWorkspaceProvider()

    def test_authorization_url_includes_required_params(self, provider):
        """Authorization URL should include all required OAuth params."""
        url = provider.get_authorization_url(
            client_id="test-client-id",
            redirect_uri="https://example.com/callback",
            scopes=["https://www.googleapis.com/auth/gmail.modify"],
            state="test-state-123",
        )

        assert "https://accounts.google.com/o/oauth2/v2/auth" in url
        assert "client_id=test-client-id" in url
        assert "redirect_uri=https%3A%2F%2Fexample.com%2Fcallback" in url
        assert "state=test-state-123" in url
        assert "response_type=code" in url
        assert "access_type=offline" in url

    def test_authorization_url_with_pkce(self, provider):
        """Authorization URL should include PKCE challenge when provided."""
        _, challenge = generate_pkce_pair()
        url = provider.get_authorization_url(
            client_id="test-client-id",
            redirect_uri="https://example.com/callback",
            scopes=["email"],
            state="test-state",
            code_challenge=challenge,
        )

        assert f"code_challenge={challenge}" in url
        assert "code_challenge_method=S256" in url

    def test_default_scopes_includes_gmail_and_calendar(self, provider):
        """Default scopes should include Gmail and Calendar."""
        scopes = provider.get_default_scopes()
        assert "https://www.googleapis.com/auth/gmail.modify" in scopes
        assert "https://www.googleapis.com/auth/calendar" in scopes
        assert "openid" in scopes

    @pytest.mark.asyncio
    async def test_exchange_code_success(self, provider):
        """Token exchange should return tokens on success."""
        mock_response = {
            "access_token": "ya29.test123",
            "refresh_token": "1//0etest456",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
            )

            tokens = await provider.exchange_code(
                code="4/0AX123",
                client_id="test-client",
                client_secret="test-secret",
                redirect_uri="https://example.com/callback",
            )

            assert tokens["access_token"] == "ya29.test123"
            assert tokens["refresh_token"] == "1//0etest456"

    @pytest.mark.asyncio
    async def test_refresh_token_preserves_original(self, provider):
        """Token refresh should preserve original refresh token if not returned."""
        mock_response = {
            "access_token": "ya29.new123",
            "expires_in": 3600,
            "token_type": "Bearer",
            # Note: no refresh_token in response
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
            )

            tokens = await provider.refresh_token(
                refresh_token="1//original-token",
                client_id="test-client",
                client_secret="test-secret",
            )

            # Original refresh token should be preserved
            assert tokens["refresh_token"] == "1//original-token"
            assert tokens["access_token"] == "ya29.new123"


class TestMicrosoftGraphProvider:
    """Tests for Microsoft Graph OAuth provider."""

    @pytest.fixture
    def provider(self):
        return MicrosoftGraphProvider()

    def test_authorization_url_uses_common_tenant(self, provider):
        """Authorization URL should use 'common' tenant by default."""
        url = provider.get_authorization_url(
            client_id="00000000-0000-0000-0000-000000000000",
            redirect_uri="https://example.com/callback",
            scopes=["Mail.Read"],
            state="test-state",
        )

        assert "login.microsoftonline.com/common" in url

    def test_authorization_url_adds_offline_access(self, provider):
        """Microsoft requires offline_access scope for refresh tokens."""
        url = provider.get_authorization_url(
            client_id="test-client",
            redirect_uri="https://example.com/callback",
            scopes=["Mail.Read"],  # Without offline_access
            state="test-state",
        )

        assert "offline_access" in url

    def test_custom_tenant_in_url(self):
        """Should use custom tenant ID when provided."""
        provider = MicrosoftGraphProvider(tenant="my-tenant-id")
        url = provider.get_authorization_url(
            client_id="test-client",
            redirect_uri="https://example.com/callback",
            scopes=["Mail.Read"],
            state="test-state",
        )

        assert "login.microsoftonline.com/my-tenant-id" in url

    def test_default_scopes_includes_mail_and_calendar(self, provider):
        """Default scopes should include Mail and Calendar."""
        scopes = provider.get_default_scopes()
        assert "Mail.Read" in scopes
        assert "Calendars.Read" in scopes
        assert "offline_access" in scopes

    @pytest.mark.asyncio
    async def test_revoke_token_logs_warning(self, provider):
        """Microsoft doesn't support token revocation - should log warning."""
        # This should not raise, just log a warning
        await provider.revoke_token("test-token")

    @pytest.mark.asyncio
    async def test_get_user_info_normalizes_response(self, provider):
        """User info should normalize Microsoft's response format."""
        mock_response = {
            "id": "user-123",
            "mail": "user@example.com",
            "displayName": "Test User",
            "givenName": "Test",
            "surname": "User",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
            )

            user_info = await provider.get_user_info("test-access-token")

            # Should have normalized fields
            assert user_info["email"] == "user@example.com"
            assert user_info["name"] == "Test User"
            assert user_info["given_name"] == "Test"
            assert user_info["family_name"] == "User"
