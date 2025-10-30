"""
Integration tests for Memory Systems.

Tests all four memory types (Episodic, Semantic, Procedural, Working)
with real database interactions.
"""

import pytest
from datetime import datetime, timedelta
from uuid import UUID

from empla.core.memory import (
    EpisodicMemorySystem,
    SemanticMemorySystem,
    ProceduralMemorySystem,
    WorkingMemory,
)
from empla.models.database import get_engine, get_sessionmaker
from empla.models.employee import Employee
from empla.models.tenant import Tenant, User
from sqlalchemy import event


@pytest.fixture
async def session():
    """
    Create a test database session with proper transaction isolation.

    Uses nested savepoints to ensure test commits don't release the outer transaction.
    After each commit, automatically creates a new nested savepoint to maintain isolation.
    """
    engine = get_engine(echo=False)

    # Acquire a persistent connection
    conn = await engine.connect()

    # Begin a top-level transaction
    trans = await conn.begin()

    # Create session bound to this connection
    sessionmaker = get_sessionmaker(engine)
    session = sessionmaker(bind=conn)

    # Start an initial nested savepoint
    nested = await conn.begin_nested()

    # Register after_commit hook to re-create nested savepoint
    @event.listens_for(session.sync_session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        """Re-create a nested savepoint after each commit."""
        if transaction.nested and not transaction._parent.nested:
            # This was a commit of the nested savepoint
            # Create a new nested savepoint for the next test operation
            conn.sync_connection.begin_nested()

    yield session

    # Teardown: rollback everything
    await session.close()

    # Rollback the nested savepoint if still active
    if nested.is_active:
        await nested.rollback()

    # Rollback the top-level transaction
    if trans.is_active:
        await trans.rollback()

    # Close and dispose
    await conn.close()
    await engine.dispose()


@pytest.fixture
async def tenant(session):
    """Create a test tenant with unique slug."""
    import uuid

    tenant = Tenant(
        name="Test Corp",
        slug=f"test-{uuid.uuid4().hex[:8]}",  # Unique slug for each test
        status="active",
    )
    session.add(tenant)
    await session.flush()
    return tenant


@pytest.fixture
async def user(session, tenant):
    """Create a test user."""
    user = User(
        tenant_id=tenant.id,
        email="test@test.com",
        name="Test User",
        role="admin",
    )
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
async def employee(session, tenant, user):
    """Create a test employee."""
    employee = Employee(
        tenant_id=tenant.id,
        name="Test Employee",
        role="sales_ae",
        email="employee@test.com",
        status="active",
        lifecycle_stage="autonomous",
        created_by=user.id,
    )
    session.add(employee)
    await session.flush()
    return employee


# ====================
# Episodic Memory Tests
# ====================


@pytest.mark.asyncio
async def test_episodic_memory_record_and_recall(session, employee, tenant):
    """Test recording and recalling episodic memories."""
    episodic = EpisodicMemorySystem(session, employee.id, tenant.id)

    # Record an episode
    memory = await episodic.record_episode(
        episode_type="interaction",
        description="Email discussion with Acme Corp CEO",
        content={
            "from": "ceo@acmecorp.com",
            "subject": "Interested in Enterprise plan",
            "body": "We'd like to discuss pricing...",
        },
        participants=["ceo@acmecorp.com"],
        location="email",
        importance=0.8,
    )

    assert memory is not None
    assert memory.episode_type == "interaction"
    assert memory.description == "Email discussion with Acme Corp CEO"
    assert "ceo@acmecorp.com" in memory.participants
    assert memory.importance == 0.8

    await session.commit()


@pytest.mark.asyncio
async def test_episodic_memory_recall_recent(session, employee, tenant):
    """Test recalling recent episodic memories."""
    episodic = EpisodicMemorySystem(session, employee.id, tenant.id)

    # Record multiple episodes
    await episodic.record_episode(
        episode_type="interaction",
        description="Email 1",
        content={"body": "First email"},
        importance=0.5,
    )
    await episodic.record_episode(
        episode_type="interaction",
        description="Email 2",
        content={"body": "Second email"},
        importance=0.6,
    )
    await episodic.record_episode(
        episode_type="observation",
        description="Pipeline update",
        content={"pipeline_coverage": 2.5},
        importance=0.7,
    )

    # Recall recent memories
    recent = await episodic.recall_recent(days=7)
    assert len(recent) == 3

    # Filter by type
    interactions = await episodic.recall_recent(days=7, episode_type="interaction")
    assert len(interactions) == 2
    assert all(m.episode_type == "interaction" for m in interactions)

    await session.commit()


@pytest.mark.asyncio
async def test_episodic_memory_recall_with_participant(session, employee, tenant):
    """Test recalling memories involving a specific participant."""
    episodic = EpisodicMemorySystem(session, employee.id, tenant.id)

    # Record episodes with different participants
    await episodic.record_episode(
        episode_type="interaction",
        description="Email with Acme Corp",
        content={"body": "Discussion"},
        participants=["ceo@acmecorp.com"],
    )
    await episodic.record_episode(
        episode_type="interaction",
        description="Email with Beta Inc",
        content={"body": "Another discussion"},
        participants=["contact@betainc.com"],
    )
    await episodic.record_episode(
        episode_type="interaction",
        description="Follow-up with Acme Corp",
        content={"body": "Follow-up"},
        participants=["ceo@acmecorp.com"],
    )

    # Recall memories with specific participant
    acme_memories = await episodic.recall_with_participant("ceo@acmecorp.com")
    assert len(acme_memories) == 2
    assert all("ceo@acmecorp.com" in m.participants for m in acme_memories)

    await session.commit()


# ===================
# Semantic Memory Tests
# ===================


@pytest.mark.asyncio
async def test_semantic_memory_store_and_query(session, employee, tenant):
    """Test storing and querying semantic facts."""
    semantic = SemanticMemorySystem(session, employee.id, tenant.id)

    # Store a fact
    fact = await semantic.store_fact(
        subject="Acme Corp",
        predicate="industry",
        object="manufacturing",
        confidence=0.9,
    )

    assert fact is not None
    assert fact.subject == "Acme Corp"
    assert fact.predicate == "industry"
    assert fact.object == "manufacturing"
    assert fact.confidence == 0.9

    # Query facts
    retrieved = await semantic.get_fact("Acme Corp", "industry")
    assert retrieved.id == fact.id
    assert retrieved.object == "manufacturing"

    await session.commit()


@pytest.mark.asyncio
async def test_semantic_memory_update_existing(session, employee, tenant):
    """Test updating existing semantic facts."""
    semantic = SemanticMemorySystem(session, employee.id, tenant.id)

    # Store initial fact
    fact1 = await semantic.store_fact(
        subject="Acme Corp",
        predicate="deal_stage",
        object="negotiation",
        confidence=0.8,
    )

    # Update same fact
    fact2 = await semantic.store_fact(
        subject="Acme Corp",
        predicate="deal_stage",
        object="closed_won",
        confidence=0.95,
    )

    # Should be same fact, updated
    assert fact1.id == fact2.id
    assert fact2.object == "closed_won"
    assert fact2.confidence == 0.95
    assert fact2.access_count == 2  # Accessed twice (initial + update)

    await session.commit()


@pytest.mark.asyncio
async def test_semantic_memory_query_by_subject(session, employee, tenant):
    """Test querying all facts about a subject."""
    semantic = SemanticMemorySystem(session, employee.id, tenant.id)

    # Store multiple facts about same subject
    await semantic.store_fact(
        subject="Acme Corp",
        predicate="industry",
        object="manufacturing",
        confidence=0.9,
    )
    await semantic.store_fact(
        subject="Acme Corp",
        predicate="size",
        object={"employees": 500},
        confidence=0.85,
    )
    await semantic.store_fact(
        subject="Beta Inc",
        predicate="industry",
        object="tech",
        confidence=0.8,
    )

    # Query facts about Acme Corp
    acme_facts = await semantic.query_facts(subject="Acme Corp")
    assert len(acme_facts) == 2
    assert all(f.subject == "Acme Corp" for f in acme_facts)

    # Query all industry facts
    industry_facts = await semantic.query_facts(predicate="industry")
    assert len(industry_facts) == 2
    assert all(f.predicate == "industry" for f in industry_facts)

    await session.commit()


@pytest.mark.asyncio
async def test_semantic_memory_entity_summary(session, employee, tenant):
    """Test getting entity summary."""
    semantic = SemanticMemorySystem(session, employee.id, tenant.id)

    # Store multiple facts
    await semantic.store_fact(
        subject="Acme Corp",
        predicate="industry",
        object="manufacturing",
        confidence=0.9,
    )
    await semantic.store_fact(
        subject="Acme Corp",
        predicate="location",
        object="San Francisco",
        confidence=0.85,
    )
    await semantic.store_fact(
        subject="Acme Corp",
        predicate="deal_stage",
        object="negotiation",
        confidence=0.8,
    )

    # Get summary
    summary = await semantic.get_entity_summary("Acme Corp")
    assert summary["industry"] == "manufacturing"
    assert summary["location"] == "San Francisco"
    assert summary["deal_stage"] == "negotiation"

    await session.commit()


# =====================
# Procedural Memory Tests
# =====================


@pytest.mark.asyncio
async def test_procedural_memory_record_procedure(session, employee, tenant):
    """Test recording a procedure."""
    procedural = ProceduralMemorySystem(session, employee.id, tenant.id)

    # Record a successful procedure
    procedure = await procedural.record_procedure(
        procedure_type="workflow",
        name="Qualify high-value lead",
        steps=[
            {"action": "research_company", "duration": "15min"},
            {"action": "personalize_outreach", "duration": "10min"},
            {"action": "send_email", "template": "enterprise_intro"},
        ],
        trigger_conditions={"lead_score": ">80", "company_size": ">500"},
        outcome="meeting_booked",
        success=True,
        execution_time=120.5,
    )

    assert procedure is not None
    assert procedure.name == "Qualify high-value lead"
    assert len(procedure.steps) == 3
    assert procedure.execution_count == 1
    assert procedure.success_count == 1
    assert procedure.success_rate == 1.0
    assert procedure.avg_execution_time == 120.5

    await session.commit()


@pytest.mark.asyncio
async def test_procedural_memory_update_on_repeat(session, employee, tenant):
    """Test that repeating a procedure updates statistics."""
    procedural = ProceduralMemorySystem(session, employee.id, tenant.id)

    steps = [{"action": "step1"}, {"action": "step2"}]
    conditions = {"task_type": "test"}

    # First execution
    proc1 = await procedural.record_procedure(
        procedure_type="workflow",
        name="Test procedure",
        steps=steps,
        trigger_conditions=conditions,
        success=True,
        execution_time=100.0,
    )

    # Second execution
    proc2 = await procedural.record_procedure(
        procedure_type="workflow",
        name="Test procedure",
        steps=steps,
        trigger_conditions=conditions,
        success=True,
        execution_time=80.0,
    )

    # Should be same procedure, updated
    assert proc1.id == proc2.id
    assert proc2.execution_count == 2
    assert proc2.success_count == 2
    assert proc2.success_rate == 1.0
    assert proc2.avg_execution_time == 90.0  # (100 + 80) / 2

    # Third execution - failure
    proc3 = await procedural.record_procedure(
        procedure_type="workflow",
        name="Test procedure",
        steps=steps,
        trigger_conditions=conditions,
        success=False,
        execution_time=120.0,
    )

    assert proc3.id == proc1.id
    assert proc3.execution_count == 3
    assert proc3.success_count == 2
    assert proc3.success_rate == 2.0 / 3.0  # 66.67%
    assert proc3.avg_execution_time == 100.0  # (100 + 80 + 120) / 3

    await session.commit()


@pytest.mark.asyncio
async def test_procedural_memory_find_for_situation(session, employee, tenant):
    """Test finding procedures applicable to a situation."""
    procedural = ProceduralMemorySystem(session, employee.id, tenant.id)

    # Create procedures with different trigger conditions
    await procedural.record_procedure(
        procedure_type="workflow",
        name="High-value lead workflow",
        steps=[{"action": "research"}],
        trigger_conditions={"lead_score": ">80"},
        success=True,
    )
    await procedural.record_procedure(
        procedure_type="workflow",
        name="Low-value lead workflow",
        steps=[{"action": "auto_email"}],
        trigger_conditions={"lead_score": "<50"},
        success=True,
    )

    # Find procedures for high-value situation
    situation = {"lead_score": 85}
    procedures = await procedural.find_procedures_for_situation(situation)
    assert len(procedures) == 1
    assert procedures[0].name == "High-value lead workflow"

    await session.commit()


@pytest.mark.asyncio
async def test_procedural_memory_best_procedures(session, employee, tenant):
    """Test getting best-performing procedures."""
    procedural = ProceduralMemorySystem(session, employee.id, tenant.id)

    # Create procedures with different success rates
    # Good procedure (executed 5 times, 100% success)
    for _ in range(5):
        await procedural.record_procedure(
            procedure_type="workflow",
            name="Good workflow",
            steps=[{"action": "step"}],
            trigger_conditions={"type": "good"},
            success=True,
        )

    # Poor procedure (executed 5 times, 40% success)
    for i in range(5):
        await procedural.record_procedure(
            procedure_type="workflow",
            name="Poor workflow",
            steps=[{"action": "step"}],
            trigger_conditions={"type": "poor"},
            success=(i < 2),  # Only first 2 succeed
        )

    # Get best procedures
    best = await procedural.get_best_procedures(min_executions=3)
    assert len(best) >= 1
    assert best[0].name == "Good workflow"
    assert best[0].success_rate == 1.0

    await session.commit()


# ===================
# Working Memory Tests
# ===================


@pytest.mark.asyncio
async def test_working_memory_add_and_retrieve(session, employee, tenant):
    """Test adding and retrieving working memory items."""
    working = WorkingMemory(session, employee.id, tenant.id)

    # Add an item
    item = await working.add_item(
        item_type="task",
        content={"task": "Follow up with Acme Corp", "deadline": "2024-10-30"},
        importance=0.9,
        ttl_seconds=3600,
    )

    assert item is not None
    assert item.item_type == "task"
    assert item.content["task"] == "Follow up with Acme Corp"
    assert item.importance == 0.9

    # Retrieve active items
    items = await working.get_active_items()
    assert len(items) == 1
    assert items[0].id == item.id

    await session.commit()


@pytest.mark.asyncio
async def test_working_memory_capacity_enforcement(session, employee, tenant):
    """Test that working memory enforces capacity limits."""
    capacity = 3
    working = WorkingMemory(session, employee.id, tenant.id, capacity=capacity)

    # Add items up to capacity
    for i in range(capacity):
        await working.add_item(
            item_type="task",
            content={"task": f"Task {i}"},
            importance=0.5 + (i * 0.1),  # Increasing importance
        )

    items = await working.get_active_items()
    assert len(items) == capacity

    # Add one more - should evict least important
    await working.add_item(
        item_type="task",
        content={"task": "New important task"},
        importance=0.95,
    )

    items = await working.get_active_items()
    assert len(items) == capacity  # Still at capacity
    assert items[0].importance == 0.95  # Most important first

    await session.commit()


@pytest.mark.asyncio
async def test_working_memory_refresh(session, employee, tenant):
    """Test refreshing working memory items."""
    working = WorkingMemory(session, employee.id, tenant.id)

    # Add item with short TTL
    item = await working.add_item(
        item_type="task",
        content={"task": "Short-lived task"},
        importance=0.7,
        ttl_seconds=60,  # 1 minute
    )

    # Refresh it
    refreshed = await working.refresh_item(
        item_id=item.id,
        ttl_seconds=3600,  # Extend to 1 hour
        importance_boost=0.1,
    )

    assert refreshed is not None
    assert refreshed.importance == 0.8  # 0.7 + 0.1

    await session.commit()


@pytest.mark.asyncio
async def test_working_memory_context_summary(session, employee, tenant):
    """Test getting context summary."""
    working = WorkingMemory(session, employee.id, tenant.id)

    # Add various items
    await working.add_item(
        item_type="task",
        content={"task": "Task 1"},
        importance=0.9,
    )
    await working.add_item(
        item_type="task",
        content={"task": "Task 2"},
        importance=0.8,
    )
    await working.add_item(
        item_type="goal",
        content={"goal": "Close deals"},
        importance=0.95,
    )

    # Get summary
    summary = await working.get_context_summary()
    assert summary["total_items"] == 3
    assert "active_tasks" in summary
    assert len(summary["active_tasks"]) == 2
    assert "active_goals" in summary
    assert len(summary["active_goals"]) == 1

    await session.commit()


@pytest.mark.asyncio
async def test_working_memory_clear_by_type(session, employee, tenant):
    """Test clearing items by type."""
    working = WorkingMemory(session, employee.id, tenant.id)

    # Add mixed items
    await working.add_item(item_type="task", content={"task": "Task 1"}, importance=0.8)
    await working.add_item(item_type="task", content={"task": "Task 2"}, importance=0.7)
    await working.add_item(item_type="goal", content={"goal": "Goal 1"}, importance=0.9)

    # Clear all tasks
    count = await working.clear_by_type("task")
    assert count == 2

    # Only goal should remain
    items = await working.get_active_items()
    assert len(items) == 1
    assert items[0].item_type == "goal"

    await session.commit()


# ==========================
# Cross-Memory Integration Tests
# ==========================


@pytest.mark.asyncio
async def test_memory_systems_integration(session, employee, tenant):
    """
    Test integration between memory systems.

    Simulates a complete memory workflow:
    1. Record episodic memory (experience)
    2. Extract semantic knowledge (fact)
    3. Learn procedural pattern (workflow)
    4. Track in working memory (current context)
    """
    episodic = EpisodicMemorySystem(session, employee.id, tenant.id)
    semantic = SemanticMemorySystem(session, employee.id, tenant.id)
    procedural = ProceduralMemorySystem(session, employee.id, tenant.id)
    working = WorkingMemory(session, employee.id, tenant.id)

    # 1. Record episodic memory
    episode = await episodic.record_episode(
        episode_type="interaction",
        description="Successful enterprise sale to Acme Corp",
        content={
            "customer": "Acme Corp",
            "deal_size": 50000,
            "duration_days": 45,
            "key_steps": ["research", "demo", "proposal", "negotiation", "close"],
        },
        participants=["ceo@acmecorp.com"],
        importance=0.95,
    )

    # 2. Extract semantic knowledge
    fact = await semantic.store_fact(
        subject="Acme Corp",
        predicate="customer_type",
        object="enterprise",
        confidence=0.95,
        source_type="episodic",
        source_id=episode.id,
    )

    # 3. Learn procedural pattern
    procedure = await procedural.record_procedure(
        procedure_type="workflow",
        name="Enterprise sales workflow",
        steps=episode.content["key_steps"],
        trigger_conditions={"deal_size": ">40000"},
        success=True,
        execution_time=45 * 24 * 3600,  # 45 days in seconds
    )

    # 4. Add to working memory (current focus)
    working_item = await working.add_item(
        item_type="context",
        content={
            "recent_win": "Acme Corp",
            "workflow_learned": str(procedure.id),
        },
        importance=0.9,
        source_id=episode.id,
        source_type="episodic",
    )

    # Verify all connected
    assert episode.id is not None
    assert fact.source_id == episode.id
    assert procedure.name == "Enterprise sales workflow"
    assert working_item.source_id == episode.id

    # Query to verify learning
    # Can now find enterprise customers
    enterprise_facts = await semantic.query_facts(predicate="customer_type")
    assert len(enterprise_facts) > 0

    # Can find workflow for future large deals
    large_deal_situation = {"deal_size": 50000}
    applicable_procedures = await procedural.find_procedures_for_situation(
        large_deal_situation
    )
    assert len(applicable_procedures) > 0

    # Working memory has context
    context = await working.get_context_summary()
    assert context["total_items"] > 0

    await session.commit()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
