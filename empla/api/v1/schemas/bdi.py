"""
empla.api.v1.schemas.bdi - BDI State Response Schemas

Read-only schemas for goals, intentions, and beliefs.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# =========================================================================
# Goals
# =========================================================================


class GoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    goal_type: str
    description: str
    priority: int
    target: dict[str, Any]
    current_progress: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    abandoned_at: datetime | None = None


class GoalListResponse(BaseModel):
    items: list[GoalResponse]
    total: int
    page: int
    page_size: int
    pages: int


# =========================================================================
# Intentions
# =========================================================================


class IntentionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    goal_id: UUID | None = None
    intention_type: str
    description: str
    plan: dict[str, Any]
    status: str
    priority: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    context: dict[str, Any]
    dependencies: list[UUID]
    created_at: datetime
    updated_at: datetime


class IntentionListResponse(BaseModel):
    items: list[IntentionResponse]
    total: int
    page: int
    page_size: int
    pages: int


# =========================================================================
# Beliefs
# =========================================================================


class BeliefResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    belief_type: str
    subject: str
    predicate: str
    object: dict[str, Any]
    confidence: float
    source: str
    evidence: list[Any]
    formed_at: datetime
    last_updated_at: datetime
    decay_rate: float
    created_at: datetime
    updated_at: datetime


class BeliefListResponse(BaseModel):
    items: list[BeliefResponse]
    total: int
    page: int
    page_size: int
    pages: int
