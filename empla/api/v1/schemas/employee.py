"""
empla.api.v1.schemas.employee - Employee API Schemas

Pydantic schemas for employee CRUD operations.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EmployeeCreate(BaseModel):
    """Schema for creating a new employee."""

    name: str = Field(..., min_length=2, max_length=200, description="Employee display name")
    role: str = Field(
        ...,
        pattern=r"^(sales_ae|csm|pm|sdr|recruiter|custom)$",
        description="Employee role",
    )
    email: EmailStr = Field(..., description="Employee email address")
    capabilities: list[str] = Field(
        default=["email"],
        description="Enabled capabilities",
    )
    personality: dict[str, Any] = Field(
        default_factory=dict,
        description="Personality traits",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Employee configuration",
    )


class EmployeeUpdate(BaseModel):
    """Schema for updating an employee."""

    name: str | None = Field(None, min_length=2, max_length=200)
    email: EmailStr | None = None
    capabilities: list[str] | None = None
    personality: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    status: str | None = Field(
        None,
        pattern=r"^(onboarding|active|paused|terminated)$",
    )
    lifecycle_stage: str | None = Field(
        None,
        pattern=r"^(shadow|supervised|autonomous)$",
    )


class EmployeeResponse(BaseModel):
    """Schema for employee response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    role: str
    email: str
    status: str
    lifecycle_stage: str
    capabilities: list[str]
    personality: dict[str, Any]
    config: dict[str, Any]
    performance_metrics: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    onboarded_at: datetime | None = None
    activated_at: datetime | None = None

    # Runtime status (not from DB, computed)
    is_running: bool = False


class EmployeeListResponse(BaseModel):
    """Schema for paginated employee list."""

    items: list[EmployeeResponse]
    total: int
    page: int
    page_size: int
    pages: int


class EmployeeStatusResponse(BaseModel):
    """Schema for employee runtime status."""

    id: UUID
    name: str
    status: str
    lifecycle_stage: str
    is_running: bool
    current_intention: str | None = None
    last_activity: datetime | None = None
    cycle_count: int = 0
    error_count: int = 0
