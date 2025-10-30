"""
empla.bdi.beliefs - Belief System

BDI Belief System implementation:
- Manages employee's world model (beliefs about the world)
- Handles belief updates from observations
- Implements temporal decay
- Tracks belief confidence and evidence
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.belief import Belief, BeliefHistory


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
                existing_evidence = {
                    str(item) for item in (existing.evidence or [])
                }
                existing_evidence.update(str(item) for item in evidence)
                existing.evidence = list(existing_evidence)  # type: ignore[assignment]

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
            subject: Filter by subject (optional)
            predicate: Filter by predicate (optional)
            limit: Maximum number of records to return

        Returns:
            List of BeliefHistory records
        """
        query = select(BeliefHistory).where(
            BeliefHistory.employee_id == self.employee_id,
        )

        if subject and predicate:
            # Get belief ID first
            belief = await self.get_belief(subject, predicate)
            if belief:
                query = query.where(BeliefHistory.belief_id == belief.id)
            else:
                return []

        result = await self.session.execute(
            query.order_by(BeliefHistory.changed_at.desc()).limit(limit)
        )

        return list(result.scalars().all())
