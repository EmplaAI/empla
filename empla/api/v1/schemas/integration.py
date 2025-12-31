"""
empla.api.v1.schemas.integration - Integration API Schemas

Pydantic schemas for OAuth integration management.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Type aliases for constrained values
IntegrationProviderType = Literal["google_workspace", "microsoft_graph"]
IntegrationAuthTypeValue = Literal["user_oauth", "service_account"]
IntegrationStatusValue = Literal["active", "disabled", "revoked"]
CredentialStatusValue = Literal["active", "expired", "revoked", "refreshing", "revocation_failed"]


class IntegrationCreate(BaseModel):
    """Schema for creating a new integration."""

    provider: IntegrationProviderType = Field(
        ...,
        description="Integration provider (google_workspace or microsoft_graph)",
    )
    auth_type: IntegrationAuthTypeValue = Field(
        default="user_oauth",
        description="Authentication type",
    )
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Display name for the integration",
    )
    client_id: str = Field(
        ...,
        min_length=1,
        description="OAuth client ID",
    )
    redirect_uri: str = Field(
        ...,
        description="OAuth redirect URI",
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="OAuth scopes (uses provider defaults if empty)",
    )


class IntegrationResponse(BaseModel):
    """Schema for integration response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    provider: str
    auth_type: str
    display_name: str
    status: str
    enabled_at: datetime | None = None
    enabled_by: UUID | None = None
    created_at: datetime
    updated_at: datetime

    # OAuth config (non-sensitive only)
    oauth_config: dict[str, Any] = Field(
        default_factory=dict,
        description="OAuth configuration (client_id, redirect_uri, scopes)",
    )

    # Computed fields
    credential_count: int = Field(
        default=0,
        description="Number of active credentials for this integration",
    )


class IntegrationListResponse(BaseModel):
    """Schema for list of integrations."""

    items: list[IntegrationResponse]
    total: int


class AuthorizationUrlRequest(BaseModel):
    """Schema for requesting an OAuth authorization URL."""

    employee_id: UUID = Field(
        ...,
        description="Employee to authorize for",
    )
    redirect_after: str | None = Field(
        default=None,
        description="Where to redirect after OAuth callback",
    )
    use_pkce: bool = Field(
        default=True,
        description="Whether to use PKCE for enhanced security",
    )


class AuthorizationUrlResponse(BaseModel):
    """Schema for OAuth authorization URL response."""

    authorization_url: str = Field(
        ...,
        description="URL to redirect user to for OAuth consent",
    )
    state: str = Field(
        ...,
        description="OAuth state parameter (for verification)",
    )
    provider: str = Field(
        ...,
        description="Integration provider",
    )
    employee_id: UUID = Field(
        ...,
        description="Employee being authorized",
    )


class OAuthCallbackResponse(BaseModel):
    """Schema for OAuth callback response."""

    success: bool
    redirect_uri: str = Field(
        ...,
        description="Where to redirect the user",
    )
    credential_id: UUID | None = Field(
        default=None,
        description="Created credential ID (if successful)",
    )
    employee_id: UUID | None = Field(
        default=None,
        description="Employee ID (if successful)",
    )
    error: str | None = Field(
        default=None,
        description="Error message (if failed)",
    )


class ServiceAccountSetup(BaseModel):
    """Schema for setting up service account credentials."""

    employee_id: UUID = Field(
        ...,
        description="Employee to configure for",
    )
    service_account_key: dict[str, Any] = Field(
        ...,
        description="Service account key JSON (from Google/Azure portal)",
    )


class CredentialResponse(BaseModel):
    """Schema for credential response (non-sensitive data only)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    integration_id: UUID
    employee_id: UUID
    credential_type: str
    status: str
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    last_used_at: datetime | None = None

    # Metadata (non-sensitive)
    token_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Non-sensitive credential metadata (email, scopes, etc.)",
    )


class CredentialStatusResponse(BaseModel):
    """Schema for checking credential status."""

    has_credential: bool = Field(
        ...,
        description="Whether the employee has an active credential",
    )
    provider: str = Field(
        ...,
        description="Integration provider",
    )
    employee_id: UUID = Field(
        ...,
        description="Employee ID",
    )
    credential: CredentialResponse | None = Field(
        default=None,
        description="Credential details (if exists)",
    )


class IntegrationUpdate(BaseModel):
    """Schema for updating an integration."""

    display_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    status: IntegrationStatusValue | None = Field(
        default=None,
        description="Integration status",
    )
    scopes: list[str] | None = Field(
        default=None,
        description="Updated OAuth scopes",
    )
