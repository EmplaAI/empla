"""
empla.api.v1.schemas - API Schemas

Contains all v1 API Pydantic schemas.
"""

from empla.api.v1.schemas.employee import (
    EmployeeCreate,
    EmployeeListResponse,
    EmployeeResponse,
    EmployeeStatusResponse,
    EmployeeUpdate,
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

__all__ = [
    "AuthorizationUrlRequest",
    "AuthorizationUrlResponse",
    "CredentialResponse",
    "CredentialStatusResponse",
    "EmployeeCreate",
    "EmployeeListResponse",
    "EmployeeResponse",
    "EmployeeStatusResponse",
    "EmployeeUpdate",
    "IntegrationCreate",
    "IntegrationListResponse",
    "IntegrationResponse",
    "IntegrationUpdate",
    "OAuthCallbackResponse",
    "ServiceAccountSetup",
]
