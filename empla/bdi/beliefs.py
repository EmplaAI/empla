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
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.belief import Belief, BeliefHistory

logger = logging.getLogger(__name__)

# Allowed belief types (must match database constraint)
BeliefType = Literal["state", "event", "causal", "evaluative"]

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
    belief_type: BeliefType = Field(
        default="state",
        description="Type of belief (state, event, causal, evaluative)",
    )

    @field_validator("belief_type", mode="before")
    @classmethod
    def normalize_belief_type(cls, v: str | BeliefType) -> str:
        """
        Normalize belief_type to lowercase and validate against allowed values.

        This handles variations in LLM output (capitalization, common synonyms)
        and ensures the value matches database constraints.

        Args:
            v: Raw belief_type value from LLM

        Returns:
            Normalized belief_type value

        Raises:
            ValueError: If belief_type is not valid
        """
        if not isinstance(v, str):
            return v  # Already validated by Literal type

        # Normalize to lowercase
        normalized = v.lower().strip()

        # Map common variants to canonical values
        variant_map = {
            "status": "state",
            "condition": "state",
            "action": "event",
            "occurrence": "event",
            "cause": "causal",
            "cause-effect": "causal",
            "assessment": "evaluative",
            "evaluation": "evaluative",
            "judgment": "evaluative",
        }
        normalized = variant_map.get(normalized, normalized)

        # Validate against allowed values
        allowed: set[str] = {"state", "event", "causal", "evaluative"}
        if normalized not in allowed:
            raise ValueError(
                f"Invalid belief_type '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )

        return normalized


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


class BeliefUpdateResult(BaseModel):
    """
    Result of updating or creating a belief.

    Returned by update_belief to capture both the belief and metadata
    about whether it was created or updated.

    Attributes:
        belief: The ORM Belief object that was created/updated
        old_confidence: Previous confidence (None for new beliefs, actual value for updates)
        was_created: True if this was a new belief, False if updated
    """

    belief: Any  # Belief ORM model (can't use forward ref with BaseModel easily)
    old_confidence: float | None
    was_created: bool

    model_config = {"arbitrary_types_allowed": True}


class BeliefChangeResult:
    """
    Represents a change to a belief, matching the BeliefChange protocol.

    This is returned by update_beliefs to indicate what beliefs were
    created or modified.

    Attributes:
        subject: The entity the belief is about
        predicate: The property or relationship
        importance: How significant this change is (0.0-1.0)
        old_confidence: Previous confidence level (0.0 for new beliefs)
        new_confidence: New confidence level after update
        belief: The actual Belief object that was created/updated
    """

    def __init__(
        self,
        subject: str,
        predicate: str,
        importance: float,
        old_confidence: float,
        new_confidence: float,
        belief: "Belief",
    ) -> None:
        self.subject = subject
        self.predicate = predicate
        self.importance = importance
        self.old_confidence = old_confidence
        self.new_confidence = new_confidence
        self.belief = belief


class BeliefSystem:
    """
    BDI Belief System.

    Manages an employee's beliefs about the world (their world model).
    Beliefs are formed from observations, updated based on new evidence,
    and decay over time if not reinforced.

    Example:
        >>> belief_system = BeliefSystem(session, employee_id, tenant_id, llm_service)
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
        llm_service: "LLMService",
    ) -> None:
        """
        Initialize BeliefSystem.

        Args:
            session: SQLAlchemy async session
            employee_id: Employee this belief system belongs to
            tenant_id: Tenant ID for multi-tenancy
            llm_service: LLM service for belief extraction from observations
        """
        self.session = session
        self.employee_id = employee_id
        self.tenant_id = tenant_id
        self._llm_service = llm_service

    async def update_beliefs(
        self,
        observations: list["Observation"],
        identity_context: str | None = None,
    ) -> list[BeliefChangeResult]:
        """
        Update beliefs based on a list of observations.

        This is the batch interface used by the ProactiveExecutionLoop.
        It extracts beliefs from each observation using the LLM service.

        Args:
            observations: List of observations from perception phase
            identity_context: Optional identity system prompt (name, role,
                personality, goals) prepended to the LLM prompt for
                personalized belief extraction.

        Returns:
            List of BeliefChangeResult objects indicating what beliefs changed
        """
        logger.debug(
            f"update_beliefs called with {len(observations)} observations",
            extra={
                "employee_id": str(self.employee_id),
                "observation_count": len(observations),
            },
        )

        all_changes: list[BeliefChangeResult] = []

        # Separate structured vs unstructured observations
        structured_obs: list[Observation] = []
        unstructured_obs: list[Observation] = []

        for obs in observations:
            tool_result = obs.content.get("tool_result") if isinstance(obs.content, dict) else None
            # MCP tools may return JSON strings — try parsing them
            if isinstance(tool_result, str):
                try:
                    import json

                    parsed = json.loads(tool_result)
                    if isinstance(parsed, dict):
                        obs.content["tool_result"] = parsed
                        tool_result = parsed
                except (json.JSONDecodeError, TypeError):
                    pass
            if isinstance(tool_result, dict):
                structured_obs.append(obs)
            else:
                unstructured_obs.append(obs)

        # Direct tool-to-belief mapping for structured data (no LLM needed)
        for obs in structured_obs:
            try:
                tool_result = obs.content["tool_result"]
                results = await self._map_structured_to_beliefs(obs.source, tool_result)
                for result in results:
                    belief = result.belief
                    importance = min(1.0, (obs.priority / 10.0) * belief.confidence)
                    old_conf = result.old_confidence
                    all_changes.append(
                        BeliefChangeResult(
                            subject=belief.subject,
                            predicate=belief.predicate,
                            importance=importance,
                            old_confidence=old_conf if old_conf is not None else 0.0,
                            new_confidence=belief.confidence,
                            belief=belief,
                        )
                    )
            except Exception as e:
                logger.warning(
                    "Direct belief mapping failed for %s, will use LLM: %s",
                    obs.observation_type,
                    e,
                    extra={"employee_id": str(self.employee_id)},
                )
                unstructured_obs.append(obs)

        # Batch LLM extraction for unstructured observations (single LLM call)
        if unstructured_obs and self._llm_service:
            try:
                update_results = await self._batch_extract_beliefs(
                    unstructured_obs, self._llm_service, identity_context
                )
                for obs, result in update_results:
                    belief = result.belief
                    importance = min(1.0, (obs.priority / 10.0) * belief.confidence)
                    old_conf = result.old_confidence
                    all_changes.append(
                        BeliefChangeResult(
                            subject=belief.subject,
                            predicate=belief.predicate,
                            importance=importance,
                            old_confidence=old_conf if old_conf is not None else 0.0,
                            new_confidence=belief.confidence,
                            belief=belief,
                        )
                    )
            except Exception as e:
                logger.warning(
                    "Batch belief extraction failed: %s",
                    e,
                    exc_info=True,
                    extra={"employee_id": str(self.employee_id)},
                )

        logger.info(
            "Extracted %d beliefs from %d observations (%d structured, %d via LLM)",
            len(all_changes),
            len(observations),
            len(structured_obs),
            len(unstructured_obs),
            extra={
                "employee_id": str(self.employee_id),
                "belief_count": len(all_changes),
                "observation_count": len(observations),
                "structured_count": len(structured_obs),
                "llm_count": len(unstructured_obs),
            },
        )

        return all_changes

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
        belief_object: dict[str, Any],
        confidence: float,
        source: str,
        belief_type: str = "state",
        evidence: list[UUID] | None = None,
        decay_rate: float = 0.1,
    ) -> BeliefUpdateResult:
        """
        Update or create a belief.

        This implements belief revision:
        - If belief exists: update value, adjust confidence, add evidence
        - If belief is new: create with given confidence
        - Record change in belief history

        Args:
            subject: What the belief is about (e.g., "Acme Corp")
            predicate: Property or relation (e.g., "pipeline_health")
            belief_object: Value (can be text, number, boolean, or complex object)
            confidence: Confidence level (0-1)
            source: How belief was formed (observation, inference, told_by_human, prior)
            belief_type: Type of belief (state, event, causal, evaluative)
            evidence: Supporting observations (episodic memory UUIDs)
            decay_rate: Linear decay per day (0-1)

        Returns:
            BeliefUpdateResult containing the belief and metadata about the update

        Example:
            >>> result = await belief_system.update_belief(
            ...     subject="Acme Corp",
            ...     predicate="deal_stage",
            ...     belief_object={"stage": "negotiation", "amount": 50000},
            ...     confidence=0.9,
            ...     source="observation"
            ... )
            >>> belief = result.belief
            >>> was_new = result.was_created
        """
        # Get existing belief if any
        existing = await self.get_belief(subject, predicate)

        if existing:
            # Update existing belief
            old_value = existing.object
            old_confidence = existing.confidence

            # Update belief
            existing.object = belief_object
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
                new_value=belief_object,
                old_confidence=old_confidence,
                new_confidence=confidence,
                reason=f"Updated from {source}",
            )

            return BeliefUpdateResult(
                belief=existing,
                old_confidence=old_confidence,
                was_created=False,
            )

        # Create new belief
        # Convert UUIDs to strings for JSONB serialization
        belief = Belief(
            tenant_id=self.tenant_id,
            employee_id=self.employee_id,
            belief_type=belief_type,
            subject=subject,
            predicate=predicate,
            object=belief_object,
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
            new_value=belief_object,
            old_confidence=None,
            new_confidence=confidence,
            reason=f"Created from {source}",
        )

        return BeliefUpdateResult(
            belief=belief,
            old_confidence=None,
            was_created=True,
        )

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

    async def _map_structured_to_beliefs(
        self,
        source_name: str,
        data: dict[str, Any],
    ) -> list[BeliefUpdateResult]:
        """Map structured tool output directly to beliefs without LLM.

        For tools that return structured data (CRM metrics, calendar events),
        we can create beliefs directly from the key-value pairs.
        """
        results: list[BeliefUpdateResult] = []
        for key, value in data.items():
            if key.startswith("_") or key in ("id", "tenant_id"):
                continue
            if isinstance(value, (str, int, float, bool)):
                obj = {"value": value}
            elif isinstance(value, dict):
                obj = value
            elif isinstance(value, list) and len(value) <= 10:
                obj = {"items": value, "count": len(value)}
            else:
                continue

            result = await self.update_belief(
                subject=source_name,
                predicate=key,
                belief_object=obj,
                confidence=1.0,
                source="observation",
                belief_type="state",
            )
            results.append(result)
        return results

    async def _batch_extract_beliefs(
        self,
        observations: list["Observation"],
        llm_service: "LLMService",
        identity_context: str | None = None,
    ) -> list[tuple["Observation", BeliefUpdateResult]]:
        """Extract beliefs from multiple observations in a single LLM call.

        Instead of one LLM call per observation, batches all observations
        into a single prompt for extraction.
        """
        if not observations:
            return []

        # If only one observation, use the existing method
        if len(observations) == 1:
            results = await self.extract_beliefs_from_observation(
                observations[0], llm_service, identity_context
            )
            return [(observations[0], r) for r in results]

        # Build batched prompt
        obs_texts = []
        for i, obs in enumerate(observations):
            obs_texts.append(
                f"--- Observation {i + 1} ---\n"
                f"Type: {obs.observation_type}\n"
                f"Source: {obs.source}\n"
                f"Content:\n{self._format_observation_content(obs.content)}"
            )
        all_obs_text = "\n\n".join(obs_texts)

        base_instructions = """Extract structured beliefs from ALL the observations below in Subject-Predicate-Object format.

Guidelines:
1. Extract FACTUAL beliefs only (not assumptions or speculation)
2. Use clear, specific subjects (company names, person names, project names)
3. Use consistent predicates (deal_stage, sentiment, priority, next_action, etc.)
4. Provide structured objects (use dicts with relevant fields)
5. Assign confidence based on observation strength (0.0-1.0)

IMPORTANT: Extract BUSINESS-RELEVANT beliefs only. Do NOT extract beliefs about
tool names, function calls, API arguments, or execution metadata.

Belief types: state, event, causal, evaluative"""

        system_prompt = (
            f"{identity_context}\n\n{base_instructions}"
            if identity_context
            else f"You are a digital employee.\n\n{base_instructions}"
        )

        user_prompt = f"""{all_obs_text}

Extract all relevant beliefs from these {len(observations)} observations. Focus on actionable information."""

        try:
            _, extraction_result_base = await llm_service.generate_structured(
                prompt=user_prompt,
                system=system_prompt,
                response_format=BeliefExtractionResult,
                temperature=0.3,
            )
            extraction_result: BeliefExtractionResult = extraction_result_base  # type: ignore[assignment]
        except Exception as e:
            logger.error(
                "Batch LLM belief extraction failed: %s",
                e,
                exc_info=True,
                extra={"employee_id": str(self.employee_id), "obs_count": len(observations)},
            )
            return []

        # Process extracted beliefs — assign to first observation as source
        paired_results: list[tuple[Observation, BeliefUpdateResult]] = []
        default_obs = observations[0]

        for extracted in extraction_result.beliefs:
            result = await self.update_belief(
                subject=extracted.subject,
                predicate=extracted.predicate,
                belief_object=extracted.object,
                confidence=extracted.confidence,
                source="observation",
                belief_type=extracted.belief_type,
                evidence=[default_obs.observation_id],
                decay_rate=0.1,
            )
            paired_results.append((default_obs, result))

        logger.info(
            "Batch belief extraction: %d observations → %d beliefs (1 LLM call)",
            len(observations),
            len(paired_results),
            extra={"employee_id": str(self.employee_id)},
        )

        return paired_results

    async def extract_beliefs_from_observation(
        self,
        observation: "Observation",
        llm_service: "LLMService",
        identity_context: str | None = None,
    ) -> list[BeliefUpdateResult]:
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
            identity_context: Optional identity system prompt prepended to
                the LLM prompt for personalized belief extraction.

        Returns:
            List of BeliefUpdateResult containing beliefs and update metadata

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
        base_instructions = """Extract structured beliefs from this observation in Subject-Predicate-Object format.

Guidelines:
1. Extract FACTUAL beliefs only (not assumptions or speculation)
2. Use clear, specific subjects (company names, person names, project names)
3. Use consistent predicates (deal_stage, sentiment, priority, next_action, etc.)
4. Provide structured objects (use dicts with relevant fields)
5. Assign confidence based on observation strength (0.0-1.0)
6. Explain your reasoning for each belief

IMPORTANT: Extract BUSINESS-RELEVANT beliefs only. Do NOT extract beliefs about:
- Tool names, function calls, API arguments, or execution metadata
- Internal system details (tool errors, MCP server names, function parameters)
- Timestamps or observation metadata
Focus on what the data MEANS for the business, not how it was retrieved.

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

        system_prompt = (
            f"{identity_context}\n\n{base_instructions}"
            if identity_context
            else f"You are a digital employee.\n\n{base_instructions}"
        )

        user_prompt = f"""Observation Type: {observation.observation_type}
Source: {observation.source}
Priority: {observation.priority}/10
Timestamp: {observation.timestamp.isoformat()}

Content:
{self._format_observation_content(observation.content)}

Extract all relevant beliefs from this observation. Focus on actionable information that would help the employee make decisions."""

        # Use LLM to extract beliefs with error handling
        try:
            _, extraction_result_base = await llm_service.generate_structured(
                prompt=user_prompt,
                system=system_prompt,
                response_format=BeliefExtractionResult,
                temperature=0.3,  # Lower temperature for more consistent extraction
            )
            # Type assertion since generate_structured returns BaseModel
            extraction_result: BeliefExtractionResult = extraction_result_base  # type: ignore[assignment]
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
        update_results: list[BeliefUpdateResult] = []

        for extracted in extraction_result.beliefs:
            # Create or update belief using existing update_belief method
            # Use "observation" as source since these beliefs are extracted from observations
            result = await self.update_belief(
                subject=extracted.subject,
                predicate=extracted.predicate,
                belief_object=extracted.object,
                confidence=extracted.confidence,
                source="observation",
                belief_type=extracted.belief_type,
                evidence=[observation.observation_id],
                decay_rate=0.1,  # Default decay rate
            )

            update_results.append(result)

        # Update observation to mark as processed
        # Note: This is done by the caller (ProactiveLoop) to avoid circular dependencies

        return update_results

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
