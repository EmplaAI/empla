"""
empla.models.integration - Integration & OAuth Models

Models for managing third-party integrations and OAuth credentials:
- Integration: Tenant-level provider configuration (Google, Microsoft)
- IntegrationCredential: Employee-level encrypted tokens
- IntegrationOAuthState: Temporary OAuth state for CSRF protection

These models support both User OAuth (consent flow) and Service Account
authentication, with application-level encryption for sensitive data.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID
from uuid import uuid4 as _uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from empla.models.base import Base, TenantScopedModel, TimestampedModel

if TYPE_CHECKING:
    from empla.models.employee import Employee
    from empla.models.tenant import User


class IntegrationProvider(str, Enum):
    """Supported integration providers."""

    GOOGLE_WORKSPACE = "google_workspace"
    MICROSOFT_GRAPH = "microsoft_graph"


class IntegrationAuthType(str, Enum):
    """Authentication type for integrations."""

    USER_OAUTH = "user_oauth"  # User consent flow (OAuth 2.0)
    SERVICE_ACCOUNT = "service_account"  # Service account (Google) / App-only (Microsoft)


class IntegrationStatus(str, Enum):
    """Integration status."""

    ACTIVE = "active"
    DISABLED = "disabled"
    REVOKED = "revoked"


class CredentialStatus(str, Enum):
    """
    Credential status.

    State transitions:
    - ACTIVE -> EXPIRED (token expiry)
    - ACTIVE -> REVOKED (user/admin action, provider revocation succeeded)
    - ACTIVE -> REVOCATION_FAILED (user/admin action, provider revocation failed)
    - ACTIVE -> REFRESHING (refresh in progress)
    - REFRESHING -> ACTIVE (refresh succeeded)
    - REFRESHING -> EXPIRED (refresh failed)
    - REVOCATION_FAILED -> REVOKED (manual cleanup after retry)
    """

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    REFRESHING = "refreshing"
    REVOCATION_FAILED = "revocation_failed"  # Provider revocation failed - token may still be valid


class CredentialType(str, Enum):
    """Credential type."""

    OAUTH_TOKENS = "oauth_tokens"
    SERVICE_ACCOUNT_KEY = "service_account_key"


class Integration(TenantScopedModel):
    """
    Tenant-level integration configuration for external providers.

    Stores OAuth app configuration (client_id, redirect URIs, scopes) but NOT
    secrets. Client secrets are resolved from environment variables (tenant
    credentials) or from encrypted ``PlatformOAuthApp`` rows when
    ``use_platform_credentials`` is True.

    Example:
        >>> integration = Integration(
        ...     tenant_id=tenant.id,
        ...     provider="google_workspace",
        ...     auth_type="user_oauth",
        ...     display_name="Google Workspace",
        ...     oauth_config={
        ...         "client_id": "...",
        ...         "redirect_uri": "https://app.empla.ai/oauth/callback",
        ...         "scopes": ["https://www.googleapis.com/auth/gmail.modify"]
        ...     }
        ... )
    """

    __tablename__ = "integrations"

    # Identity
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Provider (google_workspace, microsoft_graph)",
    )

    auth_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Auth type (user_oauth, service_account)",
    )

    display_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Human-readable name for this integration",
    )

    # OAuth Configuration (non-secret)
    oauth_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="OAuth config (client_id, redirect_uri, scopes) - NO secrets",
    )

    # Platform credential delegation
    use_platform_credentials: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        comment="If true, use platform-level OAuth app instead of tenant-provided credentials",
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'active'"),
        comment="Integration status (active, disabled, revoked)",
    )

    # Audit
    enabled_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        comment="User who enabled this integration",
    )

    enabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When integration was enabled",
    )

    # Relationships
    enabler: Mapped["User | None"] = relationship("User", foreign_keys=[enabled_by])
    credentials: Mapped[list["IntegrationCredential"]] = relationship(
        "IntegrationCredential",
        back_populates="integration",
        cascade="all, delete-orphan",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "provider IN ('google_workspace', 'microsoft_graph')",
            name="ck_integrations_provider",
        ),
        CheckConstraint(
            "auth_type IN ('user_oauth', 'service_account')",
            name="ck_integrations_auth_type",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled', 'revoked')",
            name="ck_integrations_status",
        ),
        Index(
            "idx_integrations_tenant_provider",
            "tenant_id",
            "provider",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_integrations_tenant",
            "tenant_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_integrations_status",
            "tenant_id",
            "status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Integration(id={self.id}, provider={self.provider}, auth_type={self.auth_type})>"


class IntegrationCredential(TenantScopedModel):
    """
    Employee-level encrypted credentials for integrations.

    Stores encrypted OAuth tokens (access_token, refresh_token) or service
    account keys. All sensitive data is encrypted at rest using Fernet (AES-128-CBC).

    The encryption_key_id tracks which key was used, enabling key rotation
    without re-encrypting all credentials at once.

    Example:
        >>> credential = IntegrationCredential(
        ...     tenant_id=tenant.id,
        ...     integration_id=integration.id,
        ...     employee_id=employee.id,
        ...     credential_type="oauth_tokens",
        ...     encrypted_data=encrypt({"access_token": "...", "refresh_token": "..."}),
        ...     encryption_key_id="key_v1",
        ...     token_metadata={"email": "employee@company.com", "scopes": [...]},
        ...     expires_at=datetime.now(UTC) + timedelta(hours=1)
        ... )
    """

    __tablename__ = "integration_credentials"

    # References
    integration_id: Mapped[UUID] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Integration this credential belongs to",
    )

    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Employee this credential belongs to",
    )

    # Credential type and encrypted data
    credential_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Type (oauth_tokens, service_account_key)",
    )

    encrypted_data: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
        comment="Fernet-encrypted credential JSON",
    )

    encryption_key_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="ID of encryption key used (for rotation)",
    )

    # Non-sensitive metadata (for management/display)
    token_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Non-sensitive metadata (email, scopes)",
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'active'"),
        comment="Credential status (active, expired, revoked, refreshing)",
    )

    # Timing
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When token was issued",
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When token expires (NULL for service accounts)",
    )

    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When token was last refreshed",
    )

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When credential was last used",
    )

    # Relationships
    integration: Mapped["Integration"] = relationship(
        "Integration",
        back_populates="credentials",
    )
    employee: Mapped["Employee"] = relationship(
        "Employee",
        backref="integration_credentials",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "credential_type IN ('oauth_tokens', 'service_account_key')",
            name="ck_credentials_credential_type",
        ),
        CheckConstraint(
            "status IN ('active', 'expired', 'revoked', 'refreshing', 'revocation_failed')",
            name="ck_credentials_status",
        ),
        Index(
            "idx_credentials_employee_integration",
            "employee_id",
            "integration_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_credentials_expires",
            "expires_at",
            postgresql_where=text("deleted_at IS NULL AND status = 'active'"),
        ),
        Index(
            "idx_credentials_tenant",
            "tenant_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_credentials_status",
            "tenant_id",
            "status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<IntegrationCredential(id={self.id}, employee_id={self.employee_id}, type={self.credential_type})>"


class IntegrationOAuthState(TenantScopedModel):
    """
    Temporary OAuth state for authorization flow (CSRF protection).

    Short-lived records that track in-progress OAuth flows. The state parameter
    is a cryptographically random string that must match between the authorization
    request and callback.

    States expire after 10 minutes and should be deleted after successful callback.

    Example:
        >>> oauth_state = IntegrationOAuthState(
        ...     tenant_id=tenant.id,
        ...     state=secrets.token_urlsafe(32),
        ...     integration_id=integration.id,
        ...     employee_id=employee.id,
        ...     initiated_by=user.id,
        ...     redirect_uri="/dashboard/integrations",
        ...     expires_at=datetime.now(UTC) + timedelta(minutes=10)
        ... )
    """

    __tablename__ = "integration_oauth_states"

    # State token (unguessable)
    state: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment="OAuth state parameter (CSRF token)",
    )

    # References
    integration_id: Mapped[UUID] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        comment="Integration being authorized",
    )

    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        comment="Employee being authorized for",
    )

    initiated_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        comment="User who initiated the flow",
    )

    # Redirect info
    redirect_uri: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Where to redirect after callback",
    )

    # PKCE code verifier (for enhanced security)
    code_verifier: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="PKCE code verifier (stored temporarily)",
    )

    # Expiry
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="State expires after 10 minutes",
    )

    # Relationships
    integration: Mapped["Integration"] = relationship("Integration")
    employee: Mapped["Employee"] = relationship("Employee")
    initiator: Mapped["User"] = relationship("User")

    # Constraints
    __table_args__ = (
        Index(
            "idx_oauth_state_state",
            "state",
            unique=True,
        ),
        Index(
            "idx_oauth_state_expires",
            "expires_at",
        ),
        Index(
            "idx_oauth_state_tenant",
            "tenant_id",
        ),
    )

    def __repr__(self) -> str:
        return f"<IntegrationOAuthState(id={self.id}, state={self.state[:8]}...)>"


class PlatformOAuthApp(TimestampedModel, Base):
    """
    Platform-level OAuth app registration.

    NOT tenant-scoped — these are global OAuth apps managed by the platform
    admin. Tenants can opt-in to use platform credentials instead of providing
    their own via ``Integration.use_platform_credentials``.

    Client secrets are Fernet-encrypted at rest (same key provider as
    IntegrationCredential).
    """

    __tablename__ = "platform_oauth_apps"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=_uuid4,
        comment="Unique identifier",
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="Provider key (google_workspace, microsoft_graph, …)",
    )

    client_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="OAuth client ID",
    )

    encrypted_client_secret: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
        comment="Fernet-encrypted OAuth client secret",
    )

    encryption_key_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="ID of encryption key used (for rotation)",
    )

    redirect_uri: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="OAuth redirect URI for this platform app",
    )

    default_scopes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        comment="Default OAuth scopes",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'active'"),
        comment="App status (active, disabled)",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_platform_oauth_apps_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<PlatformOAuthApp(id={self.id}, provider={self.provider})>"
