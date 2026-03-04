"""
empla.api.v1.endpoints.roles - Role Catalog Endpoints

Endpoint that lists all pre-defined employee roles with metadata.
"""

from fastapi import APIRouter

from empla.api.deps import CurrentUser
from empla.api.v1.schemas.roles import RoleDefinitionResponse, RoleListResponse
from empla.employees.catalog import list_roles
from empla.employees.personality import Personality
from empla.employees.registry import get_employee_class

router = APIRouter()


@router.get("/", response_model=RoleListResponse)
async def list_role_definitions(_auth: CurrentUser) -> RoleListResponse:
    """List all pre-defined employee roles with metadata."""
    default_personality = Personality()
    roles = []
    for role in list_roles():
        roles.append(
            RoleDefinitionResponse(
                code=role.code,
                title=role.title,
                description=role.description,
                short_description=role.short_description,
                default_capabilities=list(role.default_capabilities),
                has_implementation=get_employee_class(role.code) is not None,
                has_personality_preset=role.personality != default_personality,
            )
        )
    return RoleListResponse(roles=roles)
