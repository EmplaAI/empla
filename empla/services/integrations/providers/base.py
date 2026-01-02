"""
empla.services.integrations.providers.base - OAuth Provider Protocol

Defines the interface that all OAuth providers must implement.
"""

from abc import ABC, abstractmethod
from typing import Any


class OAuthProvider(ABC):
    """
    Abstract base class for OAuth provider implementations.

    All OAuth providers (Google, Microsoft, etc.) must implement this interface
    to ensure consistent behavior across the integration layer.

    Example:
        >>> class MyProvider(OAuthProvider):
        ...     def get_authorization_url(self, ...): ...
        ...     async def exchange_code(self, ...): ...
        ...     async def refresh_token(self, ...): ...
        ...     async def revoke_token(self, ...): ...
        ...     async def get_user_info(self, ...): ...
    """

    @abstractmethod
    def get_authorization_url(
        self,
        client_id: str,
        redirect_uri: str,
        scopes: list[str],
        state: str,
        code_challenge: str | None = None,
        code_challenge_method: str = "S256",
    ) -> str:
        """
        Generate OAuth authorization URL.

        Args:
            client_id: OAuth client ID
            redirect_uri: Callback URL after authorization
            scopes: List of OAuth scopes to request
            state: CSRF protection state parameter
            code_challenge: PKCE code challenge (optional but recommended)
            code_challenge_method: PKCE method ("S256" or "plain")

        Returns:
            Authorization URL to redirect user to

        Example:
            >>> url = provider.get_authorization_url(
            ...     client_id="12345.apps.googleusercontent.com",
            ...     redirect_uri="https://app.empla.ai/oauth/callback",
            ...     scopes=["https://www.googleapis.com/auth/gmail.modify"],
            ...     state="abc123",
            ... )
            >>> # Redirect user to url
        """
        ...

    @abstractmethod
    async def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> dict[str, Any]:
        """
        Exchange authorization code for tokens.

        Args:
            code: Authorization code from callback
            client_id: OAuth client ID
            client_secret: OAuth client secret
            redirect_uri: Same redirect URI used in authorization
            code_verifier: PKCE code verifier (if using PKCE)

        Returns:
            Token response dictionary containing:
            - access_token: Bearer token for API calls
            - refresh_token: Token for refreshing access (may be absent)
            - expires_in: Seconds until access token expires
            - token_type: Token type (usually "Bearer")
            - scope: Granted scopes (space-separated)

        Example:
            >>> tokens = await provider.exchange_code(
            ...     code="4/0AX...",
            ...     client_id="...",
            ...     client_secret="...",
            ...     redirect_uri="https://app.empla.ai/oauth/callback",
            ... )
            >>> access_token = tokens["access_token"]
        """
        ...

    @abstractmethod
    async def refresh_token(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: str,
    ) -> dict[str, Any]:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: Refresh token from initial authorization
            client_id: OAuth client ID
            client_secret: OAuth client secret

        Returns:
            Token response dictionary (same format as exchange_code)
            Note: Some providers return a new refresh token, some don't

        Raises:
            Exception: If refresh fails (token revoked, expired, etc.)

        Example:
            >>> new_tokens = await provider.refresh_token(
            ...     refresh_token="1//0eabc...",
            ...     client_id="...",
            ...     client_secret="...",
            ... )
        """
        ...

    @abstractmethod
    async def revoke_token(
        self,
        token: str,
        token_type_hint: str = "access_token",
    ) -> None:
        """
        Revoke an access or refresh token.

        Args:
            token: Token to revoke
            token_type_hint: Type of token ("access_token" or "refresh_token")

        Example:
            >>> await provider.revoke_token(
            ...     token="ya29.a0AX...",
            ...     token_type_hint="access_token",
            ... )
        """
        ...

    @abstractmethod
    async def get_user_info(
        self,
        access_token: str,
    ) -> dict[str, Any]:
        """
        Get user information from the token.

        Args:
            access_token: Valid access token

        Returns:
            User info dictionary containing at minimum:
            - email: User's email address
            - name: User's display name (if available)
            - sub/id: User's unique identifier

        Example:
            >>> user_info = await provider.get_user_info(access_token)
            >>> print(user_info["email"])
        """
        ...

    def get_default_scopes(self) -> list[str]:
        """
        Get default scopes for this provider.

        Subclasses can override to provide sensible defaults.

        Returns:
            List of default OAuth scopes
        """
        return []

    def get_service_account_scopes(self) -> list[str]:
        """
        Get scopes available for service account authentication.

        Returns:
            List of scopes that work with service accounts
        """
        return self.get_default_scopes()
