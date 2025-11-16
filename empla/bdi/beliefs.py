"""
empla.bdi.beliefs - Belief System

BDI Belief System implementation:
- Manages employee's world model (beliefs about the world)
- Handles belief updates from observations
- Implements temporal decay
- Tracks belief confidence and evidence
- Extracts beliefs from observations using LLM
"""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.belief import Belief, BeliefHistory

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from empla.core.loop.models import Observation
    from empla.llm import LLMService


class ExtractedBelief(BaseModel):
    """
    Single belief extracted from an observation by LLM.

    This represents a belief extracted from an observation using structured
    LLM output. It follows the Subject-Predicate-Object triple format.

    Example:
        >>> belief = ExtractedBelief(
        ...     subject="Acme Corp",
        ...     predicate="deal_stage",
        ...     object={"stage": "negotiation", "amount": 50000},
        ...     confidence=0.85,
        ...     reasoning="Email mentions 'final contract review' suggesting negotiation stage"
        ... )
    """

    subject: str = Field(
        ...,
        description="What the belief is about (e.g., customer name, project, person)",
        min_length=1,
    )
    predicate: str = Field(
        ...,
        description="Property or relation (e.g., 'pipeline_health', 'sentiment', 'next_action')",
        min_length=1,
    )
    object: dict[str, Any] = Field(
        ..., description="Value of the belief (can be text, number, boolean, or complex object)"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this belief (0-1) based on observation strength",
    )
    reasoning: str = Field(
        ...,
        description="Explanation of why this belief was extracted from the observation",
        min_length=1,
    )
    belief_type: str = Field(
        default="state",
        description="Type of belief (state, event, causal, evaluative)",
    )


class BeliefExtractionResult(BaseModel):
    """
    Result of extracting beliefs from an observation using LLM.

    Contains all beliefs extracted from a single observation, plus a summary
    of the observation for debugging and logging.

    Example:
        >>> result = BeliefExtractionResult(
        ...     beliefs=[belief1, belief2],
        ...     observation_summary="Customer email expressing high interest in product"
        ... )
    """

    beliefs: list[ExtractedBelief] = Field(
        default_factory=list,
        description="List of beliefs extracted from the observation",
    )
    observation_summary: str = Field(
        ...,
        description="Brief summary of what was observed",
        min_length=1,
    )


class BeliefSystem:
    """
    BDI Belief System.

    Manages an employee's beliefs about the world (their world model).
    Beliefs are formed from observations, updated based on new evidence,
    and decay over time if not reinforced.

    Example:
        >>> belief_system = BeliefSystem(session, employee_id, tenant_id)
        >>> await belief_system.update_belief(
        ...     subject="Acme Corp",
        ...     predicate="pipeline_health",
        ...     object={"status": "low", "coverage": 2.0},
        ...     confidence=0.8,
        ...     source="observation"
        ... )
    """

    def __init__(
        self,
        session: AsyncSession,
        employee_id: UUID,
        tenant_id: UUID,
    ):
        """
        Initialize BeliefSystem.

        Args:
            session: SQLAlchemy async session
            employee_id: Employee this belief system belongs to
            tenant_id: Tenant ID for multi-tenancy
        """
        self.session = session
        self.employee_id = employee_id
        self.tenant_id = tenant_id

    async def get_belief(
        self,
        subject: str,
        predicate: str,
    ) -> Belief | None:
        """
        Get a specific belief.

        Args:
            subject: What the belief is about
            predicate: Property or relation

        Returns:
            Belief if found, None otherwise
        """
        result = await self.session.execute(
            select(Belief).where(
                Belief.employee_id == self.employee_id,
                Belief.subject == subject,
                Belief.predicate == predicate,
                Belief.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update_belief(
        self,
        subject: str,
        predicate: str,
        object: dict[str, Any],
        confidence: float,
        source: str,
        belief_type: str = "state",
        evidence: list[UUID] | None = None,
        decay_rate: float = 0.1,
    ) -> Belief:
        """
        Update or create a belief.

        This implements belief revision:
        - If belief exists: update value, adjust confidence, add evidence
        - If belief is new: create with given confidence
        - Record change in belief history

        Args:
            subject: What the belief is about (e.g., "Acme Corp")
            predicate: Property or relation (e.g., "pipeline_health")
            object: Value (can be text, number, boolean, or complex object)
            confidence: Confidence level (0-1)
            source: How belief was formed (observation, inference, told_by_human, prior)
            belief_type: Type of belief (state, event, causal, evaluative)
            evidence: Supporting observations (episodic memory UUIDs)
            decay_rate: Linear decay per day (0-1)

        Returns:
            Updated or created Belief

        Example:
            >>> belief = await belief_system.update_belief(
            ...     subject="Acme Corp",
            ...     predicate="deal_stage",
            ...     object={"stage": "negotiation", "amount": 50000},
            ...     confidence=0.9,
            ...     source="observation"
            ... )
        """
        # Get existing belief if any
        existing = await self.get_belief(subject, predicate)

        if existing:
            # Update existing belief
            old_value = existing.object
            old_confidence = existing.confidence

            # Update belief
            existing.object = object
            existing.confidence = confidence
            existing.source = source
            existing.belief_type = belief_type
            existing.decay_rate = decay_rate
            existing.last_updated_at = datetime.now(UTC)

            # Merge evidence
            # Convert UUIDs to strings for JSONB serialization
            if evidence:
                existing_evidence = {str(item) for item in (existing.evidence or [])}
                existing_evidence.update(str(item) for item in evidence)
                existing.evidence = list(existing_evidence)

            # Record history
            await self._record_belief_change(
                belief_id=existing.id,
                change_type="updated",
                old_value=old_value,
                new_value=object,
                old_confidence=old_confidence,
                new_confidence=confidence,
                reason=f"Updated from {source}",
            )

            return existing

        # Create new belief
        # Convert UUIDs to strings for JSONB serialization
        belief = Belief(
            tenant_id=self.tenant_id,
            employee_id=self.employee_id,
            belief_type=belief_type,
            subject=subject,
            predicate=predicate,
            object=object,
            confidence=confidence,
            source=source,
            evidence=[str(item) for item in evidence] if evidence else [],
            formed_at=datetime.now(UTC),
            last_updated_at=datetime.now(UTC),
            decay_rate=decay_rate,
        )

        self.session.add(belief)
        await self.session.flush()  # Get ID for history

        # Record history
        await self._record_belief_change(
            belief_id=belief.id,
            change_type="created",
            old_value=None,
            new_value=object,
            old_confidence=None,
            new_confidence=confidence,
            reason=f"Created from {source}",
        )

        return belief

    async def get_all_beliefs(
        self,
        min_confidence: float = 0.0,
    ) -> list[Belief]:
        """
        Get all beliefs for this employee.

        Args:
            min_confidence: Minimum confidence threshold (0-1)

        Returns:
            List of Beliefs matching criteria
        """
        result = await self.session.execute(
            select(Belief)
            .where(
                Belief.employee_id == self.employee_id,
                Belief.confidence >= min_confidence,
                Belief.deleted_at.is_(None),
            )
            .order_by(Belief.confidence.desc(), Belief.last_updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_beliefs_about(
        self,
        subject: str,
        min_confidence: float = 0.0,
    ) -> list[Belief]:
        """
        Get all beliefs about a specific subject.

        Args:
            subject: Subject to query beliefs about
            min_confidence: Minimum confidence threshold (0-1)

        Returns:
            List of Beliefs about the subject
        """
        result = await self.session.execute(
            select(Belief)
            .where(
                Belief.employee_id == self.employee_id,
                Belief.subject == subject,
                Belief.confidence >= min_confidence,
                Belief.deleted_at.is_(None),
            )
            .order_by(Belief.confidence.desc())
        )
        return list(result.scalars().all())

    async def decay_beliefs(self) -> list[Belief]:
        """
        Apply temporal decay to all beliefs.

        Beliefs decay over time if not reinforced. This implements:
        - Linear decay: confidence -= (decay_rate * days_since_update)
        - Beliefs below threshold (0.1) are removed
        - Changes are recorded in history

        Returns:
            List of beliefs that were decayed

        Note:
            Should be called periodically (e.g., daily) by the proactive loop.
        """
        now = datetime.now(UTC)
        beliefs = await self.get_all_beliefs()
        decayed_beliefs = []

        for belief in beliefs:
            # Calculate days since last update
            days_since_update = (now - belief.last_updated_at).total_seconds() / 86400

            if days_since_update < 1:
                # Less than a day, no decay yet
                continue

            # Calculate decay
            decay_amount = belief.decay_rate * days_since_update
            old_confidence = belief.confidence
            new_confidence = max(0.0, belief.confidence - decay_amount)

            if new_confidence < 0.1:
                # Confidence too low, remove belief
                belief.deleted_at = now

                await self._record_belief_change(
                    belief_id=belief.id,
                    change_type="deleted",
                    old_value=belief.object,
                    new_value=None,
                    old_confidence=old_confidence,
                    new_confidence=0.0,
                    reason="Confidence decayed below threshold",
                )

                decayed_beliefs.append(belief)
            else:
                # Update confidence
                belief.confidence = new_confidence
                belief.last_updated_at = now

                await self._record_belief_change(
                    belief_id=belief.id,
                    change_type="decayed",
                    old_value=belief.object,
                    new_value=belief.object,
                    old_confidence=old_confidence,
                    new_confidence=new_confidence,
                    reason=f"Temporal decay after {days_since_update:.1f} days",
                )

                decayed_beliefs.append(belief)

        return decayed_beliefs

    async def remove_belief(
        self,
        subject: str,
        predicate: str,
        reason: str = "Manually removed",
    ) -> bool:
        """
        Remove a belief (soft delete).

        Args:
            subject: What the belief is about
            predicate: Property or relation
            reason: Why belief was removed

        Returns:
            True if belief was removed, False if not found
        """
        belief = await self.get_belief(subject, predicate)

        if not belief:
            return False

        belief.deleted_at = datetime.now(UTC)

        await self._record_belief_change(
            belief_id=belief.id,
            change_type="deleted",
            old_value=belief.object,
            new_value=None,
            old_confidence=belief.confidence,
            new_confidence=0.0,
            reason=reason,
        )

        return True

    async def _record_belief_change(
        self,
        belief_id: UUID,
        change_type: str,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any] | None,
        old_confidence: float | None,
        new_confidence: float | None,
        reason: str,
    ) -> BeliefHistory:
        """
        Record a belief change in history.

        Args:
            belief_id: Belief that changed
            change_type: Type of change (created, updated, deleted, decayed)
            old_value: Previous value
            new_value: New value
            old_confidence: Previous confidence
            new_confidence: New confidence
            reason: Why belief changed

        Returns:
            Created BeliefHistory record
        """
        history = BeliefHistory(
            tenant_id=self.tenant_id,
            employee_id=self.employee_id,
            belief_id=belief_id,
            change_type=change_type,
            old_value=old_value,
            new_value=new_value,
            old_confidence=old_confidence,
            new_confidence=new_confidence,
            reason=reason,
            changed_at=datetime.now(UTC),
        )

        self.session.add(history)
        return history

    async def get_belief_history(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        limit: int = 100,
    ) -> list[BeliefHistory]:
        """
        Get belief change history.

        Args:
            subject: Filter by subject (optional, can be used independently)
            predicate: Filter by predicate (optional, can be used independently)
            limit: Maximum number of records to return

        Returns:
            List of BeliefHistory records

        Example:
            >>> # Get all history for a subject
            >>> history = await belief_system.get_belief_history(subject="Acme Corp")
            >>> # Get all history for a predicate across all subjects
            >>> history = await belief_system.get_belief_history(predicate="deal_stage")
            >>> # Get history for specific subject+predicate combination
            >>> history = await belief_system.get_belief_history(
            ...     subject="Acme Corp", predicate="deal_stage"
            ... )
        """
        query = select(BeliefHistory).where(
            BeliefHistory.employee_id == self.employee_id,
        )

        # Apply subject and/or predicate filters independently via join
        if subject or predicate:
            query = query.join(Belief, Belief.id == BeliefHistory.belief_id)

            if subject:
                query = query.where(Belief.subject == subject)

            if predicate:
                query = query.where(Belief.predicate == predicate)

        result = await self.session.execute(
            query.order_by(BeliefHistory.changed_at.desc()).limit(limit)
        )

        return list(result.scalars().all())

    async def extract_beliefs_from_observation(
        self,
        observation: "Observation",
        llm_service: "LLMService",
    ) -> list[Belief]:
        """
        Extract structured beliefs from an observation using LLM.

        This uses the LLM to analyze an observation and extract actionable beliefs
        in Subject-Predicate-Object format. The LLM identifies:
        - What entities are mentioned (subjects)
        - What properties/relations are described (predicates)
        - What values/states are indicated (objects)
        - How confident we should be in each belief

        Args:
            observation: Observation to extract beliefs from
            llm_service: LLM service for structured extraction

        Returns:
            List of Beliefs that were created or updated

        Example:
            >>> from empla.llm import LLMService, LLMConfig
            >>> llm_service = LLMService(LLMConfig(...))
            >>> observation = Observation(
            ...     observation_type="email_received",
            ...     source="email",
            ...     content={
            ...         "from": "ceo@acmecorp.com",
            ...         "subject": "Urgent: Contract Review Needed",
            ...         "body": "We're ready to move forward with the $100k deal..."
            ...     }
            ... )
            >>> beliefs = await belief_system.extract_beliefs_from_observation(
            ...     observation, llm_service
            ... )
            >>> # Might extract:
            >>> # - ("Acme Corp", "deal_stage", {"stage": "contract_review"})
            >>> # - ("Acme Corp", "deal_amount", {"amount": 100000})
            >>> # - ("Acme Corp", "sentiment", {"sentiment": "positive", "urgency": "high"})

        Note:
            This method is typically called from the proactive loop's perception phase.
            The observation's content should be structured enough for the LLM to extract
            meaningful beliefs. Raw unstructured text may need preprocessing.
        """
        # Build prompt for LLM
        system_prompt = """You are an AI assistant helping a digital employee extract structured beliefs from observations.

Your task: Analyze the observation and extract factual beliefs in Subject-Predicate-Object format.

Guidelines:
1. Extract FACTUAL beliefs only (not assumptions or speculation)
2. Use clear, specific subjects (company names, person names, project names)
3. Use consistent predicates (deal_stage, sentiment, priority, next_action, etc.)
4. Provide structured objects (use dicts with relevant fields)
5. Assign confidence based on observation strength (0.0-1.0)
6. Explain your reasoning for each belief

Belief types:
- state: Current state of something (most common)
- event: Something that happened
- causal: Cause-effect relationship
- evaluative: Assessment or judgment

Examples:
- Subject: "Acme Corp", Predicate: "deal_stage", Object: {"stage": "negotiation"}
- Subject: "John Smith", Predicate: "sentiment", Object: {"sentiment": "positive", "reason": "expressed enthusiasm"}
- Subject: "Q4 Campaign", Predicate: "priority", Object: {"priority": "high", "deadline": "2025-12-31"}
"""

        user_prompt = f"""Observation Type: {observation.observation_type}
Source: {observation.source}
Priority: {observation.priority}/10
Timestamp: {observation.timestamp.isoformat()}

Content:
{self._format_observation_content(observation.content)}

Extract all relevant beliefs from this observation. Focus on actionable information that would help the employee make decisions."""

        # Use LLM to extract beliefs with error handling
        try:
            _, extraction_result = await llm_service.generate_structured(
                prompt=user_prompt,
                system=system_prompt,
                response_format=BeliefExtractionResult,
                temperature=0.3,  # Lower temperature for more consistent extraction
            )
        except Exception as e:
            logger.error(
                f"LLM belief extraction failed for observation {observation.observation_id}: {e}",
                exc_info=True,
                extra={
                    "observation_id": str(observation.observation_id),
                    "observation_type": observation.observation_type,
                    "source": observation.source,
                    "employee_id": str(self.employee_id),
                },
            )
            # Return empty list on LLM failure to prevent perception loop crash
            return []

        # Process extracted beliefs
        created_beliefs: list[Belief] = []

        for extracted in extraction_result.beliefs:
            # Create or update belief using existing update_belief method
            # Use "observation" as source since these beliefs are extracted from observations
            belief = await self.update_belief(
                subject=extracted.subject,
                predicate=extracted.predicate,
                object=extracted.object,
                confidence=extracted.confidence,
                source="observation",
                belief_type=extracted.belief_type,
                evidence=[observation.observation_id],
                decay_rate=0.1,  # Default decay rate
            )

            created_beliefs.append(belief)

        # Update observation to mark as processed
        # Note: This is done by the caller (ProactiveLoop) to avoid circular dependencies

        return created_beliefs

    def _format_observation_content(self, content: dict[str, Any]) -> str:
        """
        Format observation content for LLM prompt.

        Converts dict content to readable text format for the LLM.

        Args:
            content: Observation content dict

        Returns:
            Formatted string representation
        """
        lines = []
        for key, value in content.items():
            if isinstance(value, dict):
                # Nested dict
                lines.append(f"{key}:")
                for sub_key, sub_value in value.items():
                    lines.append(f"  {sub_key}: {sub_value}")
            elif isinstance(value, list):
                # List
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
            else:
                # Simple value
                lines.append(f"{key}: {value}")

        return "\n".join(lines)
