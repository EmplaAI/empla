"""
empla.services.integrations.providers.microsoft - Microsoft Graph OAuth Provider

Implements OAuth 2.0 for Microsoft Graph services:
- Outlook (email)
- Microsoft Calendar
- OneDrive
- Microsoft Teams

Supports both:
- User OAuth (delegated): User grants access via consent screen
- App-only (application): Admin grants tenant-wide access

Reference:
- https://docs.microsoft.com/en-us/graph/auth/
- https://docs.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow
"""

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from empla.services.integrations.providers.base import OAuthProvider

logger = logging.getLogger(__name__)


class MicrosoftGraphProvider(OAuthProvider):
    """
    Microsoft Graph OAuth 2.0 provider.

    Implements the OAuth 2.0 authorization code flow for Microsoft 365/Azure AD.
    Supports both multi-tenant and single-tenant configurations.

    Example:
        >>> provider = MicrosoftGraphProvider()
        >>> auth_url = provider.get_authorization_url(
        ...     client_id="00000000-0000-0000-0000-000000000000",
        ...     redirect_uri="https://app.empla.ai/oauth/callback",
        ...     scopes=["Mail.Read", "Mail.Send"],
        ...     state="random-state",
        ... )
    """

    # OAuth endpoints (using 'common' for multi-tenant)
    # For single tenant, replace 'common' with tenant ID
    AUTHORIZATION_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
    TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    USERINFO_URL = "https://graph.microsoft.com/v1.0/me"

    # Default tenant for multi-tenant apps
    DEFAULT_TENANT = "common"

    # Default timeout for HTTP requests
    TIMEOUT = 30.0

    def __init__(self, tenant: str = "common") -> None:
        """
        Initialize Microsoft Graph provider.

        Args:
            tenant: Azure AD tenant ID or "common" for multi-tenant
        """
        self.tenant = tenant

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
        Generate Microsoft OAuth authorization URL.

        Args:
            client_id: Azure AD application (client) ID
            redirect_uri: Callback URL after authorization
            scopes: List of Microsoft Graph scopes (e.g., "Mail.Read")
            state: CSRF protection state
            code_challenge: PKCE code challenge (optional)
            code_challenge_method: PKCE method (default "S256")

        Returns:
            Authorization URL
        """
        # Microsoft requires offline_access for refresh tokens
        all_scopes = list(scopes)
        if "offline_access" not in all_scopes:
            all_scopes.append("offline_access")

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(all_scopes),
            "state": state,
            "response_type": "code",
            "response_mode": "query",
        }

        # Add PKCE if provided
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method

        url = self.AUTHORIZATION_URL.format(tenant=self.tenant)
        return f"{url}?{urlencode(params)}"

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
            client_id: Azure AD application ID
            client_secret: Azure AD client secret
            redirect_uri: Same redirect URI used in authorization
            code_verifier: PKCE code verifier (if using PKCE)

        Returns:
            Token response with access_token, refresh_token, etc.
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

        url = self.TOKEN_URL.format(tenant=self.tenant)

        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            response = await client.post(url, data=data)

            if response.status_code != 200:
                logger.error(
                    f"Microsoft token exchange failed: {response.status_code} {response.text}",
                    extra={"status_code": response.status_code},
                )
                response.raise_for_status()

            tokens = response.json()

            logger.info(
                "Microsoft OAuth token exchange successful",
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
            refresh_token: Microsoft refresh token
            client_id: Azure AD application ID
            client_secret: Azure AD client secret

        Returns:
            New token response
        """
        data = {
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        }

        url = self.TOKEN_URL.format(tenant=self.tenant)

        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            response = await client.post(url, data=data)

            if response.status_code != 200:
                logger.error(
                    f"Microsoft token refresh failed: {response.status_code} {response.text}",
                    extra={"status_code": response.status_code},
                )
                response.raise_for_status()

            tokens = response.json()

            logger.info(
                "Microsoft OAuth token refresh successful",
                extra={"expires_in": tokens.get("expires_in")},
            )

            return tokens

    async def revoke_token(
        self,
        token: str,
        token_type_hint: str = "access_token",
    ) -> None:
        """
        Revoke a Microsoft OAuth token.

        Note: Microsoft doesn't have a standard token revocation endpoint.
        The best practice is to:
        1. Clear tokens from your storage
        2. Redirect user to logout URL if needed

        Args:
            token: Token to revoke (not used - Microsoft doesn't support)
            token_type_hint: Type hint (not used)
        """
        logger.warning(
            "Microsoft Graph doesn't support token revocation via API. "
            "Token has been removed from storage but may still be valid until expiry."
        )
        # For enterprise scenarios, admins can revoke via Azure AD portal
        # or use the admin consent revocation endpoint

    async def get_user_info(
        self,
        access_token: str,
    ) -> dict[str, Any]:
        """
        Get user information from Microsoft Graph.

        Args:
            access_token: Valid Microsoft access token

        Returns:
            User info with mail, displayName, etc.
        """
        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            response = await client.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code != 200:
                logger.error(
                    f"Microsoft userinfo request failed: {response.status_code}",
                    extra={"status_code": response.status_code},
                )
                response.raise_for_status()

            user_info = response.json()

            # Normalize to common format
            normalized = {
                "email": user_info.get("mail") or user_info.get("userPrincipalName"),
                "name": user_info.get("displayName"),
                "id": user_info.get("id"),
                "given_name": user_info.get("givenName"),
                "family_name": user_info.get("surname"),
                # Keep original data too
                **user_info,
            }

            logger.debug(
                "Microsoft user info retrieved",
                extra={"email": normalized.get("email")},
            )

            return normalized

    def get_default_scopes(self) -> list[str]:
        """
        Get default Microsoft Graph scopes.

        Returns scopes for:
        - Mail (read, send)
        - Calendar (read, write)
        - User profile
        """
        return [
            # Mail
            "Mail.Read",
            "Mail.Send",
            # Calendar
            "Calendars.Read",
            "Calendars.ReadWrite",
            # Profile
            "User.Read",
            # Required for refresh tokens
            "offline_access",
        ]

    def get_mail_scopes(self) -> list[str]:
        """Get Mail-specific scopes."""
        return [
            "Mail.Read",
            "Mail.ReadWrite",
            "Mail.Send",
            "offline_access",
        ]

    def get_calendar_scopes(self) -> list[str]:
        """Get Calendar-specific scopes."""
        return [
            "Calendars.Read",
            "Calendars.ReadWrite",
            "offline_access",
        ]
