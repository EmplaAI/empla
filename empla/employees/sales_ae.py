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
    >>> from empla.employees.config import EmployeeConfig, EmployeeRole
    >>>
    >>> config = EmployeeConfig(
    ...     name="Jordan Chen",
    ...     role=EmployeeRole.SALES_AE,
    ...     email="jordan@company.com"
    ... )
    >>> employee = SalesAE(config)
    >>> await employee.start()
"""

import logging
from typing import Any

from empla.employees.base import DigitalEmployee
from empla.employees.config import GoalConfig, SALES_AE_DEFAULT_GOALS
from empla.employees.exceptions import EmployeeStartupError, LLMGenerationError
from empla.employees.personality import Personality, SALES_AE_PERSONALITY

logger = logging.getLogger(__name__)


class SalesAE(DigitalEmployee):
    """
    Sales Account Executive Digital Employee.

    A highly autonomous sales professional focused on:
    - **Pipeline Management**: Maintains 3x coverage through proactive prospecting
    - **Lead Response**: Responds to inbound leads within 4 hours
    - **Outreach**: Runs personalized multi-channel outreach campaigns
    - **Deal Progression**: Moves deals through stages autonomously
    - **Meeting Management**: Runs discovery calls and product demos

    Personality:
    - Highly extraverted and enthusiastic
    - Quick decision-maker with moderate risk tolerance
    - Professional-casual communication style
    - Very proactive and persistent

    Default Goals:
    - Maintain 3x pipeline coverage (priority 9)
    - Respond to leads within 4 hours (priority 8)
    - Achieve 25% win rate (priority 7)

    Default Capabilities:
    - Email (inbox monitoring, outreach, follow-ups)
    - Calendar (scheduling meetings, managing availability)
    - CRM (logging activities, updating opportunities)

    Example:
        >>> # Create with minimal config
        >>> employee = SalesAE(EmployeeConfig(
        ...     name="Jordan Chen",
        ...     role=EmployeeRole.SALES_AE,
        ...     email="jordan@acme.com"
        ... ))
        >>> await employee.start()
        >>>
        >>> # Check status
        >>> print(employee.get_status())
        {'name': 'Jordan Chen', 'role': 'sales_ae', 'is_running': True, ...}
        >>>
        >>> # Stop when done
        >>> await employee.stop()
    """

    @property
    def default_personality(self) -> Personality:
        """Sales AE personality profile."""
        return SALES_AE_PERSONALITY

    @property
    def default_goals(self) -> list[GoalConfig]:
        """Default goals for Sales AE."""
        return SALES_AE_DEFAULT_GOALS

    @property
    def default_capabilities(self) -> list[str]:
        """Default capabilities for Sales AE."""
        return ["email", "calendar", "crm"]

    async def on_start(self) -> None:
        """
        Custom initialization for Sales AE.

        Sets up initial beliefs about the role and records start in episodic memory.

        Raises:
            EmployeeStartupError: If initialization fails
        """
        logger.info(f"Sales AE {self.name} initializing...")

        # Add initial beliefs about the role
        try:
            await self.beliefs.update_belief(
                subject="self",
                predicate="role",
                object={"type": "sales_ae", "focus": "pipeline_building"},
                confidence=1.0,
                source="initialization",
            )
        except Exception as e:
            logger.error(f"Failed to initialize beliefs for {self.name}: {e}", exc_info=True)
            raise EmployeeStartupError(f"Belief initialization failed: {e}") from e

        # Record start in episodic memory
        try:
            await self.memory.episodic.record_episode(
                episode_type="system",
                description=f"Sales AE {self.name} started and ready for autonomous operation",
                content={
                    "event": "employee_started",
                    "role": "sales_ae",
                    "capabilities": self.default_capabilities,
                    "goals": [g.description for g in self.default_goals],
                },
                importance=0.5,
            )
        except Exception as e:
            # Non-fatal: log warning but don't fail startup
            logger.warning(f"Failed to record start episode for {self.name}: {e}")

        logger.info(f"Sales AE {self.name} ready for autonomous operation")

    async def on_stop(self) -> None:
        """Custom cleanup for Sales AE."""
        logger.info(f"Sales AE {self.name} shutting down...")

        # Record stop in episodic memory (non-fatal if fails)
        if self._memory:
            try:
                await self.memory.episodic.record_episode(
                    episode_type="system",
                    description=f"Sales AE {self.name} stopped",
                    content={"event": "employee_stopped"},
                    importance=0.3,
                )
            except Exception as e:
                logger.warning(f"Failed to record stop episode for {self.name}: {e}")

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
                    logger.warning(f"Invalid pipeline coverage value '{belief.object.get('value')}': {e}")
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
            facts = await self.memory.semantic.query_by_predicate("opportunity_stage")
        except Exception as e:
            logger.error(f"Failed to query opportunities: {e}", exc_info=True)
            return []

        opportunities = []
        for fact in facts:
            if fact.object.get("stage") not in ["closed_won", "closed_lost"]:
                opportunities.append({
                    "account": fact.subject,
                    "stage": fact.object.get("stage"),
                    "value": fact.object.get("value"),
                })

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

        # Validate inputs
        if len(accounts) > 100:
            logger.warning(f"Large account list ({len(accounts)}), may be slow")

        # Use LLM to score and prioritize
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
            # Return original order on failure
            return accounts

        # TODO: Parse structured LLM response and sort by priority score
        # For now, return as-is
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
        # Validate inputs
        if not prospect_name or not prospect_name.strip():
            raise ValueError("prospect_name cannot be empty")
        if not company or not company.strip():
            raise ValueError("company cannot be empty")
        if len(prospect_name) > 100:
            raise ValueError("prospect_name too long (max 100 chars)")
        if len(company) > 100:
            raise ValueError("company too long (max 100 chars)")

        # Normalize inputs
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
                f"LLM generation failed for outreach email",
                exc_info=True,
                extra={"prospect": prospect_name, "company": company}
            )
            raise LLMGenerationError(f"Failed to generate outreach email: {e}") from e


__all__ = ["SalesAE"]
