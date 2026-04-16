"""
empla.api.v1.endpoints.role_builder - Custom-employee role generation

One admin-only endpoint that turns a plain-English job description into
a draft :class:`GeneratedRoleDraft`. The dashboard wizard pre-fills its
form from the response; on save it routes back through the regular
``POST /employees`` endpoint with ``role='custom'``. There is no
persistence here — the draft is ephemeral, the admin reviews and edits
the exact text that will be interpolated into the system prompt before
the employee is created.

Why no template table:
    Earlier drafts of PR #85 included a ``custom_roles`` table for
    template reuse. The team chose direct-create-only — re-running the
    LLM on each spawn costs ~$0.03 and avoids template-versioning
    questions. If template reuse becomes important later, an admin can
    manually re-submit the same description, or we add a "Save as
    template" button in a follow-up.

Security model:
    - Admin-only (``RequireAdmin`` dep).
    - Output validated by Pydantic — any malformed LLM payload returns
      422 with the parse error so the admin can edit-and-retry.
    - Control chars stripped from every text field.
    - Capabilities constrained to a closed allowlist.
    - The actual prompt-injection backstop is the wizard's review step
      where the admin sees the exact text before clicking Create.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from empla.api.deps import RequireAdmin
from empla.api.v1.schemas.role_builder import (
    ALLOWED_CAPABILITIES,
    GeneratedRoleDraft,
    GenerateRoleRequest,
)
from empla.llm import LLMService
from empla.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


# Bounded system prompt — gives the LLM a strict shape to generate, names
# the allowlist explicitly, and forbids meta-content. The generated
# ``role_description`` text is reviewed by an admin before it hits any
# downstream prompt, so this prompt is just for output quality, not for
# defending against the LLM emitting injection payloads (we can't — that
# job belongs to the admin review step).
# Note: f-string-style {{ }} escaping for braces inside the prompt body.
# The single {capabilities} placeholder is filled at request time from
# ALLOWED_CAPABILITIES so the prompt always reflects the current allowlist.
_SYSTEM_PROMPT = """You are designing a digital employee for a SaaS platform.

Given a plain-English job description, produce a JSON draft that captures:
- A short employee name suggestion (2-3 words, like "Marketing Manager").
- A 2-3 sentence role description that will be interpolated directly into
  the employee's system prompt. Write it in second person ("You ...").
  Keep it under 1000 characters. NO meta-instructions to the LLM, NO
  prompt-engineering tricks — just describe what the employee does.
- 3-6 initial goals: each with a clear description (1 sentence), a
  priority 1-10 (most important = 10), a target dict (use {{}} if no
  numeric target), and goal_type='achievement' unless 'maintenance' or
  'opportunity' fits better. Use these exact spellings — the BDI runtime
  branches on them.
- 1-4 capabilities from this exact set: {capabilities}. Pick only what
  the role actually needs — most roles need 1-2.
- Personality sliders (0.0-1.0): set conscientiousness, proactivity,
  persistence higher for execution-heavy roles; openness higher for
  creative/strategy roles; agreeableness higher for customer-facing roles.

Return ONLY the JSON. No commentary, no code fences."""


@router.post(
    "/generate-role",
    response_model=GeneratedRoleDraft,
    status_code=status.HTTP_200_OK,
)
async def generate_role(
    body: GenerateRoleRequest,
    auth: RequireAdmin,
) -> GeneratedRoleDraft:
    """Turn a NL job description into a :class:`GeneratedRoleDraft`.

    Returns:
        ``GeneratedRoleDraft`` ready for the dashboard wizard's review
        step. Does NOT persist anything — the draft only becomes an
        Employee row when the admin POSTs it back via /employees.

    Raises:
        503: LLM provider is unavailable / not configured.
        422: LLM returned malformed JSON or values that fail validation
             (out-of-range capability, missing required field).
    """
    settings = get_settings()
    try:
        llm_config = settings.build_llm_config()
        llm = LLMService(llm_config, owner_id=str(auth.tenant_id))
    except ValueError as e:
        # ValueError from LLMService.__init__ means an API key is missing
        # for the configured provider — treat as 503, not 500.
        logger.warning("LLM service unavailable for role generation: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM provider not configured. Set ANTHROPIC_API_KEY or equivalent.",
        ) from e

    system_prompt = _SYSTEM_PROMPT.format(capabilities=", ".join(sorted(ALLOWED_CAPABILITIES)))

    try:
        _, draft = await llm.generate_structured(
            prompt=body.description,
            response_format=GeneratedRoleDraft,
            system=system_prompt,
            max_tokens=2048,
            temperature=0.5,  # Lower than chat default — we want consistent shape, not creativity
        )
    except ValidationError as e:
        # LLM emitted JSON that doesn't match the schema. Surface the
        # validation error so the admin sees what's wrong and can rephrase.
        logger.info("LLM returned invalid role draft: %s", e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"LLM returned malformed draft: {e.errors()[0].get('msg', 'invalid')}",
        ) from e
    except Exception as e:
        logger.error("Role generation failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Role generation failed: {type(e).__name__}",
        ) from e

    if not isinstance(draft, GeneratedRoleDraft):
        # generate_structured contract guarantees this, but be defensive
        # so future provider drift can't slip past silently.
        logger.error(
            "LLMService.generate_structured returned %s, expected GeneratedRoleDraft",
            type(draft).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM returned an unexpected response shape.",
        )

    logger.info(
        "Generated role draft (admin=%s, tenant=%s, name_suggestion=%s)",
        auth.user_id,
        auth.tenant_id,
        draft.name_suggestion,
    )
    return draft
