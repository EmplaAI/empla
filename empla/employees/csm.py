"""
empla.employees.csm - Customer Success Manager Digital Employee

A proactive customer success professional focused on retention and growth.

Example:
    >>> from empla.employees import CustomerSuccessManager
    >>> from empla.employees.config import EmployeeConfig, EmployeeRole
    >>>
    >>> config = EmployeeConfig(
    ...     name="Sarah Mitchell",
    ...     role=EmployeeRole.CSM,
    ...     email="sarah@company.com"
    ... )
    >>> employee = CustomerSuccessManager(config)
    >>> await employee.start()
"""

import logging
from typing import Any

from empla.employees.base import DigitalEmployee
from empla.employees.config import GoalConfig, CSM_DEFAULT_GOALS
from empla.employees.exceptions import EmployeeStartupError, LLMGenerationError
from empla.employees.personality import Personality, CSM_PERSONALITY

logger = logging.getLogger(__name__)


class CustomerSuccessManager(DigitalEmployee):
    """
    Customer Success Manager Digital Employee.

    A highly autonomous CSM focused on:
    - **Customer Health**: Monitors usage metrics and health scores
    - **Proactive Outreach**: Reaches out before problems occur
    - **Onboarding**: Ensures smooth customer onboarding
    - **Retention**: Prevents churn through proactive intervention
    - **Expansion**: Identifies upsell opportunities

    Personality:
    - Highly agreeable and supportive
    - Detail-oriented and organized
    - Calm under pressure
    - Data-driven decision maker

    Default Goals:
    - Maintain 95% customer retention (priority 10)
    - Achieve NPS score above 50 (priority 8)
    - Complete onboarding within 5 days (priority 7)

    Default Capabilities:
    - Email (customer communication)
    - Calendar (QBR scheduling, check-ins)
    - CRM (health tracking, activity logging)

    Example:
        >>> employee = CustomerSuccessManager(EmployeeConfig(
        ...     name="Sarah Mitchell",
        ...     role=EmployeeRole.CSM,
        ...     email="sarah@acme.com"
        ... ))
        >>> await employee.start()
    """

    @property
    def default_personality(self) -> Personality:
        """CSM personality profile."""
        return CSM_PERSONALITY

    @property
    def default_goals(self) -> list[GoalConfig]:
        """Default goals for CSM."""
        return CSM_DEFAULT_GOALS

    @property
    def default_capabilities(self) -> list[str]:
        """Default capabilities for CSM."""
        return ["email", "calendar", "crm"]

    async def on_start(self) -> None:
        """
        Custom initialization for CSM.

        Sets up initial beliefs about the role and records start in episodic memory.

        Raises:
            EmployeeStartupError: If initialization fails
        """
        logger.info(f"CSM {self.name} initializing...")

        # Add initial beliefs about the role
        try:
            await self.beliefs.update_belief(
                subject="self",
                predicate="role",
                object={"type": "csm", "focus": "customer_success"},
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
                description=f"CSM {self.name} started and ready for autonomous operation",
                content={
                    "event": "employee_started",
                    "role": "csm",
                    "capabilities": self.default_capabilities,
                },
                importance=0.5,
            )
        except Exception as e:
            # Non-fatal: log warning but don't fail startup
            logger.warning(f"Failed to record start episode for {self.name}: {e}")

        logger.info(f"CSM {self.name} ready for autonomous operation")

    async def on_stop(self) -> None:
        """Custom cleanup for CSM."""
        logger.info(f"CSM {self.name} shutting down...")

        # Record stop in episodic memory (non-fatal if fails)
        if self._memory:
            try:
                await self.memory.episodic.record_episode(
                    episode_type="system",
                    description=f"CSM {self.name} stopped",
                    content={"event": "employee_stopped"},
                    importance=0.3,
                )
            except Exception as e:
                logger.warning(f"Failed to record stop episode for {self.name}: {e}")

    # =========================================================================
    # CSM-Specific Methods
    # =========================================================================

    async def get_at_risk_customers(self) -> list[dict[str, Any]]:
        """
        Get list of at-risk customers.

        Returns:
            List of customer dictionaries with risk factors, sorted by
            churn risk (highest risk first). Each dict contains:
            - customer: Customer name
            - health_status: Health status (at_risk, critical)
            - churn_risk: Churn probability (0.0-1.0)
            - reason: Reason for risk status
        """
        try:
            beliefs = await self.beliefs.get_beliefs_about("customer")
        except Exception as e:
            logger.error(f"Failed to query customer beliefs: {e}", exc_info=True)
            return []

        at_risk = []
        for belief in beliefs:
            if belief.predicate == "health_status":
                health = belief.obj.get("status", "")
                if health in ["at_risk", "critical"]:
                    at_risk.append({
                        "customer": belief.subject,
                        "health_status": health,
                        "churn_risk": belief.obj.get("churn_risk", 0.0),
                        "reason": belief.obj.get("reason", "unknown"),
                    })

        # Sort by churn risk descending (highest risk first)
        # This ensures CSM addresses most critical customers first
        return sorted(at_risk, key=lambda x: x.get("churn_risk", 0), reverse=True)

    async def check_customer_health(self, customer_name: str) -> dict[str, Any]:
        """
        Check health status of a specific customer.

        Args:
            customer_name: Name of the customer

        Returns:
            Health status dictionary with:
            - customer: Customer name
            - status: Health status (unknown, healthy, at_risk, critical)
            - churn_risk: Churn probability (if available)
            - metrics: Usage metrics (if available)
        """
        if not customer_name or not customer_name.strip():
            raise ValueError("customer_name cannot be empty")

        customer_name = customer_name.strip()

        try:
            beliefs = await self.beliefs.get_beliefs_about(customer_name)
        except Exception as e:
            logger.error(f"Failed to query beliefs for customer {customer_name}: {e}", exc_info=True)
            return {
                "customer": customer_name,
                "status": "unknown",
                "error": str(e),
            }

        health: dict[str, Any] = {
            "customer": customer_name,
            "status": "unknown",
            "metrics": {},
        }

        for belief in beliefs:
            if belief.predicate == "health_status":
                health["status"] = belief.obj.get("status", "unknown")
                health["churn_risk"] = belief.obj.get("churn_risk", 0.0)
            elif belief.predicate == "usage_metrics":
                health["metrics"] = belief.obj

        return health

    async def draft_check_in_email(
        self,
        customer_name: str,
        contact_name: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Draft a proactive check-in email.

        Args:
            customer_name: Company name (required, max 100 chars)
            contact_name: Contact person name (required, max 100 chars)
            context: Additional context (health status, recent issues, etc.)

        Returns:
            Email body text

        Raises:
            ValueError: If customer_name or contact_name is empty/invalid
            LLMGenerationError: If email generation fails
        """
        # Validate inputs
        if not customer_name or not customer_name.strip():
            raise ValueError("customer_name cannot be empty")
        if not contact_name or not contact_name.strip():
            raise ValueError("contact_name cannot be empty")
        if len(customer_name) > 100:
            raise ValueError("customer_name too long (max 100 chars)")
        if len(contact_name) > 100:
            raise ValueError("contact_name too long (max 100 chars)")

        # Normalize inputs
        customer_name = customer_name.strip()
        contact_name = contact_name.strip()

        context_str = ""
        if context:
            context_str = f"\nContext: {context}"

        prompt = f"""
        Draft a proactive check-in email to:
        - Contact: {contact_name}
        - Company: {customer_name}
        {context_str}

        The email should:
        - Be warm and supportive
        - Check on their success with the product
        - Offer help proactively
        - Be concise and genuine
        """

        try:
            logger.debug(f"Generating check-in email for {contact_name} at {customer_name}")
            response = await self.llm.generate(
                prompt=prompt,
                system=self.personality.to_system_prompt(),
            )
            logger.debug(f"Generated check-in email ({len(response.content)} chars)")
            return response.content
        except Exception as e:
            logger.error(
                f"LLM generation failed for check-in email",
                exc_info=True,
                extra={"customer": customer_name, "contact": contact_name}
            )
            raise LLMGenerationError(f"Failed to generate check-in email: {e}") from e


__all__ = ["CustomerSuccessManager"]
