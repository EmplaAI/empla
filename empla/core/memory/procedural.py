"""
empla.core.memory.procedural - Procedural Memory System

Procedural Memory stores skills, workflows, and learned behaviors:
- How to execute common tasks
- What approaches work for different situations
- Learned workflows from observation
- Success/failure patterns
- Behavioral templates

Key characteristics:
- Action-oriented (stores HOW, not WHAT)
- Context-dependent (different procedures for different situations)
- Reinforcement-based (success strengthens, failure weakens)
- Transferable (procedures learned in one context apply to similar contexts)
- Continuously refined (improves with every execution)
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.memory import ProceduralMemory


class ProceduralMemorySystem:
    """
    Procedural Memory System - Skills and workflows.

    Manages an employee's procedural knowledge - learned workflows,
    behavioral patterns, and action sequences that achieve specific goals.
    Each procedure tracks success/failure to continuously improve.

    Example:
        >>> procedural = ProceduralMemorySystem(session, employee_id, tenant_id)
        >>> # Record a successful workflow
        >>> procedure = await procedural.record_procedure(
        ...     procedure_type="workflow",
        ...     name="Qualify high-value lead",
        ...     trigger_conditions={"lead_score": ">80", "company_size": ">500"},
        ...     steps=[
        ...         {"action": "research_company", "duration": "15min"},
        ...         {"action": "personalize_outreach", "duration": "10min"},
        ...         {"action": "send_email", "template": "enterprise_intro"}
        ...     ],
        ...     outcome="meeting_booked",
        ...     success=True
        ... )
    """

    def __init__(
        self,
        session: AsyncSession,
        employee_id: UUID,
        tenant_id: UUID,
    ) -> None:
        """
        Initialize ProceduralMemorySystem.

        Args:
            session: SQLAlchemy async session
            employee_id: Employee this procedural memory belongs to
            tenant_id: Tenant ID for multi-tenancy
        """
        self.session = session
        self.employee_id = employee_id
        self.tenant_id = tenant_id

    async def record_procedure(
        self,
        procedure_type: str,
        name: str,
        steps: list[dict[str, Any]],
        trigger_conditions: dict[str, Any] | None = None,
        outcome: str | None = None,
        success: bool = True,
        execution_time: float | None = None,
        context: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> ProceduralMemory:
        """
        Record a new procedure or update existing one.

        When recording a procedure that matches an existing one (same name
        and trigger conditions), this updates the existing procedure's
        success rate and execution statistics.

        Args:
            procedure_type: Type (workflow, tactic, behavior, template)
            name: Descriptive name
            steps: Sequence of actions/steps
            trigger_conditions: When to use this procedure
            outcome: What happened after execution
            success: Whether execution succeeded
            execution_time: How long it took (seconds)
            context: Additional context
            embedding: Pre-computed embedding

        Returns:
            Created or updated ProceduralMemory

        Example:
            >>> # First execution - creates new procedure
            >>> proc = await procedural.record_procedure(
            ...     procedure_type="workflow",
            ...     name="Research competitor",
            ...     trigger_conditions={"task_type": "competitor_research"},
            ...     steps=[
            ...         {"action": "search_web", "query": "{competitor_name}"},
            ...         {"action": "analyze_website"},
            ...         {"action": "summarize_findings"}
            ...     ],
            ...     success=True,
            ...     execution_time=120.5
            ... )
            >>>
            >>> # Second execution - updates existing procedure
            >>> proc = await procedural.record_procedure(
            ...     procedure_type="workflow",
            ...     name="Research competitor",
            ...     trigger_conditions={"task_type": "competitor_research"},
            ...     steps=[...],  # Same steps
            ...     success=True,
            ...     execution_time=95.2  # Faster this time
            ... )
            >>> # Now: execution_count=2, success_rate updates, avg_execution_time updates
        """
        # Check if procedure already exists
        existing = await self.get_procedure_by_name_and_conditions(
            name=name,
            trigger_conditions=trigger_conditions,
        )

        if existing:
            # Update existing procedure with new execution data
            existing.execution_count += 1
            if success:
                existing.success_count += 1

            # Update success rate
            existing.success_rate = existing.success_count / existing.execution_count

            # Update average execution time
            if execution_time is not None:
                if existing.avg_execution_time is None:
                    existing.avg_execution_time = execution_time
                else:
                    # Incremental average
                    total_time = existing.avg_execution_time * (existing.execution_count - 1)
                    existing.avg_execution_time = (
                        total_time + execution_time
                    ) / existing.execution_count

            # Update last execution
            existing.last_executed_at = datetime.now(UTC)
            existing.updated_at = datetime.now(UTC)

            # Optionally update steps if they've evolved
            existing.steps = steps

            # Store outcome in context
            if outcome:
                updated_context = dict(existing.context or {})
                outcomes = updated_context.get("outcomes", [])
                outcomes.append(
                    {
                        "outcome": outcome,
                        "success": success,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "execution_time": execution_time,
                    }
                )
                # Keep only last 10 outcomes
                updated_context["outcomes"] = outcomes[-10:]
                existing.context = updated_context

            await self.session.flush()
            return existing

        # Create new procedure
        procedure = ProceduralMemory(
            tenant_id=self.tenant_id,
            employee_id=self.employee_id,
            procedure_type=procedure_type,
            name=name,
            description="",  # Empty description, can be updated later
            steps=steps,  # Store list directly in JSONB
            trigger_conditions=trigger_conditions or {},
            context=context or {},
            embedding=embedding,
            execution_count=1,
            success_count=1 if success else 0,
            success_rate=1.0 if success else 0.0,
            avg_execution_time=execution_time,
            last_executed_at=datetime.now(UTC),
        )

        # Store initial outcome
        if outcome:
            procedure.context["outcomes"] = [
                {
                    "outcome": outcome,
                    "success": success,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "execution_time": execution_time,
                }
            ]

        self.session.add(procedure)
        await self.session.flush()

        return procedure

    async def get_procedure_by_name_and_conditions(
        self,
        name: str,
        trigger_conditions: dict[str, Any] | None = None,
    ) -> ProceduralMemory | None:
        """
        Get a specific procedure by name and trigger conditions.

        Args:
            name: Procedure name
            trigger_conditions: Trigger conditions to match

        Returns:
            ProceduralMemory if found, None otherwise

        Note:
            This matches procedures with identical trigger_conditions.
            For similarity-based matching, use search_similar_procedures().
        """
        # Use JSONB containment to match trigger conditions
        # This finds procedures where stored conditions match provided ones
        query = select(ProceduralMemory).where(
            ProceduralMemory.employee_id == self.employee_id,
            ProceduralMemory.tenant_id == self.tenant_id,
            ProceduralMemory.name == name,
            ProceduralMemory.deleted_at.is_(None),
        )

        if trigger_conditions:
            # PostgreSQL JSONB @> operator (contains)
            query = query.where(text("trigger_conditions @> :conditions")).params(
                conditions=json.dumps(trigger_conditions)
            )

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def find_procedures_for_situation(
        self,
        situation: dict[str, Any],
        procedure_type: str | None = None,
        min_success_rate: float = 0.5,
        limit: int = 5,
    ) -> list[ProceduralMemory]:
        """
        Find procedures applicable to a given situation.

        Matches procedures whose trigger_conditions are satisfied by the
        current situation. Returns procedures sorted by success rate.

        Args:
            situation: Current situation/context
            procedure_type: Filter by procedure type
            min_success_rate: Minimum success rate threshold
            limit: Maximum number of procedures to return

        Returns:
            List of applicable procedures, sorted by success rate (highest first)

        Example:
            >>> # Find procedures for qualifying a lead
            >>> situation = {
            ...     "task_type": "lead_qualification",
            ...     "lead_score": 85,
            ...     "company_size": 750
            ... }
            >>> procedures = await procedural.find_procedures_for_situation(
            ...     situation=situation,
            ...     min_success_rate=0.7
            ... )
            >>> # Returns procedures that worked well in similar situations
        """
        # Build base query
        query = select(ProceduralMemory).where(
            ProceduralMemory.employee_id == self.employee_id,
            ProceduralMemory.tenant_id == self.tenant_id,
            ProceduralMemory.success_rate >= min_success_rate,
            ProceduralMemory.deleted_at.is_(None),
        )

        if procedure_type:
            query = query.where(ProceduralMemory.procedure_type == procedure_type)

        # For now, we retrieve all matching procedures and filter in Python
        # In production, could use PostgreSQL jsonpath for more sophisticated matching
        result = await self.session.execute(query.order_by(ProceduralMemory.success_rate.desc()))

        all_procedures = list(result.scalars().all())

        # Filter to procedures whose trigger conditions match situation
        applicable = []
        for proc in all_procedures:
            if self._conditions_match_situation(proc.trigger_conditions, situation):
                applicable.append(proc)

            if len(applicable) >= limit:
                break

        return applicable

    def _conditions_match_situation(
        self,
        conditions: dict[str, Any],
        situation: dict[str, Any],
    ) -> bool:
        """
        Check if trigger conditions are satisfied by situation.

        This is a simple implementation. Production could support:
        - Comparison operators (>, <, >=, <=, !=)
        - Logical operators (AND, OR, NOT)
        - Pattern matching (regex, wildcards)
        - Range checks (between, in)

        Args:
            conditions: Procedure trigger conditions
            situation: Current situation

        Returns:
            True if conditions are satisfied, False otherwise
        """
        if not conditions:
            # No conditions = always applicable
            return True

        # Check if all condition keys exist in situation with matching values
        for key, value in conditions.items():
            if key not in situation:
                return False

            # Simple equality check for now
            # Could be extended to support operators like ">80", "in [a,b,c]", etc.
            if isinstance(value, str) and value.startswith(">"):
                # Simple > operator support
                threshold = float(value[1:])
                if not (isinstance(situation[key], (int, float)) and situation[key] > threshold):
                    return False
            elif isinstance(value, str) and value.startswith("<"):
                # Simple < operator support
                threshold = float(value[1:])
                if not (isinstance(situation[key], (int, float)) and situation[key] < threshold):
                    return False
            elif situation[key] != value:
                return False

        return True

    async def search_similar_procedures(
        self,
        query_embedding: list[float],
        procedure_type: str | None = None,
        limit: int = 10,
        similarity_threshold: float = 0.7,
    ) -> list[ProceduralMemory]:
        """
        Search for procedures similar to query embedding.

        Uses pgvector cosine similarity to find semantically similar procedures.

        Args:
            query_embedding: Vector embedding of query/situation
            procedure_type: Optional procedure type filter
            limit: Maximum number of procedures to return
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of similar procedures, sorted by similarity

        Example:
            >>> # Find procedures similar to "how to handle objection"
            >>> query_emb = await generate_embedding("handle pricing objection")
            >>> procedures = await procedural.search_similar_procedures(
            ...     query_embedding=query_emb,
            ...     procedure_type="tactic",
            ...     limit=5
            ... )
        """
        query = select(ProceduralMemory).where(
            ProceduralMemory.employee_id == self.employee_id,
            ProceduralMemory.tenant_id == self.tenant_id,
            ProceduralMemory.deleted_at.is_(None),
            ProceduralMemory.embedding.is_not(None),
            text("1 - (embedding <=> :query_emb) >= :threshold"),
        )

        if procedure_type:
            query = query.where(ProceduralMemory.procedure_type == procedure_type)

        result = await self.session.execute(
            query.params(
                query_emb=str(query_embedding),
                threshold=similarity_threshold,
            )
            .order_by(text("embedding <=> :query_emb"))
            .limit(limit)
        )

        return list(result.scalars().all())

    async def get_best_procedures(
        self,
        procedure_type: str | None = None,
        min_executions: int = 3,
        limit: int = 10,
    ) -> list[ProceduralMemory]:
        """
        Get the best-performing procedures.

        Returns procedures with highest success rates that have been
        executed enough times to be statistically meaningful.

        Args:
            procedure_type: Optional procedure type filter
            min_executions: Minimum execution count
            limit: Maximum number of procedures to return

        Returns:
            List of best procedures, sorted by success rate

        Example:
            >>> # Get best workflows
            >>> best = await procedural.get_best_procedures(
            ...     procedure_type="workflow",
            ...     min_executions=5,
            ...     limit=10
            ... )
        """
        query = select(ProceduralMemory).where(
            ProceduralMemory.employee_id == self.employee_id,
            ProceduralMemory.tenant_id == self.tenant_id,
            ProceduralMemory.execution_count >= min_executions,
            ProceduralMemory.deleted_at.is_(None),
        )

        if procedure_type:
            query = query.where(ProceduralMemory.procedure_type == procedure_type)

        result = await self.session.execute(
            query.order_by(
                ProceduralMemory.success_rate.desc(),
                ProceduralMemory.execution_count.desc(),
            ).limit(limit)
        )

        return list(result.scalars().all())

    async def update_procedure_embedding(
        self,
        procedure_id: UUID,
        embedding: list[float],
    ) -> ProceduralMemory | None:
        """
        Update embedding for a procedure.

        Args:
            procedure_id: Procedure UUID
            embedding: New embedding vector

        Returns:
            Updated ProceduralMemory, or None if not found
        """
        result = await self.session.execute(
            select(ProceduralMemory).where(
                ProceduralMemory.id == procedure_id,
                ProceduralMemory.employee_id == self.employee_id,
                ProceduralMemory.tenant_id == self.tenant_id,
                ProceduralMemory.deleted_at.is_(None),
            )
        )
        procedure = result.scalar_one_or_none()

        if not procedure:
            return None

        procedure.embedding = embedding
        procedure.updated_at = datetime.now(UTC)

        await self.session.flush()
        return procedure

    async def archive_poor_procedures(
        self,
        max_success_rate: float = 0.3,
        min_executions: int = 5,
    ) -> int:
        """
        Archive (soft delete) procedures with poor success rates.

        Only archives procedures that have been executed enough times
        to have statistically meaningful failure rates.

        Args:
            max_success_rate: Maximum success rate to qualify for archival
            min_executions: Minimum executions before archiving

        Returns:
            Number of procedures archived

        Example:
            >>> # Archive procedures that fail >70% of the time
            >>> count = await procedural.archive_poor_procedures(
            ...     max_success_rate=0.3,
            ...     min_executions=5
            ... )
        """
        now = datetime.now(UTC)

        result = await self.session.execute(
            select(ProceduralMemory).where(
                ProceduralMemory.employee_id == self.employee_id,
                ProceduralMemory.tenant_id == self.tenant_id,
                ProceduralMemory.success_rate < max_success_rate,
                ProceduralMemory.execution_count >= min_executions,
                ProceduralMemory.deleted_at.is_(None),
            )
        )

        procedures = list(result.scalars().all())
        count = 0

        for procedure in procedures:
            procedure.deleted_at = now
            count += 1

        await self.session.flush()
        return count

    async def reinforce_successful_procedures(
        self,
        min_success_rate: float = 0.8,
        min_executions: int = 5,
    ) -> int:
        """
        Reinforce successful procedures by marking them for prioritization.

        Updates context to indicate these are proven procedures that should
        be preferred in future decisions.

        Args:
            min_success_rate: Minimum success rate to qualify
            min_executions: Minimum executions to be statistically significant

        Returns:
            Number of procedures reinforced

        Example:
            >>> # Mark highly successful procedures
            >>> count = await procedural.reinforce_successful_procedures(
            ...     min_success_rate=0.85,
            ...     min_executions=10
            ... )
        """
        result = await self.session.execute(
            select(ProceduralMemory).where(
                ProceduralMemory.employee_id == self.employee_id,
                ProceduralMemory.tenant_id == self.tenant_id,
                ProceduralMemory.success_rate >= min_success_rate,
                ProceduralMemory.execution_count >= min_executions,
                ProceduralMemory.deleted_at.is_(None),
            )
        )

        procedures = list(result.scalars().all())
        count = 0

        for procedure in procedures:
            updated_context = dict(procedure.context or {})
            updated_context["proven"] = True
            updated_context["reinforced_at"] = datetime.now(UTC).isoformat()
            procedure.context = updated_context
            count += 1

        await self.session.flush()
        return count

    async def get_procedure(self, procedure_id: UUID) -> ProceduralMemory | None:
        """
        Get a specific procedure by ID.

        Args:
            procedure_id: Procedure UUID

        Returns:
            ProceduralMemory if found, None otherwise
        """
        result = await self.session.execute(
            select(ProceduralMemory).where(
                ProceduralMemory.id == procedure_id,
                ProceduralMemory.employee_id == self.employee_id,
                ProceduralMemory.tenant_id == self.tenant_id,
                ProceduralMemory.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_procedures_by_type(
        self,
        procedure_type: str,
        limit: int = 50,
    ) -> list[ProceduralMemory]:
        """
        Get all procedures of a specific type.

        Args:
            procedure_type: Procedure type
            limit: Maximum number of procedures

        Returns:
            List of procedures, ordered by success rate

        Example:
            >>> # Get all tactics
            >>> tactics = await procedural.get_procedures_by_type("tactic")
        """
        result = await self.session.execute(
            select(ProceduralMemory)
            .where(
                ProceduralMemory.employee_id == self.employee_id,
                ProceduralMemory.tenant_id == self.tenant_id,
                ProceduralMemory.procedure_type == procedure_type,
                ProceduralMemory.deleted_at.is_(None),
            )
            .order_by(ProceduralMemory.success_rate.desc())
            .limit(limit)
        )

        return list(result.scalars().all())
