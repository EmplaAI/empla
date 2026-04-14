"""
empla.employees.sdr - Sales Development Representative Digital Employee

An SDR generates qualified leads through outbound prospecting and inbound
qualification. Personality, goals, and capabilities come from
``ROLE_CATALOG['sdr']``.

Example:
    >>> from empla.employees import SDR
    >>> from empla.employees.config import EmployeeConfig
    >>>
    >>> config = EmployeeConfig(
    ...     name="Taylor Reyes",
    ...     role="sdr",
    ...     email="taylor@company.com"
    ... )
    >>> employee = SDR(config)
    >>> await employee.start()
"""

import logging
from typing import Any

from empla.employees.catalog_backed import CatalogBackedEmployee
from empla.employees.exceptions import LLMGenerationError

logger = logging.getLogger(__name__)

MAX_NAME_LENGTH = 100
QUALIFICATION_REASONING_MAX_CHARS = 280  # tweet-length excerpt for stub output


class SDR(CatalogBackedEmployee):
    """Sales Development Representative Digital Employee."""

    role_code = "sdr"

    # =========================================================================
    # SDR-Specific Methods
    # =========================================================================

    async def qualify_lead(self, lead: dict[str, Any]) -> dict[str, Any]:
        """
        Qualify *lead* against a simple BANT-style rubric.

        Returns a dict with ``qualified`` (bool), ``score`` (0-100), and
        ``reasoning`` (str). On LLM failure, returns ``qualified=False`` with
        a reasoning note so callers can distinguish rejection from error.
        """
        if not lead:
            raise ValueError("lead cannot be empty")

        prompt = f"""
        Qualify this inbound lead using BANT (Budget, Authority, Need, Timing).

        Lead:
        {lead}

        Return a short JSON object with:
        - qualified (true/false)
        - score (0-100)
        - reasoning (one sentence)
        """

        try:
            response = await self.llm.generate(
                prompt=prompt,
                system=self.personality.to_system_prompt(),
            )
            # TODO: parse structured output; for now return raw content with a default
            return {
                "qualified": False,
                "score": 0,
                "reasoning": response.content[:QUALIFICATION_REASONING_MAX_CHARS],
            }
        except Exception as e:
            logger.error(
                "LLM generation failed for lead qualification",
                exc_info=True,
                extra={"lead_keys": list(lead.keys())},
            )
            return {
                "qualified": False,
                "score": 0,
                "reasoning": f"qualification_error: {e}",
            }

    async def draft_prospect_email(
        self,
        prospect_name: str,
        company: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Draft a short, high-volume prospecting email.

        Args:
            prospect_name: Prospect name (required, max 100 chars).
            company: Prospect company (required, max 100 chars).
            context: Optional context (industry, recent news).

        Raises:
            ValueError: If inputs are empty or too long.
            LLMGenerationError: If generation fails.
        """
        if not prospect_name or not prospect_name.strip():
            raise ValueError("prospect_name cannot be empty")
        if not company or not company.strip():
            raise ValueError("company cannot be empty")
        if len(prospect_name) > MAX_NAME_LENGTH:
            raise ValueError(f"prospect_name too long (max {MAX_NAME_LENGTH} chars)")
        if len(company) > MAX_NAME_LENGTH:
            raise ValueError(f"company too long (max {MAX_NAME_LENGTH} chars)")

        prospect_name = prospect_name.strip()
        company = company.strip()

        context_str = f"\nContext: {context}" if context else ""

        prompt = f"""
        Draft a concise outbound prospecting email to:
        - Name: {prospect_name}
        - Company: {company}
        {context_str}

        The email should:
        - Be under 80 words
        - Open with a specific, relevant hook
        - Ask for a short discovery call
        - Avoid jargon
        """

        try:
            response = await self.llm.generate(
                prompt=prompt,
                system=self.personality.to_system_prompt(),
            )
            return response.content
        except Exception as e:
            logger.error(
                "LLM generation failed for prospect email",
                exc_info=True,
                extra={"prospect": prospect_name, "company": company},
            )
            raise LLMGenerationError(f"Failed to generate prospect email: {e}") from e


__all__ = ["SDR"]
