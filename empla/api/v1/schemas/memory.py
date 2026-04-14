"""
empla.api.v1.schemas.memory - Memory Response Schemas

Read-only schemas for episodic, semantic, procedural, and working memory.

**N+1 safety:** Every response schema here lists explicit fields from the
memory table only — no ``employee`` field. Memory models have a lazy
``employee: Mapped["Employee"]`` relationship; accessing it outside an
eager-load raises ``MissingGreenlet`` in async contexts or silently fires
a sync query in sync contexts. Keeping ``employee`` out of the schema
guarantees ``model_validate(row)`` never dereferences it.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# =========================================================================
# Episodic
# =========================================================================


class EpisodicMemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    episode_type: str
    description: str
    content: dict[str, Any]
    participants: list[str]
    location: str | None = None
    importance: float
    recall_count: int
    last_recalled_at: datetime | None = None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime


class EpisodicMemoryListResponse(BaseModel):
    items: list[EpisodicMemoryResponse]
    total: int
    page: int
    page_size: int
    pages: int


# =========================================================================
# Semantic
# =========================================================================


class SemanticMemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    fact_type: str
    subject: str
    predicate: str
    object: str
    confidence: float
    source: str | None = None
    verified: bool
    access_count: int
    last_accessed_at: datetime | None = None
    context: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SemanticMemoryListResponse(BaseModel):
    items: list[SemanticMemoryResponse]
    total: int
    page: int
    page_size: int
    pages: int


# =========================================================================
# Procedural
# =========================================================================


class ProceduralMemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    name: str
    description: str
    procedure_type: str
    steps: list[dict[str, Any]]
    trigger_conditions: dict[str, Any]
    success_rate: float
    execution_count: int
    success_count: int
    avg_execution_time: float | None = None
    last_executed_at: datetime | None = None
    is_playbook: bool
    promoted_at: datetime | None = None
    learned_from: str | None = None
    created_at: datetime
    updated_at: datetime


class ProceduralMemoryListResponse(BaseModel):
    items: list[ProceduralMemoryResponse]
    total: int
    page: int
    page_size: int
    pages: int


# =========================================================================
# Working
# =========================================================================


class WorkingMemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    item_type: str
    content: dict[str, Any]
    importance: float
    expires_at: float | None = None
    access_count: int
    last_accessed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WorkingMemoryListResponse(BaseModel):
    """Working memory has no pagination — it's always small."""

    items: list[WorkingMemoryResponse]
    total: int
