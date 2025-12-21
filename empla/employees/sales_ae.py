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

import logging
from typing import Any

from empla.employees.base import DigitalEmployee
from empla.employees.config import GoalConfig, SALES_AE_DEFAULT_GOALS
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
        ...     role="sales_ae",
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
        """Custom initialization for Sales AE."""
        logger.info(f"Sales AE {self.name} initializing...")

        # Add initial beliefs about the role
        await self.beliefs.update_belief(
            subject="self",
            predicate="role",
            object={"type": "sales_ae", "focus": "pipeline_building"},
            confidence=1.0,
            source="initialization",
        )

        # Record start in episodic memory
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

        logger.info(f"Sales AE {self.name} ready for autonomous operation")

    async def on_stop(self) -> None:
        """Custom cleanup for Sales AE."""
        logger.info(f"Sales AE {self.name} shutting down...")

        # Record stop in episodic memory
        if self.memory:
            await self.memory.episodic.record_episode(
                episode_type="system",
                description=f"Sales AE {self.name} stopped",
                content={"event": "employee_stopped"},
                importance=0.3,
            )

    # =========================================================================
    # Sales-Specific Methods
    # =========================================================================

    async def check_pipeline_coverage(self) -> float:
        """
        Check current pipeline coverage.

        Returns:
            Pipeline coverage ratio (e.g., 2.5 means 2.5x quota)
        """
        # Query beliefs for pipeline metrics
        beliefs = await self.beliefs.get_beliefs_about("pipeline")

        for belief in beliefs:
            if belief.predicate == "coverage":
                return float(belief.obj.get("value", 0.0))

        return 0.0

    async def get_open_opportunities(self) -> list[dict[str, Any]]:
        """
        Get list of open opportunities.

        Returns:
            List of opportunity dictionaries
        """
        # Query semantic memory for opportunities
        facts = await self.memory.semantic.query_by_predicate("opportunity_stage")

        opportunities = []
        for fact in facts:
            if fact.obj.get("stage") not in ["closed_won", "closed_lost"]:
                opportunities.append({
                    "account": fact.subject,
                    "stage": fact.obj.get("stage"),
                    "value": fact.obj.get("value"),
                })

        return opportunities

    async def prioritize_accounts(self, accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Prioritize accounts for outreach.

        Args:
            accounts: List of account dictionaries

        Returns:
            Sorted list with highest priority first
        """
        # Use LLM to score and prioritize
        prompt = f"""
        As a Sales AE, prioritize these accounts for outreach.
        Consider: deal size, engagement level, urgency, fit.

        Accounts:
        {accounts}

        Return the accounts sorted by priority with a score 1-10 for each.
        """

        response = await self.llm.generate(
            prompt=prompt,
            system=self.personality.to_system_prompt(),
        )

        # For now, return as-is (in production, parse LLM response)
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
            prospect_name: Name of the prospect
            company: Company name
            context: Additional context (industry, recent news, etc.)

        Returns:
            Email body text
        """
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

        response = await self.llm.generate(
            prompt=prompt,
            system=self.personality.to_system_prompt(),
        )

        return response.content


__all__ = ["SalesAE"]
