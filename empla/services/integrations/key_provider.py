"""
empla.services.integrations.key_provider - Encryption Key Management

Manages encryption keys for credential storage with support for key rotation.

Key Storage (by environment):
- Development: Environment variables (ENCRYPTION_KEY_V1, ENCRYPTION_KEY_V2, etc.)
- Production: AWS Secrets Manager / HashiCorp Vault / Azure Key Vault

Key Rotation:
- Keys are versioned (key_v1, key_v2, etc.)
- Current key ID stored in ENCRYPTION_KEY_ID environment variable
- Old keys kept for decryption
- Re-encryption happens on credential access (lazy) or via batch job (eager)
"""

import base64
import binascii
import logging
import os
import re
from abc import ABC, abstractmethod

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class KeyProviderError(Exception):
    """Base exception for key provider errors."""


class KeyNotFoundError(KeyProviderError):
    """Raised when a requested key is not found."""


class NoKeysConfiguredError(KeyProviderError):
    """Raised when no encryption keys are configured."""


class KeyProvider(ABC):
    """
    Abstract base class for encryption key providers.

    Implementations handle loading keys from different sources:
    - Environment variables (development)
    - AWS Secrets Manager (production)
    - HashiCorp Vault (production)
    - Azure Key Vault (production)

    Example:
        >>> provider = EnvironmentKeyProvider()
        >>> current_key_id = provider.get_current_key_id()
        >>> key = provider.get_key(current_key_id)
        >>> fernet = Fernet(key)
    """

    @abstractmethod
    def get_current_key_id(self) -> str:
        """
        Get the ID of the current encryption key.

        Returns:
            Key ID (e.g., "key_v1", "key_v2")
        """
        ...

    @abstractmethod
    def get_key(self, key_id: str) -> bytes:
        """
        Get encryption key by ID.

        Args:
            key_id: Key identifier

        Returns:
            32-byte Fernet key (base64-encoded)

        Raises:
            KeyNotFoundError: If key is not found
        """
        ...

    @abstractmethod
    def list_key_ids(self) -> list[str]:
        """
        List all available key IDs.

        Returns:
            List of key IDs
        """
        ...


class EnvironmentKeyProvider(KeyProvider):
    """
    Key provider that loads keys from environment variables.

    Environment variables:
    - ENCRYPTION_KEY_ID: Current key ID (e.g., "key_v1")
    - ENCRYPTION_KEY_V1: Base64-encoded 32-byte Fernet key
    - ENCRYPTION_KEY_V2: Base64-encoded 32-byte Fernet key (for rotation)
    - etc.

    Example:
        # Generate a key:
        >>> from cryptography.fernet import Fernet
        >>> import base64
        >>> key = Fernet.generate_key()
        >>> print(key.decode())  # Set this as ENCRYPTION_KEY_V1

    Usage:
        >>> provider = EnvironmentKeyProvider()
        >>> key = provider.get_key("key_v1")
    """

    # Pattern to match key environment variables
    KEY_ENV_PATTERN = re.compile(r"^ENCRYPTION_KEY_V(\d+)$")

    def __init__(self) -> None:
        """
        Initialize key provider from environment.

        Raises:
            NoKeysConfiguredError: If no encryption keys are configured
        """
        self._keys: dict[str, bytes] = {}
        self._current_key_id: str = ""
        self._load_keys()

    def _load_keys(self) -> None:
        """Load encryption keys from environment variables."""
        # Load current key ID
        self._current_key_id = os.getenv("ENCRYPTION_KEY_ID", "key_v1")

        # Load all available keys
        for key, value in os.environ.items():
            match = self.KEY_ENV_PATTERN.match(key)
            if match and value:
                version = match.group(1)
                key_id = f"key_v{version}"
                try:
                    # Validate it's a valid Fernet key
                    decoded = base64.urlsafe_b64decode(value)
                    if len(decoded) == 32:
                        # Store the original base64 key, not decoded
                        self._keys[key_id] = value.encode()
                    else:
                        logger.warning(f"Invalid key length for {key_id}: expected 32 bytes")
                except (binascii.Error, ValueError, TypeError) as e:
                    logger.warning(f"Invalid key format for {key_id}: {e}")

        if not self._keys:
            empla_env = os.getenv("EMPLA_ENV")

            # Only generate temporary key when EMPLA_ENV is explicitly "development"
            if empla_env == "development":
                logger.warning(
                    "No encryption keys configured. Generating temporary key for development. "
                    "Set ENCRYPTION_KEY_V1 for persistent storage. "
                    'Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
                )
                temp_key = Fernet.generate_key()
                self._keys["key_v1"] = temp_key
                self._current_key_id = "key_v1"
            elif empla_env is None:
                # EMPLA_ENV not set - fail fast to prevent accidental temp key usage
                raise NoKeysConfiguredError(
                    "No encryption keys configured and EMPLA_ENV is not set. "
                    "Set EMPLA_ENV=development to allow temporary keys, or configure "
                    "ENCRYPTION_KEY_V1 and ENCRYPTION_KEY_ID for production. "
                    'Generate a key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
                )
            else:
                # Non-development environment without keys - fail fast
                raise NoKeysConfiguredError(
                    f"No encryption keys configured for EMPLA_ENV={empla_env}. "
                    "Set ENCRYPTION_KEY_V1 and ENCRYPTION_KEY_ID environment variables."
                )

        if self._current_key_id not in self._keys:
            # Fall back to the first available key
            if self._keys:
                sorted_keys = sorted(self._keys.keys())
                self._current_key_id = sorted_keys[-1]  # Use latest version
                logger.warning(
                    f"ENCRYPTION_KEY_ID not found, falling back to {self._current_key_id}"
                )
            else:
                raise NoKeysConfiguredError("No encryption keys available")

    def get_current_key_id(self) -> str:
        """Get the current encryption key ID."""
        return self._current_key_id

    def get_key(self, key_id: str) -> bytes:
        """
        Get encryption key by ID.

        Args:
            key_id: Key identifier (e.g., "key_v1")

        Returns:
            Fernet key bytes

        Raises:
            KeyNotFoundError: If key is not found
        """
        if key_id not in self._keys:
            raise KeyNotFoundError(f"Key not found: {key_id}")
        return self._keys[key_id]

    def list_key_ids(self) -> list[str]:
        """List all available key IDs."""
        return sorted(self._keys.keys())


def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key.

    Returns:
        Base64-encoded 32-byte key suitable for ENCRYPTION_KEY_Vn environment variable

    Example:
        >>> key = generate_encryption_key()
        >>> print(f"ENCRYPTION_KEY_V1={key}")
    """
    return Fernet.generate_key().decode()


# Default provider instance (can be replaced for testing)
_default_provider: KeyProvider | None = None


def get_key_provider() -> KeyProvider:
    """
    Get the default key provider instance.

    Returns:
        KeyProvider instance

    Example:
        >>> provider = get_key_provider()
        >>> key = provider.get_key("key_v1")
    """
    global _default_provider  # noqa: PLW0603
    if _default_provider is None:
        _default_provider = EnvironmentKeyProvider()
    return _default_provider


def set_key_provider(provider: KeyProvider | None) -> None:
    """
    Set the default key provider (for testing).

    Args:
        provider: KeyProvider instance or None to reset

    Example:
        >>> from unittest.mock import Mock
        >>> mock_provider = Mock(spec=KeyProvider)
        >>> set_key_provider(mock_provider)
    """
    global _default_provider  # noqa: PLW0603
    _default_provider = provider
