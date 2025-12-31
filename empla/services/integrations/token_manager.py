"""
empla.services.integrations.token_manager - Token Encryption & Refresh

Manages token encryption, decryption, and automatic refresh for OAuth credentials.

Features:
- Fernet encryption (AES-128-CBC with HMAC authentication)
- Key rotation support via encryption_key_id tracking
- Automatic token refresh before expiry
- Transparent refresh on credential access

Security:
- Tokens encrypted at rest in database
- Different ciphertext on each encryption (random IV)
- No sensitive data logged
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from empla.services.integrations.key_provider import KeyProvider, get_key_provider

if TYPE_CHECKING:
    from empla.models.integration import Integration, IntegrationCredential

logger = logging.getLogger(__name__)


class TokenManagerError(Exception):
    """Base exception for token manager errors."""


class DecryptionError(TokenManagerError):
    """Raised when token decryption fails."""


class RefreshError(TokenManagerError):
    """Raised when token refresh fails."""


class TokenManager:
    """
    Manages token encryption, decryption, and refresh.

    Uses Fernet (symmetric encryption based on AES-128-CBC with HMAC)
    for application-level encryption. Keys are versioned to support
    rotation without re-encrypting all credentials at once.

    Example:
        >>> manager = TokenManager()
        >>> data = {"access_token": "secret123", "refresh_token": "refresh456"}
        >>> encrypted, key_id = manager.encrypt(data)
        >>> decrypted = manager.decrypt(encrypted, key_id)
        >>> assert decrypted == data
    """

    def __init__(self, key_provider: KeyProvider | None = None) -> None:
        """
        Initialize token manager.

        Args:
            key_provider: Key provider instance (uses default if None)
        """
        self.key_provider = key_provider or get_key_provider()
        self._fernet_instances: dict[str, Fernet] = {}

    def _get_fernet(self, key_id: str) -> Fernet:
        """
        Get or create Fernet instance for key.

        Args:
            key_id: Key identifier

        Returns:
            Fernet instance for the key
        """
        if key_id not in self._fernet_instances:
            key = self.key_provider.get_key(key_id)
            self._fernet_instances[key_id] = Fernet(key)
        return self._fernet_instances[key_id]

    def encrypt(self, data: dict[str, Any]) -> tuple[bytes, str]:
        """
        Encrypt credential data.

        Args:
            data: Dictionary to encrypt (typically contains access_token, refresh_token, etc.)

        Returns:
            Tuple of (encrypted_bytes, key_id)

        Example:
            >>> encrypted, key_id = manager.encrypt({"access_token": "..."})
            >>> # Store encrypted in database, key_id in encryption_key_id column
        """
        current_key_id = self.key_provider.get_current_key_id()
        fernet = self._get_fernet(current_key_id)

        # Serialize to JSON bytes
        json_bytes = json.dumps(data).encode("utf-8")

        # Encrypt (Fernet adds timestamp and random IV automatically)
        encrypted = fernet.encrypt(json_bytes)

        logger.debug(
            f"Encrypted credential data with key {current_key_id}",
            extra={"key_id": current_key_id, "data_size": len(json_bytes)},
        )

        return encrypted, current_key_id

    def decrypt(self, encrypted_data: bytes, key_id: str) -> dict[str, Any]:
        """
        Decrypt credential data.

        Args:
            encrypted_data: Encrypted bytes from database
            key_id: Key ID used for encryption

        Returns:
            Decrypted dictionary

        Raises:
            DecryptionError: If decryption fails (invalid key, corrupted data, etc.)

        Example:
            >>> data = manager.decrypt(credential.encrypted_data, credential.encryption_key_id)
            >>> access_token = data["access_token"]
        """
        try:
            fernet = self._get_fernet(key_id)
            decrypted = fernet.decrypt(encrypted_data)
            return json.loads(decrypted.decode("utf-8"))

        except InvalidToken as e:
            logger.error(
                "Failed to decrypt credential: invalid token",
                extra={"key_id": key_id},
            )
            raise DecryptionError(f"Failed to decrypt credential: {e}") from e

        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse decrypted data as JSON",
                extra={"key_id": key_id},
            )
            raise DecryptionError(f"Invalid credential format: {e}") from e

        except Exception as e:
            logger.error(
                f"Unexpected error decrypting credential: {e}",
                extra={"key_id": key_id},
            )
            raise DecryptionError(f"Decryption failed: {e}") from e

    async def rotate_credential(
        self,
        credential: "IntegrationCredential",
        session: AsyncSession,
    ) -> "IntegrationCredential":
        """
        Re-encrypt credential with current key (for key rotation).

        Args:
            credential: Credential to rotate
            session: Database session

        Returns:
            Updated credential with new encryption

        Example:
            >>> # After adding new ENCRYPTION_KEY_V2
            >>> rotated = await manager.rotate_credential(credential, session)
        """
        current_key_id = self.key_provider.get_current_key_id()

        # Skip if already using current key
        if credential.encryption_key_id == current_key_id:
            logger.debug(f"Credential {credential.id} already using current key")
            return credential

        # Decrypt with old key
        data = self.decrypt(credential.encrypted_data, credential.encryption_key_id)

        # Encrypt with new key
        encrypted, new_key_id = self.encrypt(data)

        # Update credential
        credential.encrypted_data = encrypted
        credential.encryption_key_id = new_key_id

        await session.commit()
        await session.refresh(credential)

        logger.info(
            f"Rotated credential {credential.id} from {credential.encryption_key_id} to {new_key_id}",
            extra={
                "credential_id": str(credential.id),
                "old_key": credential.encryption_key_id,
                "new_key": new_key_id,
            },
        )

        return credential

    async def refresh_if_needed(
        self,
        credential: "IntegrationCredential",
        integration: "Integration",
        session: AsyncSession,
        provider: Any,  # OAuthProvider - avoid circular import
        buffer_minutes: int = 5,
    ) -> dict[str, Any]:
        """
        Refresh token if expiring soon.

        Automatically refreshes the token if it expires within buffer_minutes.
        Updates the credential in the database with new tokens.

        Args:
            credential: Credential to potentially refresh
            integration: Integration configuration
            session: Database session
            provider: OAuth provider instance for refresh
            buffer_minutes: Refresh if expiring within this many minutes

        Returns:
            Decrypted credential data (refreshed if needed)

        Example:
            >>> data = await manager.refresh_if_needed(
            ...     credential, integration, session, google_provider
            ... )
            >>> access_token = data["access_token"]  # Always valid
        """
        data = self.decrypt(credential.encrypted_data, credential.encryption_key_id)

        # Check if refresh needed
        if credential.expires_at:
            threshold = datetime.now(UTC) + timedelta(minutes=buffer_minutes)

            if credential.expires_at <= threshold:
                logger.info(
                    f"Refreshing token for credential {credential.id} "
                    f"(expires at {credential.expires_at}, threshold {threshold})",
                    extra={"credential_id": str(credential.id)},
                )

                try:
                    # Mark as refreshing
                    credential.status = "refreshing"
                    await session.commit()

                    # Refresh with provider
                    refresh_token = data.get("refresh_token")
                    if not refresh_token:
                        raise RefreshError("No refresh token available")

                    new_tokens = await provider.refresh_token(
                        refresh_token=refresh_token,
                        client_id=integration.oauth_config.get("client_id"),
                        client_secret=await self._get_client_secret(integration),
                    )

                    # Update data with new tokens
                    data.update(new_tokens)

                    # Re-encrypt with potentially new key
                    encrypted, key_id = self.encrypt(data)

                    # Update credential
                    credential.encrypted_data = encrypted
                    credential.encryption_key_id = key_id
                    credential.last_refreshed_at = datetime.now(UTC)
                    credential.status = "active"

                    # Calculate new expiry
                    expires_in = new_tokens.get("expires_in", 3600)
                    credential.expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

                    await session.commit()
                    await session.refresh(credential)

                    logger.info(
                        f"Successfully refreshed token for credential {credential.id}",
                        extra={
                            "credential_id": str(credential.id),
                            "new_expires_at": str(credential.expires_at),
                        },
                    )

                except Exception as e:
                    # Revert status on failure
                    credential.status = "active"
                    await session.commit()

                    logger.error(
                        f"Failed to refresh token for credential {credential.id}: {e}",
                        extra={"credential_id": str(credential.id)},
                        exc_info=True,
                    )
                    raise RefreshError(f"Token refresh failed: {e}") from e

        return data

    async def _get_client_secret(self, integration: "Integration") -> str:
        """
        Get OAuth client secret from secure storage.

        Delegates to shared utility function.

        Args:
            integration: Integration configuration

        Returns:
            Client secret string

        Raises:
            ClientSecretNotConfiguredError: If client secret is not configured
        """
        from empla.services.integrations.utils import get_oauth_client_secret

        return get_oauth_client_secret(integration)


# Default instance (can be replaced for testing)
_default_manager: TokenManager | None = None


def get_token_manager() -> TokenManager:
    """
    Get the default token manager instance.

    Returns:
        TokenManager instance
    """
    global _default_manager  # noqa: PLW0603
    if _default_manager is None:
        _default_manager = TokenManager()
    return _default_manager


def set_token_manager(manager: TokenManager | None) -> None:
    """
    Set the default token manager (for testing).

    Args:
        manager: TokenManager instance or None to reset
    """
    global _default_manager  # noqa: PLW0603
    _default_manager = manager
