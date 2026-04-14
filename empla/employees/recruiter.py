"""
empla.employees.recruiter - Recruiter Digital Employee

A Recruiter sources, screens, and hires talent. Personality, goals, and
capabilities come from ``ROLE_CATALOG['recruiter']``.

Example:
    >>> from empla.employees import Recruiter
    >>> from empla.employees.config import EmployeeConfig
    >>>
    >>> config = EmployeeConfig(
    ...     name="Alex Kim",
    ...     role="recruiter",
    ...     email="alex@company.com"
    ... )
    >>> employee = Recruiter(config)
    >>> await employee.start()
"""

import logging
from typing import Any

from empla.employees.catalog_backed import CatalogBackedEmployee
from empla.employees.exceptions import LLMGenerationError

logger = logging.getLogger(__name__)

MAX_NAME_LENGTH = 100
SCREENING_NOTES_MAX_CHARS = 500  # 2-3 sentence excerpt for stub output


class Recruiter(CatalogBackedEmployee):
    """Recruiter Digital Employee."""

    role_code = "recruiter"

    # =========================================================================
    # Recruiter-Specific Methods
    # =========================================================================

    async def screen_candidate(
        self,
        candidate: dict[str, Any],
        role_description: str,
    ) -> dict[str, Any]:
        """
        Screen *candidate* against *role_description*.

        Returns a dict with ``fit`` (``strong`` | ``possible`` | ``weak``),
        ``score`` (0-100), and ``notes``. On LLM failure, returns ``fit=weak``
        with an error note so callers can handle both rejection and transient
        failure explicitly.
        """
        if not candidate:
            raise ValueError("candidate cannot be empty")
        if not role_description or not role_description.strip():
            raise ValueError("role_description cannot be empty")

        prompt = f"""
        Screen this candidate for the role below.

        Role:
        {role_description}

        Candidate:
        {candidate}

        Return a short JSON object with:
        - fit ("strong" | "possible" | "weak")
        - score (0-100)
        - notes (2-3 sentences)
        """

        try:
            response = await self.llm.generate(
                prompt=prompt,
                system=self.personality.to_system_prompt(),
            )
            # TODO: parse structured output
            return {
                "fit": "possible",
                "score": 0,
                "notes": response.content[:SCREENING_NOTES_MAX_CHARS],
            }
        except Exception as e:
            logger.error(
                "LLM generation failed for candidate screening",
                exc_info=True,
                extra={"candidate_keys": list(candidate.keys())},
            )
            return {
                "fit": "weak",
                "score": 0,
                "notes": f"screening_error: {e}",
            }

    async def draft_outreach_message(
        self,
        candidate_name: str,
        role_title: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Draft a warm outreach message for a candidate.

        Args:
            candidate_name: Candidate name (required, max 100 chars).
            role_title: Target role title (required, max 100 chars).
            context: Optional context (why this candidate, company hook).

        Raises:
            ValueError: If inputs are empty or too long.
            LLMGenerationError: If generation fails.
        """
        if not candidate_name or not candidate_name.strip():
            raise ValueError("candidate_name cannot be empty")
        if not role_title or not role_title.strip():
            raise ValueError("role_title cannot be empty")
        if len(candidate_name) > MAX_NAME_LENGTH:
            raise ValueError(f"candidate_name too long (max {MAX_NAME_LENGTH} chars)")
        if len(role_title) > MAX_NAME_LENGTH:
            raise ValueError(f"role_title too long (max {MAX_NAME_LENGTH} chars)")

        candidate_name = candidate_name.strip()
        role_title = role_title.strip()

        context_str = f"\nContext: {context}" if context else ""

        prompt = f"""
        Draft a warm, personalized outreach message to:
        - Candidate: {candidate_name}
        - Role: {role_title}
        {context_str}

        The message should:
        - Be warm and specific, not generic
        - Explain why you reached out to this person
        - Invite a short conversation
        - Be under 120 words
        """

        try:
            response = await self.llm.generate(
                prompt=prompt,
                system=self.personality.to_system_prompt(),
            )
            return response.content
        except Exception as e:
            logger.error(
                "LLM generation failed for candidate outreach",
                exc_info=True,
                extra={"candidate": candidate_name, "role": role_title},
            )
            raise LLMGenerationError(f"Failed to generate outreach message: {e}") from e


__all__ = ["Recruiter"]
