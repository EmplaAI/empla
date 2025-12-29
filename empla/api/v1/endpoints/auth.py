"""
empla.api.v1.endpoints.auth - Authentication Endpoints

Stub authentication for development.
In production, replace with proper JWT authentication.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select

from empla.api.deps import DBSession
from empla.models.tenant import Tenant, User

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


class TokenInfo(BaseModel):
    """Token introspection response."""

    valid: bool
    user_id: UUID | None = None
    tenant_id: UUID | None = None
    role: str | None = None


@router.post("/login", response_model=LoginResponse, response_model_by_alias=True)
async def login(
    db: DBSession,
    data: LoginRequest,
) -> LoginResponse:
    """
    Login and get an authentication token.

    This is a stub implementation for development.
    In production, this should validate password/OAuth/SAML.

    Args:
        db: Database session
        data: Login credentials

    Returns:
        Authentication token

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

    # Generate stub token (user_id:tenant_id)
    # TODO: Replace with proper JWT
    token = f"{user.id}:{tenant.id}"

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
    db: DBSession,
    authorization: str = Header(..., alias="Authorization"),
) -> LoginResponse:
    """
    Get current user info from token.

    Args:
        db: Database session
        authorization: Authorization header (Bearer token)

    Returns:
        Current user info

    Raises:
        HTTPException: If token is invalid
    """
    # Extract token from "Bearer <token>" format
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:]  # Remove "Bearer " prefix

    try:
        parts = token.split(":")
        if len(parts) != 2:
            raise ValueError("Invalid format")

        user_id = UUID(parts[0])
        tenant_id = UUID(parts[1])
    except (ValueError, IndexError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from e

    # Fetch user
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    # Fetch tenant
    result = await db.execute(
        select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.deleted_at.is_(None),
        )
    )
    tenant = result.scalar_one_or_none()

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    return LoginResponse(
        token=token,
        user_id=user.id,
        tenant_id=tenant.id,
        user_name=user.name,
        tenant_name=tenant.name,
        role=user.role,
    )
