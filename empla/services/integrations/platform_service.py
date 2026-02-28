"""
empla.services.integrations.platform_service - Platform OAuth App Service

CRUD operations for platform-level OAuth apps.
These are global (not tenant-scoped) OAuth app registrations that tenants
can opt into instead of providing their own OAuth credentials.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.integration import PlatformOAuthApp
from empla.services.integrations.token_manager import TokenManager

logger = logging.getLogger(__name__)


class PlatformOAuthAppService:
    """Manages platform-level OAuth app registrations."""

    def __init__(self, session: AsyncSession, token_manager: TokenManager) -> None:
        self.session = session
        self.token_manager = token_manager

    async def get_app(self, provider: str) -> PlatformOAuthApp | None:
        """Get the platform OAuth app for a provider (active only)."""
        result = await self.session.execute(
            select(PlatformOAuthApp).where(
                PlatformOAuthApp.provider == provider,
                PlatformOAuthApp.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def list_apps(self) -> list[PlatformOAuthApp]:
        """List all platform OAuth apps."""
        result = await self.session.execute(
            select(PlatformOAuthApp).order_by(PlatformOAuthApp.provider)
        )
        return list(result.scalars().all())

    async def create_app(
        self,
        *,
        provider: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str],
    ) -> PlatformOAuthApp:
        """Create a platform OAuth app with encrypted client secret."""
        encrypted, key_id = self.token_manager.encrypt({"client_secret": client_secret})

        app = PlatformOAuthApp(
            provider=provider,
            client_id=client_id,
            encrypted_client_secret=encrypted,
            encryption_key_id=key_id,
            redirect_uri=redirect_uri,
            default_scopes=scopes,
            status="active",
        )
        self.session.add(app)
        await self.session.commit()
        await self.session.refresh(app)

        logger.info(
            "Created platform OAuth app",
            extra={"provider": provider, "app_id": str(app.id)},
        )
        return app

    async def delete_app(self, provider: str) -> None:
        """Delete (hard-delete) an active platform OAuth app by provider.

        Only deletes apps with status='active'. Returns without error if
        no active app is found (a warning is logged).
        """
        app = await self.get_app(provider)
        if not app:
            logger.warning(
                "Attempted to delete platform OAuth app that does not exist",
                extra={"provider": provider},
            )
            return
        await self.session.delete(app)
        await self.session.commit()
        logger.info(
            "Deleted platform OAuth app",
            extra={"provider": provider, "app_id": str(app.id)},
        )

    def decrypt_client_secret(self, app: PlatformOAuthApp) -> str:
        """Decrypt the client secret for a platform OAuth app."""
        data = self.token_manager.decrypt(app.encrypted_client_secret, app.encryption_key_id)
        secret = data.get("client_secret")
        if not secret:
            logger.error(
                "Decrypted platform OAuth app payload missing 'client_secret' key",
                extra={"app_id": str(app.id), "provider": app.provider},
            )
            raise ValueError(f"Platform OAuth app for {app.provider} has corrupted secret data")
        return secret
