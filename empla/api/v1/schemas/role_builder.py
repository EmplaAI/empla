"""
empla.api.v1.schemas.role_builder - Custom-employee role generation schemas

Pydantic models for the LLM-driven role builder (PR #85). Two layers:

1. ``GenerateRoleRequest`` — admin describes the job in plain English.
2. ``GeneratedRoleDraft`` — what the LLM returns + what the API echoes
   back to the dashboard wizard for review/edit. The draft maps 1:1 onto
   ``EmployeeCreate`` (name + role_description + capabilities + goals
   + personality) so the wizard can submit it back through the existing
   ``POST /employees`` endpoint with ``role='custom'`` after the admin
   approves the text.

Validation is deliberately strict: every string passes through control-
char stripping + length caps, every capability is from a closed allowlist,
every goal matches the same shape ``EmployeeGoal`` will store. If the LLM
emits anything off-shape, ``generate_structured`` raises and the endpoint
returns 422 — the dashboard surfaces the parse error so the admin can
edit-and-retry.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from empla.api.v1.schemas.employee import (
    MAX_ROLE_DESCRIPTION_LEN,
    GoalInput,
    _strip_control_chars,
)

# Closed allowlist of capability keys the LLM is allowed to pick. Matches
# what ``ROLE_CATALOG`` uses today (``email``, ``calendar``, ``crm``).
# ``search`` is included as a forward-compatible option used by some
# built-in tools but not yet wired everywhere; if the LLM emits anything
# else we reject the draft so the admin sees the rejection rather than
# silently shipping a tool the runtime can't satisfy.
ALLOWED_CAPABILITIES: frozenset[str] = frozenset({"email", "calendar", "crm", "search"})

CapabilityKey = Literal["email", "calendar", "crm", "search"]


class GenerateRoleRequest(BaseModel):
    """Admin's natural-language description of the job to fill."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(
        min_length=10,
        max_length=2000,
        description=(
            "Plain-English description of the employee's job, audience, and "
            "ways of working. Length-capped at 2kB; the LLM compresses this "
            "into a 1kB role_description."
        ),
    )

    @field_validator("description")
    @classmethod
    def _clean(cls, v: str) -> str:
        cleaned = _strip_control_chars(v).strip()
        if len(cleaned) < 10:
            raise ValueError("description must be at least 10 non-control characters")
        return cleaned


class PersonalitySliders(BaseModel):
    """Subset of ``empla.employees.personality.Personality`` that the LLM controls.

    We expose only the Big Five floats + the work-style floats so the
    LLM can't emit unbounded structured config. ``CommunicationStyle``
    and ``DecisionStyle`` are nested dataclasses with their own enums and
    are deliberately omitted from the LLM surface — admin can tune those
    in the wizard's review step if they care, but the default is fine.
    """

    model_config = ConfigDict(extra="forbid")

    openness: float = Field(default=0.5, ge=0.0, le=1.0)
    conscientiousness: float = Field(default=0.5, ge=0.0, le=1.0)
    extraversion: float = Field(default=0.5, ge=0.0, le=1.0)
    agreeableness: float = Field(default=0.5, ge=0.0, le=1.0)
    neuroticism: float = Field(default=0.3, ge=0.0, le=1.0)
    proactivity: float = Field(default=0.7, ge=0.0, le=1.0)
    persistence: float = Field(default=0.7, ge=0.0, le=1.0)
    attention_to_detail: float = Field(default=0.5, ge=0.0, le=1.0)


class GeneratedRoleDraft(BaseModel):
    """LLM-generated employee draft. Returned by ``POST /employees/generate-role``.

    The dashboard wizard pre-fills its form from this object. The admin
    may edit any field, then submit through ``POST /employees`` with
    ``role='custom'`` and the (possibly edited) ``role_description`` +
    ``goals`` + ``personality`` + ``capabilities``.

    Stays close to ``EmployeeCreate`` field names so the round-trip is
    literally a JSON copy with one field renamed (``name_suggestion``
    → ``name``).
    """

    model_config = ConfigDict(extra="forbid")

    name_suggestion: str = Field(
        min_length=2,
        max_length=200,
        description="Suggested employee display name. Admin can rename freely.",
    )
    role_description: str = Field(
        min_length=20,
        max_length=MAX_ROLE_DESCRIPTION_LEN,
        description="What this role does — interpolated into the LLM system prompt.",
    )
    capabilities: list[CapabilityKey] = Field(
        min_length=1,
        max_length=10,
        description="Tool categories the employee should have access to.",
    )
    goals: list[GoalInput] = Field(
        min_length=1,
        max_length=10,
        description="Initial goals seeded into the BDI system at creation.",
    )
    personality: PersonalitySliders = Field(
        default_factory=PersonalitySliders,
        description="Big Five + work-style sliders. Defaults are sensible.",
    )

    @field_validator("name_suggestion", "role_description")
    @classmethod
    def _clean_text(cls, v: str) -> str:
        cleaned = _strip_control_chars(v).strip()
        if not cleaned:
            raise ValueError("must be non-empty after control-char stripping")
        return cleaned

    @field_validator("capabilities")
    @classmethod
    def _dedupe_capabilities(cls, v: list[str]) -> list[str]:
        # Pydantic's Literal already rejects unknown values; this just
        # de-duplicates while preserving order so `["email","email"]`
        # doesn't survive into the Employee row.
        seen: set[str] = set()
        out: list[str] = []
        for c in v:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out
