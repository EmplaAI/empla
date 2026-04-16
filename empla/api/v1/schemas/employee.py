"""
empla.api.v1.schemas.employee - Employee API Schemas

Pydantic schemas for employee CRUD operations.
"""

import unicodedata
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# Type aliases for constrained values
EmployeeRole = Literal["sales_ae", "csm", "pm", "sdr", "recruiter", "custom"]
EmployeeStatus = Literal["onboarding", "active", "paused", "stopped", "terminated"]
LifecycleStage = Literal["shadow", "supervised", "autonomous"]

# Length cap for admin-supplied / LLM-generated role descriptions before they
# get interpolated into employee system prompts. Matches
# ``EmployeeConfig.validate_role_description`` so the API and the runtime
# agree on the budget. The cap exists for prompt-injection defense (an
# unbounded user-supplied blob landing in a system prompt is a vector); the
# admin-review gate is the real backstop, this is belt-and-suspenders.
MAX_ROLE_DESCRIPTION_LEN = 1000


_KEEP_WHITESPACE = {"\t", "\n", "\r"}


def _strip_control_chars(text: str) -> str:
    """Remove control / format chars that could hide content in a prompt.

    Strips every Unicode codepoint whose category begins with ``C``: ``Cc``
    (control — \\u0008 backspace, \\u001b ESC), ``Cf`` (format — includes
    BOM, ``\\u202e`` RTL override, ``\\u200b`` zero-width space, ``\\u200d``
    ZWJ), ``Cs`` (lone surrogates), ``Co`` (private-use), and ``Cn``
    (unassigned). Permits ``\\t \\n \\r`` so multi-line role descriptions
    still work. Run on every operator-supplied or LLM-generated string that
    lands in an employee system prompt — without this, an LLM could emit
    ``\\u202e`` or ``\\u200b`` inside a "harmless" description and silently
    change how the prompt parses.
    """
    return "".join(c for c in text if c in _KEEP_WHITESPACE or unicodedata.category(c)[0] != "C")


class GoalInput(BaseModel):
    """Goal payload for custom-employee creation. Mirrors ``GoalConfig``.

    ``description`` passes through ``_strip_control_chars`` because each
    goal is interpolated verbatim into the LLM system prompt via
    ``empla/employees/identity.py:_format_goals`` (``f"- [{p}/10] {desc}"``).
    The dashboard wizard does NOT show goals in the admin review step, so
    the schema is the only chokepoint for hidden Cc/Cf chars.
    """

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=500)
    priority: int = Field(default=5, ge=1, le=10)
    target: dict[str, Any] = Field(default_factory=dict)
    goal_type: str = Field(default="achievement", min_length=1, max_length=50)

    @field_validator("description")
    @classmethod
    def _clean_description(cls, v: str) -> str:
        cleaned = _strip_control_chars(v).strip()
        if not cleaned:
            raise ValueError("Goal description cannot be empty after stripping control chars")
        return cleaned


class EmployeeCreate(BaseModel):
    """Schema for creating a new employee.

    The optional ``role_description`` and ``goals`` fields are populated
    only for ``role='custom'`` employees, where the admin (or the
    LLM via ``POST /employees/generate-role``) defines the job. Built-in
    roles ignore them and use their ``ROLE_CATALOG`` defaults.
    """

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

    # Custom-role fields. Optional for built-ins, required-by-policy for
    # ``role='custom'`` (enforced in the endpoint, not the schema, so the
    # 422 messages can name the role).
    role_description: str | None = Field(
        default=None,
        max_length=MAX_ROLE_DESCRIPTION_LEN,
        description=(
            "Free-form job description interpolated into the LLM system prompt. "
            "Required for role='custom'. 1kB cap + control chars stripped."
        ),
    )
    goals: list[GoalInput] | None = Field(
        default=None,
        max_length=20,
        description=(
            "Initial goals seeded into ``employee_goals`` at creation. "
            "Required (non-empty) for role='custom'."
        ),
    )

    @field_validator("role_description")
    @classmethod
    def _clean_role_description(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = _strip_control_chars(v).strip()
        return cleaned or None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        # ``name`` is interpolated into every LLM system prompt via
        # ``identity.py``: ``f"You are {self.name}, a {self.role_title}."``
        # The same threat model that justifies stripping control chars from
        # ``role_description`` applies here — RTL overrides / zero-width
        # chars in the name silently shift the prompt's parsing.
        cleaned = _strip_control_chars(v).strip()
        if len(cleaned) < 2:
            raise ValueError("Employee name must be at least 2 non-control characters")
        return cleaned


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
