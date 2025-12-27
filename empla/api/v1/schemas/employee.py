"""
empla.api.v1.schemas.employee - Employee API Schemas

Pydantic schemas for employee CRUD operations.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Type aliases for constrained values
EmployeeRole = Literal["sales_ae", "csm", "pm", "sdr", "recruiter", "custom"]
EmployeeStatus = Literal["onboarding", "active", "paused", "stopped", "terminated"]
LifecycleStage = Literal["shadow", "supervised", "autonomous"]


class EmployeeCreate(BaseModel):
    """Schema for creating a new employee."""

    name: str = Field(..., min_length=2, max_length=200, description="Employee display name")
    role: EmployeeRole = Field(..., description="Employee role")
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
    status: EmployeeStatus | None = None
    lifecycle_stage: LifecycleStage | None = None


class EmployeeResponse(BaseModel):
    """Schema for employee response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    role: EmployeeRole
    email: str
    status: EmployeeStatus
    lifecycle_stage: LifecycleStage
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
    status: EmployeeStatus
    lifecycle_stage: LifecycleStage
    is_running: bool
    is_paused: bool = False
    has_error: bool = False
    last_error: str | None = None
    current_intention: str | None = None
    last_activity: datetime | None = None
    cycle_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
