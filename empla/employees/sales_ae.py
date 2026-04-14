"""
empla.employees.sales_ae - Sales Account Executive Digital Employee

The first production-ready digital employee.

A Sales AE is proactive, goal-oriented, and focused on:
- Building and maintaining pipeline
- Prospecting and outreach
- Running discovery calls and demos
- Closing deals

Example:
    >>> from empla.employees import SalesAE
    >>> from empla.employees.config import EmployeeConfig
    >>>
    >>> config = EmployeeConfig(
    ...     name="Jordan Chen",
    ...     role="sales_ae",
    ...     email="jordan@company.com"
    ... )
    >>> employee = SalesAE(config)
    >>> await employee.start()
"""

import json
import logging
from typing import Any

from empla.employees.catalog_backed import CatalogBackedEmployee
from empla.employees.exceptions import LLMGenerationError

logger = logging.getLogger(__name__)


class SalesAE(CatalogBackedEmployee):
    """
    Sales Account Executive Digital Employee.

    A highly autonomous sales professional focused on:
    - **Pipeline Management**: Maintains 3x coverage through proactive prospecting
    - **Lead Response**: Responds to inbound leads within 4 hours
    - **Outreach**: Runs personalized multi-channel outreach campaigns
    - **Deal Progression**: Moves deals through stages autonomously
    - **Meeting Management**: Runs discovery calls and product demos

    Personality, goals, and capabilities come from ``ROLE_CATALOG['sales_ae']``.

    Example:
        >>> employee = SalesAE(EmployeeConfig(
        ...     name="Jordan Chen",
        ...     role="sales_ae",
        ...     email="jordan@acme.com"
        ... ))
        >>> await employee.start()
    """

    role_code = "sales_ae"

    # =========================================================================
    # Sales-Specific Methods
    # =========================================================================

    async def check_pipeline_coverage(self) -> float:
        """
        Check current pipeline coverage.

        Pipeline coverage is the ratio of total pipeline value to quota.
        For example, if quota is $100k and pipeline is $250k, coverage is 2.5x.

        Returns:
            Pipeline coverage ratio (e.g., 2.5 means 2.5x quota).
            Returns 0.0 if no pipeline data available or on error.
        """
        try:
            beliefs = await self.beliefs.get_beliefs_about("pipeline")
        except Exception as e:
            logger.error(f"Failed to query pipeline beliefs: {e}", exc_info=True)
            return 0.0

        for belief in beliefs:
            if belief.predicate == "coverage":
                try:
                    value = belief.object.get("value")
                    if value is not None:
                        return float(value)
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Invalid pipeline coverage value '{belief.object.get('value')}': {e}"
                    )
                    continue

        logger.debug("No pipeline coverage belief found, returning 0.0")
        return 0.0

    async def get_open_opportunities(self) -> list[dict[str, Any]]:
        """
        Get list of open opportunities.

        Returns:
            List of opportunity dictionaries with keys:
            - account: Account name
            - stage: Deal stage
            - value: Deal value
        """
        try:
            facts = await self.memory.semantic.query_facts(predicate="opportunity_stage")
        except Exception as e:
            logger.error(f"Failed to query opportunities: {e}", exc_info=True)
            return []

        opportunities = []
        for fact in facts:
            if isinstance(fact.object, dict):
                fact_object = fact.object
            else:
                try:
                    parsed = json.loads(fact.object)
                    fact_object = parsed if isinstance(parsed, dict) else {}
                except (TypeError, ValueError, json.JSONDecodeError):
                    fact_object = {}

            if fact_object.get("stage") not in ["closed_won", "closed_lost"]:
                opportunities.append(
                    {
                        "account": fact.subject,
                        "stage": fact_object.get("stage"),
                        "value": fact_object.get("value"),
                    }
                )

        return opportunities

    async def prioritize_accounts(self, accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Prioritize accounts for outreach.

        Uses LLM to score and prioritize accounts based on deal size,
        engagement level, urgency, and fit.

        Args:
            accounts: List of account dictionaries

        Returns:
            Sorted list with highest priority first

        Note:
            Currently returns accounts in original order.
            TODO: Parse structured output from LLM and sort by priority score.
        """
        if not accounts:
            return []

        if len(accounts) > 100:
            logger.warning(f"Large account list ({len(accounts)}), may be slow")

        prompt = f"""
        As a Sales AE, prioritize these accounts for outreach.
        Consider: deal size, engagement level, urgency, fit.

        Accounts:
        {accounts}

        Return the accounts sorted by priority with a score 1-10 for each.
        """

        try:
            logger.debug(f"Prioritizing {len(accounts)} accounts")
            response = await self.llm.generate(
                prompt=prompt,
                system=self.personality.to_system_prompt(),
            )
            logger.debug(f"Account prioritization complete ({len(response.content)} chars)")
        except Exception as e:
            logger.error(f"LLM generation failed for account prioritization: {e}", exc_info=True)
            return accounts

        # TODO: Parse structured LLM response and sort by priority score
        return accounts

    async def draft_outreach_email(
        self,
        prospect_name: str,
        company: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Draft a personalized outreach email.

        Args:
            prospect_name: Name of the prospect (required, max 100 chars)
            company: Company name (required, max 100 chars)
            context: Additional context (industry, recent news, etc.)

        Returns:
            Email body text

        Raises:
            ValueError: If prospect_name or company is empty/invalid
            LLMGenerationError: If email generation fails
        """
        if not prospect_name or not prospect_name.strip():
            raise ValueError("prospect_name cannot be empty")
        if not company or not company.strip():
            raise ValueError("company cannot be empty")
        if len(prospect_name) > 100:
            raise ValueError("prospect_name too long (max 100 chars)")
        if len(company) > 100:
            raise ValueError("company too long (max 100 chars)")

        prospect_name = prospect_name.strip()
        company = company.strip()

        context_str = ""
        if context:
            context_str = f"\nContext: {context}"

        prompt = f"""
        Draft a personalized outreach email to:
        - Name: {prospect_name}
        - Company: {company}
        {context_str}

        The email should:
        - Be personalized and relevant
        - Have a clear value proposition
        - Include a specific call-to-action
        - Be concise (under 150 words)
        """

        try:
            logger.debug(f"Generating outreach email for {prospect_name} at {company}")
            response = await self.llm.generate(
                prompt=prompt,
                system=self.personality.to_system_prompt(),
            )
            logger.debug(f"Generated outreach email ({len(response.content)} chars)")
            return response.content
        except Exception as e:
            logger.error(
                "LLM generation failed for outreach email",
                exc_info=True,
                extra={"prospect": prospect_name, "company": company},
            )
            raise LLMGenerationError(f"Failed to generate outreach email: {e}") from e


__all__ = ["SalesAE"]
