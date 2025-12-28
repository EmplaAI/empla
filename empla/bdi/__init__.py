"""
empla.bdi - Belief-Desire-Intention Engine

BDI (Belief-Desire-Intention) architecture implementation for autonomous agents.

Components:
- BeliefSystem: Manages employee's world model (beliefs about the world)
- GoalSystem: Manages employee's goals/desires
- IntentionStack: Manages employee's committed plans/intentions

Example:
    >>> from empla.bdi import BeliefSystem, GoalSystem, IntentionStack
    >>> from empla.llm import LLMService, LLMConfig
    >>> from empla.models.database import get_db
    >>>
    >>> async with get_db() as session:
    ...     # Initialize LLM service
    ...     llm_service = LLMService(LLMConfig(...))
    ...
    ...     # Initialize BDI components
    ...     beliefs = BeliefSystem(session, employee_id, tenant_id, llm_service)
    ...     goals = GoalSystem(session, employee_id, tenant_id)
    ...     intentions = IntentionStack(session, employee_id, tenant_id)
    ...
    ...     # Update beliefs from observations
    ...     await beliefs.update_belief(
    ...         subject="Pipeline",
    ...         predicate="coverage",
    ...         object={"value": 2.0},
    ...         confidence=0.9,
    ...         source="observation"
    ...     )
    ...
    ...     # Add a goal
    ...     goal = await goals.add_goal(
    ...         goal_type="achievement",
    ...         description="Build pipeline to 3x coverage",
    ...         priority=8,
    ...         target={"metric": "coverage", "value": 3.0}
    ...     )
    ...
    ...     # Form an intention to achieve the goal
    ...     intention = await intentions.add_intention(
    ...         goal_id=goal.id,
    ...         intention_type="strategy",
    ...         description="Launch outbound campaign",
    ...         plan={"type": "outbound", "target_accounts": 50},
    ...         priority=8
    ...     )
    ...
    ...     # Commit transaction
    ...     await session.commit()
"""

from empla.bdi.beliefs import BeliefSystem
from empla.bdi.goals import GoalSystem
from empla.bdi.intentions import IntentionStack

__all__ = [
    "BeliefSystem",
    "GoalSystem",
    "IntentionStack",
]
