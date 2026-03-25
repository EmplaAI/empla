"""
empla.api.v1.endpoints.auth - Authentication Endpoints

JWT-based authentication using HS256. Tokens contain user_id, tenant_id,
and role claims with configurable expiry (default 24h).
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select

from empla.api.deps import CurrentUser, DBSession
from empla.models.tenant import Tenant, User
from empla.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


class LoginRequest(BaseModel):
    """Login request schema."""

    email: EmailStr
    tenant_slug: str


class LoginResponse(BaseModel):
    """Login response with token."""

    model_config = ConfigDict(populate_by_name=True)

    token: str
    user_id: UUID = Field(serialization_alias="userId")
    tenant_id: UUID = Field(serialization_alias="tenantId")
    user_name: str = Field(serialization_alias="userName")
    tenant_name: str = Field(serialization_alias="tenantName")
    role: str


def create_access_token(user_id: UUID, tenant_id: UUID, role: str) -> str:
    """Create a signed JWT access token.

    Args:
        user_id: User UUID to encode in the token.
        tenant_id: Tenant UUID to encode in the token.
        role: User role (e.g. "admin", "member").

    Returns:
        Encoded JWT string.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expiry_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@router.post("/login", response_model=LoginResponse, response_model_by_alias=True)
async def login(
    db: DBSession,
    data: LoginRequest,
) -> LoginResponse:
    """
    Login and get a JWT authentication token.

    Args:
        db: Database session
        data: Login credentials (email + tenant slug)

    Returns:
        JWT token and user info

    Raises:
        HTTPException: If credentials are invalid
    """
    # Find tenant by slug
    tenant_result = await db.execute(
        select(Tenant).where(
            Tenant.slug == data.tenant_slug,
            Tenant.deleted_at.is_(None),
        )
    )
    tenant: Tenant | None = tenant_result.scalar_one_or_none()

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant",
        )

    if tenant.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is not active",
        )

    # Find user by email within tenant
    user_result = await db.execute(
        select(User).where(
            User.tenant_id == tenant.id,
            User.email == data.email,
            User.deleted_at.is_(None),
        )
    )
    user: User | None = user_result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_access_token(user.id, tenant.id, user.role)

    logger.info(
        "User logged in",
        extra={"user_id": str(user.id), "tenant_id": str(tenant.id)},
    )

    return LoginResponse(
        token=token,
        user_id=user.id,
        tenant_id=tenant.id,
        user_name=user.name,
        tenant_name=tenant.name,
        role=user.role,
    )


@router.get("/me", response_model=LoginResponse, response_model_by_alias=True)
async def get_current_user_info(
    auth: CurrentUser,
) -> LoginResponse:
    """
    Get current user info from JWT token.

    Uses the shared get_current_user dependency for token validation.

    Args:
        auth: Authenticated user context (injected by FastAPI)

    Returns:
        Current user info (token field is empty since the caller already has it)
    """
    return LoginResponse(
        token="",  # Don't echo the token back
        user_id=auth.user_id,
        tenant_id=auth.tenant_id,
        user_name=auth.user.name,
        tenant_name=auth.tenant.name,
        role=auth.user.role,
    )
