"""
empla.api.v1.endpoints.integrations - Integration Management Endpoints

REST API endpoints for OAuth integration management:
- Provider catalog and simplified connect flow
- Create/list/delete integrations (admin operations)
- OAuth authorization flow (authorize, callback)
- Service account setup
- Credential status checking
- Platform OAuth app management (admin)
"""

import logging
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from empla.api.deps import CurrentUser, DBSession, RequireAdmin
from empla.api.ratelimit import (
    RateLimitExceeded,
    get_client_identifier,
    oauth_callback_limiter,
)
from empla.api.v1.schemas.integration import (
    AuthorizationUrlRequest,
    AuthorizationUrlResponse,
    ConnectRequest,
    ConnectResponse,
    CredentialListItem,
    CredentialListResponse,
    CredentialResponse,
    CredentialStatusResponse,
    IntegrationCreate,
    IntegrationListResponse,
    IntegrationResponse,
    IntegrationUpdate,
    PlatformOAuthAppCreate,
    PlatformOAuthAppResponse,
    ProviderInfo,
    ProviderListResponse,
    ServiceAccountSetup,
)
from empla.models.employee import Employee
from empla.models.integration import (
    Integration,
    IntegrationAuthType,
    IntegrationCredential,
    IntegrationProvider,
)
from empla.services.integrations import (
    ClientSecretNotConfiguredError,
    DecryptionError,
    IntegrationService,
    InvalidStateError,
    OAuthService,
    PlatformOAuthAppService,
    RevocationError,
    TokenExchangeError,
    get_token_manager,
)
from empla.services.integrations.catalog import PROVIDER_CATALOG
from empla.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_integration_service(db: DBSession) -> IntegrationService:
    """Get integration service instance."""
    token_manager = get_token_manager()
    return IntegrationService(db, token_manager)


def _get_oauth_service(db: DBSession) -> OAuthService:
    """Get OAuth service instance."""
    token_manager = get_token_manager()
    return OAuthService(db, token_manager)


def _get_platform_service(db: DBSession) -> PlatformOAuthAppService:
    """Get platform OAuth app service instance."""
    token_manager = get_token_manager()
    return PlatformOAuthAppService(db, token_manager)


@router.get("", response_model=IntegrationListResponse)
async def list_integrations(
    db: DBSession,
    auth: CurrentUser,
) -> IntegrationListResponse:
    """
    List all integrations for the current tenant.

    Returns:
        List of integrations with credential counts
    """
    service = _get_integration_service(db)
    integrations = await service.list_integrations(auth.tenant_id)

    # Get credential counts for each integration
    items = []
    for integration in integrations:
        # Count active credentials
        count_result = await db.execute(
            select(func.count())
            .select_from(IntegrationCredential)
            .where(
                IntegrationCredential.integration_id == integration.id,
                IntegrationCredential.status == "active",
                IntegrationCredential.deleted_at.is_(None),
            )
        )
        credential_count = count_result.scalar() or 0

        response = IntegrationResponse.model_validate(integration)
        response.credential_count = credential_count
        items.append(response)

    return IntegrationListResponse(
        items=items,
        total=len(items),
    )


@router.post("", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
async def create_integration(
    db: DBSession,
    auth: RequireAdmin,
    data: IntegrationCreate,
) -> IntegrationResponse:
    """
    Create a new integration for the tenant.

    Requires admin access.

    Args:
        data: Integration configuration

    Returns:
        Created integration

    Raises:
        HTTPException: If integration for provider already exists
    """
    service = _get_integration_service(db)

    # Check if integration already exists for this provider
    existing = await service.get_integration(
        auth.tenant_id,
        IntegrationProvider(data.provider),
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Integration for {data.provider} already exists",
        )

    # Build OAuth config
    oauth_config = {
        "client_id": data.client_id,
        "redirect_uri": data.redirect_uri,
        "scopes": data.scopes if data.scopes else None,  # None = use defaults
    }

    # Create integration
    integration = await service.create_integration(
        tenant_id=auth.tenant_id,
        provider=IntegrationProvider(data.provider),
        auth_type=IntegrationAuthType(data.auth_type),
        display_name=data.display_name,
        oauth_config=oauth_config,
        enabled_by=auth.user_id,
    )

    logger.info(
        f"Created integration {integration.id} for provider {data.provider}",
        extra={
            "integration_id": str(integration.id),
            "tenant_id": str(auth.tenant_id),
            "provider": data.provider,
        },
    )

    return IntegrationResponse.model_validate(integration)


# =============================================================================
# Static routes (MUST be registered before /{integration_id} dynamic route)
# =============================================================================


@router.get("/providers", response_model=ProviderListResponse)
async def list_providers(
    db: DBSession,
    auth: CurrentUser,
) -> ProviderListResponse:
    """List available integration providers from the catalog.

    Checks each provider's availability (platform app exists or tenant integration exists).
    """
    platform_svc = _get_platform_service(db)
    platform_apps = await platform_svc.list_apps()
    platform_providers = {app.provider for app in platform_apps}

    # Get tenant integrations
    result = await db.execute(
        select(Integration).where(
            Integration.tenant_id == auth.tenant_id,
            Integration.deleted_at.is_(None),
        )
    )
    tenant_integrations = {i.provider: i for i in result.scalars().all()}

    items: list[ProviderInfo] = []
    for provider_key, meta in PROVIDER_CATALOG.items():
        integration = tenant_integrations.get(provider_key)
        has_platform = provider_key in platform_providers
        has_tenant = integration is not None

        # Count connected employees
        connected = 0
        integration_id = None
        if integration:
            integration_id = integration.id
            count_result = await db.execute(
                select(func.count())
                .select_from(IntegrationCredential)
                .where(
                    IntegrationCredential.integration_id == integration.id,
                    IntegrationCredential.status == "active",
                    IntegrationCredential.deleted_at.is_(None),
                )
            )
            connected = count_result.scalar() or 0

        if integration is not None and not integration.use_platform_credentials:
            source = "tenant"
        elif has_platform:
            source = "platform"
        else:
            source = None

        # Available when credentials can actually be resolved:
        #  - Tenant owns an integration with its own creds (not delegated to platform), OR
        #  - A platform OAuth app exists for this provider
        available = (
            has_tenant and not (integration and integration.use_platform_credentials)
        ) or has_platform

        items.append(
            ProviderInfo(
                provider=provider_key,
                display_name=meta.display_name,
                description=meta.description,
                icon=meta.icon,
                available=available,
                source=source,
                integration_id=integration_id,
                connected_employees=connected,
            )
        )

    return ProviderListResponse(items=items)


@router.post("/connect", response_model=ConnectResponse)
async def connect_provider(
    db: DBSession,
    auth: CurrentUser,
    data: ConnectRequest,
) -> ConnectResponse:
    """Simplified connect flow for employees.

    If the tenant already has an integration for the provider, uses it.
    Otherwise, if a platform OAuth app exists, auto-creates a tenant
    integration with ``use_platform_credentials=True``. Returns an
    authorization URL for the OAuth consent screen.

    Raises 404 if the employee is not found or terminated, 400 if no
    credentials are available for the provider.
    """
    # Validate employee belongs to tenant and is not terminated
    emp_result = await db.execute(
        select(Employee).where(
            Employee.id == data.employee_id,
            Employee.tenant_id == auth.tenant_id,
            Employee.status != "terminated",
            Employee.deleted_at.is_(None),
        )
    )
    if not emp_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    service = _get_integration_service(db)
    oauth_service = _get_oauth_service(db)
    platform_svc = _get_platform_service(db)

    # Check if Integration exists for tenant+provider
    existing = await service.get_integration(auth.tenant_id, data.provider)

    if existing:
        integration = existing
    else:
        # Check if PlatformOAuthApp exists
        platform_app = await platform_svc.get_app(data.provider)
        if not platform_app:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No credentials available for provider '{data.provider}'. "
                "Ask your admin to configure an integration or contact the platform.",
            )

        # Auto-create Integration with use_platform_credentials=True
        meta = PROVIDER_CATALOG.get(data.provider)
        display_name = meta.display_name if meta else data.provider
        integration = await service.create_integration(
            tenant_id=auth.tenant_id,
            provider=data.provider,
            auth_type=IntegrationAuthType.USER_OAUTH,
            display_name=display_name,
            oauth_config={},  # platform creds used instead
            enabled_by=auth.user_id,
            use_platform_credentials=True,
        )
        logger.info(
            "Auto-created integration with platform credentials",
            extra={
                "integration_id": str(integration.id),
                "tenant_id": str(auth.tenant_id),
                "provider": data.provider,
            },
        )

    try:
        auth_url, state_val = await oauth_service.generate_authorization_url(
            integration=integration,
            employee_id=data.employee_id,
            user_id=auth.user_id,
            redirect_after=data.redirect_after,
        )
    except ClientSecretNotConfiguredError as e:
        logger.exception(
            "Connect failed: OAuth credentials not configured",
            extra={"provider": data.provider, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth credentials not configured for {data.provider}. "
            "Contact your administrator.",
        ) from e
    except DecryptionError as e:
        logger.exception("Connect failed: platform credential decryption error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Platform OAuth configuration error. Contact support.",
        ) from e

    return ConnectResponse(
        authorization_url=auth_url,
        state=state_val,
        provider=data.provider,
        employee_id=data.employee_id,
        integration_id=integration.id,
    )


@router.get("/credentials", response_model=CredentialListResponse)
async def list_credentials(
    db: DBSession,
    auth: CurrentUser,
) -> CredentialListResponse:
    """List all credentials for the current tenant across integrations."""
    result = await db.execute(
        select(IntegrationCredential, Integration.provider, Employee.name)
        .join(Integration, IntegrationCredential.integration_id == Integration.id)
        .outerjoin(Employee, IntegrationCredential.employee_id == Employee.id)
        .where(
            IntegrationCredential.tenant_id == auth.tenant_id,
            IntegrationCredential.deleted_at.is_(None),
        )
        .order_by(IntegrationCredential.created_at.desc())
    )

    items: list[CredentialListItem] = []
    for cred, provider, employee_name in result.all():
        item = CredentialListItem(
            id=cred.id,
            integration_id=cred.integration_id,
            employee_id=cred.employee_id,
            employee_name=employee_name or "Unknown employee",
            provider=provider,
            credential_type=cred.credential_type,
            status=cred.status,
            issued_at=cred.issued_at,
            expires_at=cred.expires_at,
            last_refreshed_at=cred.last_refreshed_at,
            last_used_at=cred.last_used_at,
            token_metadata=cred.token_metadata or {},
        )
        items.append(item)

    return CredentialListResponse(items=items, total=len(items))


@router.get("/callback")
async def oauth_callback(
    request: Request,
    db: DBSession,
    state: str = Query(..., description="OAuth state parameter"),
    code: str = Query(default=None, description="Authorization code"),
    error: str = Query(default=None, description="OAuth error"),
    error_description: str = Query(default=None, description="OAuth error description"),
) -> RedirectResponse:
    """Handle OAuth callback from provider.

    Returns a 302 redirect to the frontend instead of JSON.
    """
    settings = get_settings()
    base = settings.frontend_base_url.rstrip("/")

    # Rate limit check
    client_id = get_client_identifier(request)
    if not oauth_callback_limiter.is_allowed(client_id):
        reset_time = int(oauth_callback_limiter.get_reset_time(client_id))
        raise RateLimitExceeded(
            retry_after=reset_time,
            detail="Too many OAuth callback requests. Please try again later.",
        )

    # Handle OAuth error from provider
    if error:
        logger.warning(
            "OAuth error from provider",
            extra={"error": error, "error_description": error_description},
        )
        return RedirectResponse(
            url=f"{base}/integrations/callback?error=oauth_denied",
            status_code=302,
        )

    if not code:
        return RedirectResponse(
            url=f"{base}/integrations/callback?error=missing_code",
            status_code=302,
        )

    oauth_service = _get_oauth_service(db)

    try:
        credential, _redirect_uri = await oauth_service.handle_callback(
            state=state,
            code=code,
        )

        # Look up provider from the integration
        integration = await db.get(Integration, credential.integration_id)
        provider = integration.provider if integration else "unknown"

        logger.info(
            f"OAuth callback successful for employee {credential.employee_id}",
            extra={
                "credential_id": str(credential.id),
                "employee_id": str(credential.employee_id),
            },
        )

        params = urlencode(
            {
                "success": "true",
                "provider": provider,
                "employee_id": str(credential.employee_id),
            }
        )
        return RedirectResponse(
            url=f"{base}/integrations/callback?{params}",
            status_code=302,
        )

    except InvalidStateError:
        return RedirectResponse(
            url=f"{base}/integrations/callback?error=invalid_state",
            status_code=302,
        )

    except TokenExchangeError:
        return RedirectResponse(
            url=f"{base}/integrations/callback?error=token_exchange",
            status_code=302,
        )

    except ClientSecretNotConfiguredError:
        logger.exception("OAuth callback failed: client secret not configured")
        return RedirectResponse(
            url=f"{base}/integrations/callback?error=config_missing",
            status_code=302,
        )

    except DecryptionError:
        logger.exception("OAuth callback failed: credential decryption error")
        return RedirectResponse(
            url=f"{base}/integrations/callback?error=internal",
            status_code=302,
        )

    except Exception:
        logger.exception("Unexpected error in OAuth callback")
        return RedirectResponse(
            url=f"{base}/integrations/callback?error=unknown",
            status_code=302,
        )


# =============================================================================
# Platform OAuth App Endpoints (admin)
# =============================================================================


@router.get("/platform-apps", response_model=list[PlatformOAuthAppResponse])
async def list_platform_apps(
    db: DBSession,
    auth: RequireAdmin,  # noqa: ARG001 — enforces admin via DI
) -> list[PlatformOAuthAppResponse]:
    """List all platform OAuth apps (admin only)."""
    svc = _get_platform_service(db)
    apps = await svc.list_apps()
    return [PlatformOAuthAppResponse.model_validate(app) for app in apps]


@router.post(
    "/platform-apps",
    response_model=PlatformOAuthAppResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_platform_app(
    db: DBSession,
    auth: RequireAdmin,  # noqa: ARG001 — enforces admin via DI
    data: PlatformOAuthAppCreate,
) -> PlatformOAuthAppResponse:
    """Register a platform OAuth app (admin only)."""
    svc = _get_platform_service(db)

    # Check for existing
    existing = await svc.get_app(data.provider)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Platform OAuth app for '{data.provider}' already exists",
        )

    try:
        app = await svc.create_app(
            provider=data.provider,
            client_id=data.client_id,
            client_secret=data.client_secret.get_secret_value(),
            redirect_uri=data.redirect_uri,
            scopes=data.scopes,
        )
    except IntegrityError:
        # Race condition: another request created the app between our check and insert
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Platform OAuth app for '{data.provider}' already exists",
        ) from None

    logger.info(
        "Created platform OAuth app",
        extra={"provider": data.provider, "app_id": str(app.id)},
    )
    return PlatformOAuthAppResponse.model_validate(app)


# =============================================================================
# Integration CRUD (dynamic routes below)
# =============================================================================


@router.get("/{integration_id}", response_model=IntegrationResponse)
async def get_integration(
    db: DBSession,
    auth: CurrentUser,
    integration_id: UUID,
) -> IntegrationResponse:
    """
    Get a specific integration by ID.

    Args:
        integration_id: Integration UUID

    Returns:
        Integration details

    Raises:
        HTTPException: If integration not found
    """
    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.tenant_id == auth.tenant_id,
            Integration.deleted_at.is_(None),
        )
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    # Get credential count
    count_result = await db.execute(
        select(func.count())
        .select_from(IntegrationCredential)
        .where(
            IntegrationCredential.integration_id == integration.id,
            IntegrationCredential.status == "active",
            IntegrationCredential.deleted_at.is_(None),
        )
    )
    credential_count = count_result.scalar() or 0

    response = IntegrationResponse.model_validate(integration)
    response.credential_count = credential_count

    return response


@router.put("/{integration_id}", response_model=IntegrationResponse)
async def update_integration(
    db: DBSession,
    auth: RequireAdmin,
    integration_id: UUID,
    data: IntegrationUpdate,
) -> IntegrationResponse:
    """
    Update an integration.

    Requires admin access.

    Args:
        integration_id: Integration UUID
        data: Update data

    Returns:
        Updated integration

    Raises:
        HTTPException: If integration not found
    """
    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.tenant_id == auth.tenant_id,
            Integration.deleted_at.is_(None),
        )
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    # Apply updates
    if data.display_name is not None:
        integration.display_name = data.display_name
    if data.status is not None:
        integration.status = data.status
    if data.scopes is not None:
        oauth_config = dict(integration.oauth_config)
        oauth_config["scopes"] = data.scopes
        integration.oauth_config = oauth_config

    await db.commit()
    await db.refresh(integration)

    logger.info(
        f"Updated integration {integration.id}",
        extra={"integration_id": str(integration.id)},
    )

    return IntegrationResponse.model_validate(integration)


@router.delete("/{integration_id}")
async def delete_integration(
    db: DBSession,
    auth: RequireAdmin,
    integration_id: UUID,
    revoke_credentials: bool = Query(
        default=True,
        description="Whether to revoke all credentials with the provider",
    ),
    force: bool = Query(
        default=False,
        description=(
            "Force deletion even if some credential revocations fail. "
            "WARNING: Tokens may remain valid at the provider if revocation fails."
        ),
    ),
) -> dict:
    """
    Delete an integration and optionally revoke all credentials.

    Requires admin access.

    By default, this endpoint will fail if any credential cannot be revoked
    with the provider. This is a security measure to ensure tokens are not
    left active at the provider while appearing revoked in our system.

    Use `force=true` to delete the integration even if some revocations fail.
    In this case, credentials that failed to revoke will be marked as
    'revocation_failed' and should be investigated.

    Args:
        integration_id: Integration UUID
        revoke_credentials: Whether to revoke credentials with provider
        force: Delete even if some revocations fail

    Returns:
        Deletion result with revocation details

    Raises:
        HTTPException: If integration not found or revocation fails (unless force=true)
    """
    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.tenant_id == auth.tenant_id,
            Integration.deleted_at.is_(None),
        )
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    service = _get_integration_service(db)

    try:
        deletion_result = await service.delete_integration(
            integration,
            revoke_credentials=revoke_credentials,
            force=force,
        )
    except RevocationError as e:
        logger.exception(
            f"Failed to revoke credentials for integration {integration_id}",
            extra={
                "integration_id": str(integration_id),
                "credential_id": str(e.credential_id) if e.credential_id else None,
                "provider_error": e.provider_error,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "Failed to revoke some credentials with the provider. "
                    "Use force=true to delete anyway (not recommended)."
                ),
                "credential_id": str(e.credential_id) if e.credential_id else None,
                "provider_error": e.provider_error,
            },
        ) from e

    logger.info(
        f"Deleted integration {integration.id}",
        extra={
            "integration_id": str(integration.id),
            "revoked_credentials": revoke_credentials,
            "credentials_revoked": deletion_result["credentials_revoked"],
            "credentials_failed": [str(c) for c in deletion_result["credentials_failed"]],
            "fully_revoked": deletion_result["fully_revoked"],
        },
    )

    return {
        "message": "Integration deleted successfully",
        "integration_id": str(deletion_result["integration_id"]),
        "credentials_revoked": deletion_result["credentials_revoked"],
        "credentials_failed": [str(c) for c in deletion_result["credentials_failed"]],
        "fully_revoked": deletion_result["fully_revoked"],
        "warning": (
            None
            if deletion_result["fully_revoked"]
            else "Some credentials failed to revoke. Tokens may still be valid at the provider."
        ),
    }


# =============================================================================
# OAuth Flow Endpoints
# =============================================================================


@router.post("/{integration_id}/authorize", response_model=AuthorizationUrlResponse)
async def get_authorization_url(
    db: DBSession,
    auth: CurrentUser,
    integration_id: UUID,
    data: AuthorizationUrlRequest,
) -> AuthorizationUrlResponse:
    """
    Generate OAuth authorization URL for an employee.

    Starts the OAuth flow by generating a consent URL that the user
    should be redirected to.

    Args:
        integration_id: Integration UUID
        data: Authorization request with employee_id

    Returns:
        Authorization URL and state

    Raises:
        HTTPException: If integration not found
    """
    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.tenant_id == auth.tenant_id,
            Integration.status == "active",
            Integration.deleted_at.is_(None),
        )
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found or not active",
        )

    oauth_service = _get_oauth_service(db)

    try:
        auth_url, state = await oauth_service.generate_authorization_url(
            integration=integration,
            employee_id=data.employee_id,
            user_id=auth.user_id,
            redirect_after=data.redirect_after,
            use_pkce=data.use_pkce,
        )
    except ClientSecretNotConfiguredError as e:
        logger.exception(
            "Authorization failed: OAuth credentials not configured",
            extra={"provider": integration.provider, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth credentials not configured for {integration.provider}. "
            "Contact your administrator.",
        ) from e
    except DecryptionError as e:
        logger.exception("Authorization failed: credential decryption error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Platform OAuth configuration error. Contact support.",
        ) from e

    logger.info(
        f"Generated OAuth authorization URL for employee {data.employee_id}",
        extra={
            "employee_id": str(data.employee_id),
            "integration_id": str(integration_id),
            "provider": integration.provider,
        },
    )

    return AuthorizationUrlResponse(
        authorization_url=auth_url,
        state=state,
        provider=integration.provider,
        employee_id=data.employee_id,
    )


# =============================================================================
# Service Account Endpoints
# =============================================================================


@router.post(
    "/{integration_id}/service-account",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def setup_service_account(
    db: DBSession,
    auth: RequireAdmin,
    integration_id: UUID,
    data: ServiceAccountSetup,
) -> CredentialResponse:
    """
    Set up service account credentials for an employee.

    Requires admin access.

    Args:
        integration_id: Integration UUID
        data: Service account setup data

    Returns:
        Created credential

    Raises:
        HTTPException: If integration not found or not configured for service accounts
    """
    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.tenant_id == auth.tenant_id,
            Integration.deleted_at.is_(None),
        )
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    if integration.auth_type != "service_account":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Integration is not configured for service account authentication",
        )

    service = _get_integration_service(db)
    credential = await service.setup_service_account(
        integration=integration,
        employee_id=data.employee_id,
        service_account_key=data.service_account_key,
    )

    logger.info(
        f"Set up service account for employee {data.employee_id}",
        extra={
            "credential_id": str(credential.id),
            "employee_id": str(data.employee_id),
            "integration_id": str(integration_id),
        },
    )

    return CredentialResponse.model_validate(credential)


# =============================================================================
# Credential Status Endpoints
# =============================================================================


@router.get(
    "/{integration_id}/employees/{employee_id}/credential",
    response_model=CredentialStatusResponse,
)
async def get_credential_status(
    db: DBSession,
    auth: CurrentUser,
    integration_id: UUID,
    employee_id: UUID,
) -> CredentialStatusResponse:
    """
    Check if an employee has a credential for an integration.

    Args:
        integration_id: Integration UUID
        employee_id: Employee UUID

    Returns:
        Credential status
    """
    # Get integration first
    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.tenant_id == auth.tenant_id,
            Integration.deleted_at.is_(None),
        )
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    # Check for credential
    cred_result = await db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.integration_id == integration_id,
            IntegrationCredential.employee_id == employee_id,
            IntegrationCredential.status == "active",
            IntegrationCredential.deleted_at.is_(None),
        )
    )
    credential = cred_result.scalar_one_or_none()

    return CredentialStatusResponse(
        has_credential=credential is not None,
        provider=integration.provider,
        employee_id=employee_id,
        credential=CredentialResponse.model_validate(credential) if credential else None,
    )


@router.delete(
    "/{integration_id}/employees/{employee_id}/credential",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_employee_credential(
    db: DBSession,
    auth: RequireAdmin,
    integration_id: UUID,
    employee_id: UUID,
) -> None:
    """
    Revoke an employee's credential for an integration.

    Requires admin access.

    Args:
        integration_id: Integration UUID
        employee_id: Employee UUID

    Raises:
        HTTPException: If credential not found
    """
    # Get integration
    int_result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.tenant_id == auth.tenant_id,
            Integration.deleted_at.is_(None),
        )
    )
    integration = int_result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    # Get credential
    cred_result = await db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.integration_id == integration_id,
            IntegrationCredential.employee_id == employee_id,
            IntegrationCredential.deleted_at.is_(None),
        )
    )
    credential = cred_result.scalar_one_or_none()

    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )

    service = _get_integration_service(db)
    await service.revoke_credential(credential, integration)

    logger.info(
        f"Revoked credential for employee {employee_id}",
        extra={
            "credential_id": str(credential.id),
            "employee_id": str(employee_id),
            "integration_id": str(integration_id),
        },
    )
