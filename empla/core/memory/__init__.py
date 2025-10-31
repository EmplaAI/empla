"""
empla.core.memory - Memory Systems

Multi-layered memory architecture for autonomous digital employees:

- **Episodic Memory**: Personal experiences and events
  - Email conversations, meeting interactions, observations
  - Temporal retrieval, similarity search (pgvector)
  - Importance-weighted, decay over time

- **Semantic Memory**: General knowledge and facts
  - SPO triples (Subject-Predicate-Object)
  - Domain knowledge, entity relationships
  - Graph-structured, confidence-weighted

- **Procedural Memory**: Skills and workflows
  - How to execute tasks, learned behaviors
  - Success/failure tracking, reinforcement learning
  - Context-dependent procedure selection

- **Working Memory**: Current context and active information
  - Limited capacity (7±2 items)
  - Temporary storage for active tasks/goals
  - Fast access, automatic expiration

Design Philosophy:
- Inspired by human memory systems
- Optimized for autonomous operation
- Enables learning and improvement
- Multi-tenant by default
- Production-ready persistence

Example:
    >>> from empla.core.memory import (
    ...     EpisodicMemorySystem,
    ...     SemanticMemorySystem,
    ...     ProceduralMemorySystem,
    ...     WorkingMemory
    ... )
    >>>
    >>> # Initialize memory systems for an employee
    >>> episodic = EpisodicMemorySystem(session, employee_id, tenant_id)
    >>> semantic = SemanticMemorySystem(session, employee_id, tenant_id)
    >>> procedural = ProceduralMemorySystem(session, employee_id, tenant_id)
    >>> working = WorkingMemory(session, employee_id, tenant_id)
    >>>
    >>> # Record an experience
    >>> memory = await episodic.record_episode(
    ...     episode_type="interaction",
    ...     description="Email discussion with Acme Corp CEO about pricing",
    ...     content={"email_thread": [...], "key_points": [...]},
    ...     participants=["ceo@acmecorp.com"],
    ...     importance=0.8
    ... )
    >>>
    >>> # Extract knowledge
    >>> fact = await semantic.store_fact(
    ...     subject="Acme Corp",
    ...     predicate="interested_in",
    ...     object="Enterprise plan",
    ...     confidence=0.9,
    ...     source_id=memory.id
    ... )
    >>>
    >>> # Learn a procedure
    >>> procedure = await procedural.record_procedure(
    ...     procedure_type="workflow",
    ...     name="Enterprise sales qualification",
    ...     steps=[...],
    ...     success=True
    ... )
    >>>
    >>> # Track current context
    >>> await working.add_item(
    ...     item_type="task",
    ...     content={"task": "Follow up with Acme Corp", "deadline": "2024-10-30"},
    ...     importance=0.9
    ... )
"""

from empla.core.memory.episodic import EpisodicMemorySystem
from empla.core.memory.procedural import ProceduralMemorySystem
from empla.core.memory.semantic import SemanticMemorySystem
from empla.core.memory.working import WorkingMemory

__all__ = [
    "EpisodicMemorySystem",
    "ProceduralMemorySystem",
    "SemanticMemorySystem",
    "WorkingMemory",
]
