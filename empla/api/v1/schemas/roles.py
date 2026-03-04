"""
empla.api.v1.schemas.roles - Role API Schemas
"""

from pydantic import BaseModel, Field


class RoleDefinitionResponse(BaseModel):
    """API response for a single role definition."""

    code: str = Field(..., description="Role code, e.g. 'sales_ae'")
    title: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="LLM-facing role description")
    short_description: str = Field(..., description="Brief UI label")
    default_capabilities: list[str] = Field(
        default_factory=list, description="Default capabilities for this role"
    )
    has_implementation: bool = Field(
        ..., description="True if a DigitalEmployee subclass exists for this role"
    )
    has_personality_preset: bool = Field(
        ..., description="True if personality differs from default"
    )


class RoleListResponse(BaseModel):
    """API response for listing all roles."""

    roles: list[RoleDefinitionResponse]
