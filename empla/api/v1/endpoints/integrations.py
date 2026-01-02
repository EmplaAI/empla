"""
empla.api.v1.endpoints.integrations - Integration Management Endpoints

REST API endpoints for OAuth integration management:
- Create/list/delete integrations (admin operations)
- OAuth authorization flow (authorize, callback)
- Service account setup
- Credential status checking
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, select

from empla.api.deps import CurrentUser, DBSession, RequireAdmin
from empla.api.ratelimit import (
    RateLimitExceeded,
    get_client_identifier,
    oauth_callback_limiter,
)
from empla.api.v1.schemas.integration import (
    AuthorizationUrlRequest,
    AuthorizationUrlResponse,
    CredentialResponse,
    CredentialStatusResponse,
    IntegrationCreate,
    IntegrationListResponse,
    IntegrationResponse,
    IntegrationUpdate,
    OAuthCallbackResponse,
    ServiceAccountSetup,
)
from empla.models.integration import (
    Integration,
    IntegrationAuthType,
    IntegrationCredential,
    IntegrationProvider,
)
from empla.services.integrations import (
    IntegrationService,
    InvalidStateError,
    OAuthService,
    RevocationError,
    TokenExchangeError,
    get_token_manager,
)

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
        logger.error(
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

    auth_url, state = await oauth_service.generate_authorization_url(
        integration=integration,
        employee_id=data.employee_id,
        user_id=auth.user_id,
        redirect_after=data.redirect_after,
        use_pkce=data.use_pkce,
    )

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


@router.get("/callback", response_model=OAuthCallbackResponse)
async def oauth_callback(
    request: Request,
    db: DBSession,
    state: str = Query(..., description="OAuth state parameter"),
    code: str = Query(default=None, description="Authorization code"),
    error: str = Query(default=None, description="OAuth error"),
    error_description: str = Query(default=None, description="OAuth error description"),
) -> OAuthCallbackResponse:
    """
    Handle OAuth callback from provider.

    This endpoint is called by the OAuth provider after user consent.
    It exchanges the authorization code for tokens and stores them.

    Note: This endpoint doesn't require authentication because it's called
    by the OAuth provider redirect. Security is provided by the state parameter.

    Rate limited: 10 requests per minute per IP to prevent abuse.

    Args:
        state: OAuth state for CSRF protection
        code: Authorization code (if successful)
        error: OAuth error code (if failed)
        error_description: OAuth error description

    Returns:
        Callback result with redirect URI

    Raises:
        RateLimitExceeded: If rate limit is exceeded (429 Too Many Requests)
    """
    # Rate limit check - prevent abuse of unauthenticated callback endpoint
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
            f"OAuth error from provider: {error} - {error_description}",
            extra={"error": error, "error_description": error_description},
        )
        return OAuthCallbackResponse(
            success=False,
            redirect_uri="/integrations?error=oauth_denied",
            error=error_description or error,
        )

    if not code:
        return OAuthCallbackResponse(
            success=False,
            redirect_uri="/integrations?error=missing_code",
            error="Authorization code not provided",
        )

    oauth_service = _get_oauth_service(db)

    try:
        credential, redirect_uri = await oauth_service.handle_callback(
            state=state,
            code=code,
        )

        logger.info(
            f"OAuth callback successful for employee {credential.employee_id}",
            extra={
                "credential_id": str(credential.id),
                "employee_id": str(credential.employee_id),
            },
        )

        return OAuthCallbackResponse(
            success=True,
            redirect_uri=redirect_uri,
            credential_id=credential.id,
            employee_id=credential.employee_id,
        )

    except InvalidStateError as e:
        logger.warning(f"Invalid OAuth state: {e}")
        return OAuthCallbackResponse(
            success=False,
            redirect_uri="/integrations?error=invalid_state",
            error="Invalid or expired OAuth state",
        )

    except TokenExchangeError as e:
        logger.error(f"Token exchange failed: {e}")
        return OAuthCallbackResponse(
            success=False,
            redirect_uri="/integrations?error=token_exchange",
            error=str(e),
        )

    except Exception as e:
        logger.exception(f"Unexpected error in OAuth callback: {e}")
        return OAuthCallbackResponse(
            success=False,
            redirect_uri="/integrations?error=unknown",
            error="An unexpected error occurred",
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
