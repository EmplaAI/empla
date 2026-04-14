"""
empla.employees.pm - Product Manager Digital Employee

A Product Manager drives product strategy, prioritizes features, and ships
high-impact releases. Personality, goals, and capabilities come from
``ROLE_CATALOG['pm']``.

Example:
    >>> from empla.employees import ProductManager
    >>> from empla.employees.config import EmployeeConfig
    >>>
    >>> config = EmployeeConfig(
    ...     name="Morgan Park",
    ...     role="pm",
    ...     email="morgan@company.com"
    ... )
    >>> employee = ProductManager(config)
    >>> await employee.start()
"""

import logging
from typing import Any

from empla.employees.catalog_backed import CatalogBackedEmployee
from empla.employees.exceptions import LLMGenerationError

logger = logging.getLogger(__name__)


class ProductManager(CatalogBackedEmployee):
    """Product Manager Digital Employee."""

    role_code = "pm"

    # =========================================================================
    # PM-Specific Methods
    # =========================================================================

    async def prioritize_backlog(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Prioritize backlog items using impact-vs-effort reasoning.

        Args:
            items: Backlog items, each with at least ``title`` and optional
                ``impact``, ``effort``, and ``confidence`` keys.

        Returns:
            A list sorted by descending priority. On LLM failure, returns the
            original order so the caller always gets a usable list.
        """
        if not items:
            return []

        if len(items) > 100:
            logger.warning(f"Large backlog ({len(items)}), prioritization may be slow")

        prompt = f"""
        As a Product Manager, rank these backlog items by impact vs effort.
        Consider user value, strategic alignment, effort, and confidence.

        Items:
        {items}

        Return the items sorted by priority with a 1-10 score for each.
        """

        try:
            response = await self.llm.generate(
                prompt=prompt,
                system=self.personality.to_system_prompt(),
            )
            logger.debug(f"Backlog prioritization complete ({len(response.content)} chars)")
        except Exception as e:
            logger.error(f"LLM generation failed for backlog prioritization: {e}", exc_info=True)
            return items

        # TODO: Parse structured output and sort by score
        return items

    async def draft_release_notes(
        self,
        features: list[str],
        version: str,
    ) -> str:
        """
        Draft release notes for *features* at *version*.

        Args:
            features: Short descriptions of shipped features (required, non-empty).
            version: Release version string (required, max 50 chars).

        Returns:
            Formatted release notes.

        Raises:
            ValueError: If *features* is empty or *version* invalid.
            LLMGenerationError: If generation fails.
        """
        if not features:
            raise ValueError("features cannot be empty")
        if not version or not version.strip():
            raise ValueError("version cannot be empty")
        if len(version) > 50:
            raise ValueError("version too long (max 50 chars)")

        version = version.strip()

        prompt = f"""
        Draft release notes for version {version}.

        Features:
        {chr(10).join(f"- {f}" for f in features)}

        The release notes should:
        - Start with a short summary (1-2 sentences)
        - Group features logically
        - Highlight user-visible benefits
        - Be concise and professional
        """

        try:
            response = await self.llm.generate(
                prompt=prompt,
                system=self.personality.to_system_prompt(),
            )
            return response.content
        except Exception as e:
            logger.error(
                "LLM generation failed for release notes",
                exc_info=True,
                extra={"version": version, "feature_count": len(features)},
            )
            raise LLMGenerationError(f"Failed to generate release notes: {e}") from e


__all__ = ["ProductManager"]
