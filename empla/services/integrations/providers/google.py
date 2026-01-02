"""
empla.services.integrations.providers.google - Google Workspace OAuth Provider

Implements OAuth 2.0 for Google Workspace services:
- Gmail (email)
- Google Calendar
- Google Drive
- Google Meet

Supports both:
- User OAuth: User grants access via consent screen
- Service Account: Admin delegates domain-wide access

Reference:
- https://developers.google.com/identity/protocols/oauth2
- https://developers.google.com/identity/protocols/oauth2/web-server
"""

import hashlib
import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from empla.services.integrations.providers.base import OAuthProvider

logger = logging.getLogger(__name__)


class GoogleWorkspaceProvider(OAuthProvider):
    """
    Google Workspace OAuth 2.0 provider.

    Implements the OAuth 2.0 authorization code flow with PKCE support
    for enhanced security.

    Example:
        >>> provider = GoogleWorkspaceProvider()
        >>> auth_url = provider.get_authorization_url(
        ...     client_id="12345.apps.googleusercontent.com",
        ...     redirect_uri="https://app.empla.ai/oauth/callback",
        ...     scopes=["https://www.googleapis.com/auth/gmail.modify"],
        ...     state="random-state",
        ... )
    """

    # OAuth endpoints
    AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    REVOKE_URL = "https://oauth2.googleapis.com/revoke"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    # Default timeout for HTTP requests
    TIMEOUT = 30.0

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
        Generate Google OAuth authorization URL.

        Args:
            client_id: Google OAuth client ID
            redirect_uri: Callback URL after authorization
            scopes: List of Google API scopes
            state: CSRF protection state
            code_challenge: PKCE code challenge (optional)
            code_challenge_method: PKCE method (default "S256")

        Returns:
            Authorization URL
        """
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "response_type": "code",
            "access_type": "offline",  # Get refresh token
            "prompt": "consent",  # Always show consent (ensures refresh token)
        }

        # Add PKCE if provided
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method

        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

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
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret
            redirect_uri: Same redirect URI used in authorization
            code_verifier: PKCE code verifier (if using PKCE)

        Returns:
            Token response with access_token, refresh_token, etc.

        Raises:
            httpx.HTTPStatusError: If token exchange fails
        """
        data = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        # Add PKCE verifier if provided
        if code_verifier:
            data["code_verifier"] = code_verifier

        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            response = await client.post(self.TOKEN_URL, data=data)

            if response.status_code != 200:
                logger.error(
                    f"Google token exchange failed: {response.status_code} {response.text}",
                    extra={"status_code": response.status_code},
                )
                response.raise_for_status()

            tokens = response.json()

            logger.info(
                "Google OAuth token exchange successful",
                extra={
                    "has_refresh_token": "refresh_token" in tokens,
                    "expires_in": tokens.get("expires_in"),
                    "scope": tokens.get("scope"),
                },
            )

            return tokens

    async def refresh_token(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: str,
    ) -> dict[str, Any]:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: Google refresh token
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret

        Returns:
            New token response (note: Google may not return new refresh_token)
        """
        data = {
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            response = await client.post(self.TOKEN_URL, data=data)

            if response.status_code != 200:
                logger.error(
                    f"Google token refresh failed: {response.status_code} {response.text}",
                    extra={"status_code": response.status_code},
                )
                response.raise_for_status()

            tokens = response.json()

            # Google doesn't always return a new refresh token
            # Preserve the original if not returned
            if "refresh_token" not in tokens:
                tokens["refresh_token"] = refresh_token

            logger.info(
                "Google OAuth token refresh successful",
                extra={"expires_in": tokens.get("expires_in")},
            )

            return tokens

    async def revoke_token(
        self,
        token: str,
        token_type_hint: str = "access_token",
    ) -> None:
        """
        Revoke a Google OAuth token.

        Args:
            token: Access or refresh token to revoke
            token_type_hint: Type hint (Google ignores this)
        """
        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            response = await client.post(
                self.REVOKE_URL,
                params={"token": token},
            )

            # Google returns 200 on success, 400 if token already revoked
            if response.status_code == 200:
                logger.info("Google OAuth token revoked successfully")
            elif response.status_code == 400:
                logger.warning("Google OAuth token already revoked or invalid")
            else:
                logger.error(
                    f"Google token revocation failed: {response.status_code}",
                    extra={"status_code": response.status_code},
                )
                response.raise_for_status()

    async def get_user_info(
        self,
        access_token: str,
    ) -> dict[str, Any]:
        """
        Get user information from Google.

        Args:
            access_token: Valid Google access token

        Returns:
            User info with email, name, picture, etc.
        """
        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            response = await client.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code != 200:
                logger.error(
                    f"Google userinfo request failed: {response.status_code}",
                    extra={"status_code": response.status_code},
                )
                response.raise_for_status()

            user_info = response.json()

            logger.debug(
                "Google user info retrieved",
                extra={"email": user_info.get("email")},
            )

            return user_info

    def get_default_scopes(self) -> list[str]:
        """
        Get default Google Workspace scopes.

        Returns scopes for:
        - Gmail (read, send, modify)
        - Calendar (read, write events)
        - User profile (email, basic info)
        """
        return [
            # Gmail
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.send",
            # Calendar
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/calendar.events",
            # Profile
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            # OpenID Connect
            "openid",
        ]

    def get_gmail_scopes(self) -> list[str]:
        """Get Gmail-specific scopes."""
        return [
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.readonly",
        ]

    def get_calendar_scopes(self) -> list[str]:
        """Get Calendar-specific scopes."""
        return [
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar.readonly",
        ]


def generate_pkce_pair() -> tuple[str, str]:
    """
    Generate PKCE code verifier and challenge pair.

    PKCE (Proof Key for Code Exchange) provides additional security
    for OAuth flows, especially for mobile/public clients.

    Returns:
        Tuple of (code_verifier, code_challenge)

    Example:
        >>> verifier, challenge = generate_pkce_pair()
        >>> # Use challenge in authorization URL
        >>> # Use verifier in token exchange
    """
    # Generate 32-byte random verifier (43-128 chars base64url)
    code_verifier = secrets.token_urlsafe(32)

    # Generate S256 challenge: BASE64URL(SHA256(verifier))
    digest = hashlib.sha256(code_verifier.encode()).digest()
    import base64

    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    return code_verifier, code_challenge
