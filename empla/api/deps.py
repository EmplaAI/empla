"""
empla.api.deps - FastAPI Dependencies

Provides reusable dependencies for API endpoints:
- get_db: Database session
- get_current_user: JWT authentication (returns AuthContext with user and tenant)
"""

import logging
from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.tenant import Tenant, User

logger = logging.getLogger(__name__)

# Security scheme for JWT bearer tokens
security = HTTPBearer(auto_error=False)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session from app state.

    Yields:
        AsyncSession for database operations

    Raises:
        HTTPException: If database is not initialized
    """
    sessionmaker = getattr(request.app.state, "sessionmaker", None)
    if sessionmaker is None:
        logger.error("Database not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available",
        )

    async with sessionmaker() as session:
        yield session


# Type alias for database dependency
DBSession = Annotated[AsyncSession, Depends(get_db)]


class AuthContext:
    """
    Authentication context containing current user and tenant.

    Attributes:
        user: Current authenticated user
        tenant: Tenant the user belongs to
        tenant_id: UUID of the tenant (shortcut)
        user_id: UUID of the user (shortcut)
    """

    def __init__(self, user: User, tenant: Tenant) -> None:
        self.user = user
        self.tenant = tenant
        self.tenant_id = tenant.id
        self.user_id = user.id


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: DBSession,
) -> AuthContext:
    """
    Get the current authenticated user from JWT token.

    For now, this is a stub that accepts any token in format:
    "Bearer <user_id>:<tenant_id>"

    In production, this should validate a proper JWT token.

    Args:
        credentials: Bearer token from Authorization header
        db: Database session

    Returns:
        AuthContext with current user and tenant

    Raises:
        HTTPException: If authentication fails
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # ==========================================================================
    # SECURITY WARNING: Development-only stub implementation
    # ==========================================================================
    # Token format "user_id:tenant_id" provides NO cryptographic security.
    # This is for development/testing ONLY.
    #
    # TODO(security): Before production deployment:
    # - Implement proper JWT validation with signature verification
    # - Add token expiration checking
    # - Add rate limiting for auth endpoints
    # - See docs/decisions/XXX-authentication.md for planned implementation
    # ==========================================================================
    try:
        parts = token.split(":")
        if len(parts) != 2:
            raise ValueError("Invalid token format")

        user_id = UUID(parts[0])
        tenant_id = UUID(parts[1])
    except (ValueError, IndexError) as e:
        logger.warning(f"Invalid token format: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    # Fetch user and tenant from database
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or invalid tenant",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch tenant separately (User model doesn't define tenant relationship)
    tenant_result = await db.execute(
        select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.deleted_at.is_(None),
        )
    )
    tenant: Tenant | None = tenant_result.scalar_one_or_none()

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if tenant.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is not active",
        )

    return AuthContext(user=user, tenant=tenant)


# Type alias for auth dependency
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


async def require_admin(auth: CurrentUser) -> AuthContext:
    """
    Require the current user to be an admin.

    Args:
        auth: Current authentication context

    Returns:
        AuthContext if user is admin

    Raises:
        HTTPException: If user is not an admin
    """
    if auth.user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return auth


# Type alias for admin dependency
RequireAdmin = Annotated[AuthContext, Depends(require_admin)]
