"""
Integration tests for BDI engine.

Tests the BeliefSystem, GoalSystem, and IntentionStack with real database.
"""

import pytest
from uuid import uuid4

from empla.bdi import BeliefSystem, GoalSystem, IntentionStack
from empla.models.database import get_engine, get_sessionmaker
from empla.models.employee import Employee
from empla.models.tenant import Tenant, User


@pytest.fixture
async def session():
    """Create a test database session with transaction rollback."""
    engine = get_engine(echo=False)
    sessionmaker = get_sessionmaker(engine)

    async with engine.begin() as conn:
        async with sessionmaker(bind=conn) as session:
            # Start a nested transaction
            nested = await conn.begin_nested()

            yield session

            # Rollback the nested transaction
            if nested.is_active:
                await nested.rollback()

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


@pytest.mark.asyncio
async def test_belief_system_basic(session, employee, tenant):
    """Test basic BeliefSystem operations."""
    beliefs = BeliefSystem(session, employee.id, tenant.id)

    # Add a belief
    belief = await beliefs.update_belief(
        subject="Acme Corp",
        predicate="deal_stage",
        object={"stage": "negotiation", "amount": 50000},
        confidence=0.9,
        source="observation",
    )

    assert belief is not None
    assert belief.subject == "Acme Corp"
    assert belief.predicate == "deal_stage"
    assert belief.confidence == 0.9

    # Update the belief
    updated = await beliefs.update_belief(
        subject="Acme Corp",
        predicate="deal_stage",
        object={"stage": "closed_won", "amount": 50000},
        confidence=0.95,
        source="observation",
    )

    assert updated.id == belief.id  # Same belief
    assert updated.object["stage"] == "closed_won"
    assert updated.confidence == 0.95

    # Get belief
    retrieved = await beliefs.get_belief("Acme Corp", "deal_stage")
    assert retrieved.id == belief.id

    # Get all beliefs
    all_beliefs = await beliefs.get_all_beliefs()
    assert len(all_beliefs) == 1

    await session.commit()


@pytest.mark.asyncio
async def test_goal_system_basic(session, employee, tenant):
    """Test basic GoalSystem operations."""
    goals = GoalSystem(session, employee.id, tenant.id)

    # Add a goal
    goal = await goals.add_goal(
        goal_type="achievement",
        description="Close 10 deals this quarter",
        priority=8,
        target={"metric": "deals_closed", "value": 10},
    )

    assert goal is not None
    assert goal.description == "Close 10 deals this quarter"
    assert goal.priority == 8
    assert goal.status == "active"

    # Update progress
    updated = await goals.update_goal_progress(
        goal_id=goal.id,
        progress={"deals_closed": 3, "velocity": 0.3},
    )

    assert updated.status == "in_progress"
    assert updated.current_progress["deals_closed"] == 3

    # Calculate progress percentage
    percentage = await goals.calculate_goal_progress_percentage(goal.id)
    assert percentage == 30.0

    # Complete goal
    completed = await goals.complete_goal(
        goal_id=goal.id,
        final_progress={"deals_closed": 10},
    )

    assert completed.status == "completed"
    assert completed.completed_at is not None

    await session.commit()


@pytest.mark.asyncio
async def test_intention_stack_basic(session, employee, tenant):
    """Test basic IntentionStack operations."""
    goals = GoalSystem(session, employee.id, tenant.id)
    intentions = IntentionStack(session, employee.id, tenant.id)

    # Create a goal first
    goal = await goals.add_goal(
        goal_type="achievement",
        description="Build pipeline",
        priority=9,
        target={"metric": "pipeline_coverage", "value": 3.0},
    )

    # Add an intention
    intention = await intentions.add_intention(
        goal_id=goal.id,
        intention_type="strategy",
        description="Launch outbound campaign",
        plan={
            "type": "outbound",
            "target_accounts": 50,
            "expected_duration": "2_weeks",
        },
        priority=9,
    )

    assert intention is not None
    assert intention.description == "Launch outbound campaign"
    assert intention.status == "planned"
    assert intention.goal_id == goal.id

    # Get next intention
    next_intention = await intentions.get_next_intention()
    assert next_intention.id == intention.id

    # Start intention
    started = await intentions.start_intention(intention.id)
    assert started.status == "in_progress"
    assert started.started_at is not None

    # Complete intention
    completed = await intentions.complete_intention(
        intention_id=intention.id,
        outcome={"accounts_contacted": 50, "responses": 12},
    )

    assert completed.status == "completed"
    assert completed.completed_at is not None
    assert completed.context["outcome"]["responses"] == 12

    await session.commit()


@pytest.mark.asyncio
async def test_intention_dependencies(session, employee, tenant):
    """Test intention dependency handling."""
    intentions = IntentionStack(session, employee.id, tenant.id)

    # Create first intention (no dependencies)
    intention1 = await intentions.add_intention(
        intention_type="action",
        description="Research accounts",
        plan={"type": "research"},
        priority=8,
    )

    # Create second intention (depends on first)
    intention2 = await intentions.add_intention(
        intention_type="action",
        description="Send emails",
        plan={"type": "email"},
        priority=8,
        dependencies=[intention1.id],
    )

    # Get next intention - should be intention1 (no dependencies)
    next_intention = await intentions.get_next_intention()
    assert next_intention.id == intention1.id

    # Complete intention1
    await intentions.start_intention(intention1.id)
    await intentions.complete_intention(intention1.id)

    # Now intention2 should be next (dependencies satisfied)
    next_intention = await intentions.get_next_intention()
    assert next_intention.id == intention2.id

    await session.commit()


@pytest.mark.asyncio
async def test_bdi_full_cycle(session, employee, tenant):
    """Test full BDI cycle: Belief → Goal → Intention."""
    beliefs = BeliefSystem(session, employee.id, tenant.id)
    goals = GoalSystem(session, employee.id, tenant.id)
    intentions = IntentionStack(session, employee.id, tenant.id)

    # 1. Form a belief from observation
    await beliefs.update_belief(
        subject="Pipeline",
        predicate="coverage",
        object={"value": 2.0, "target": 3.0},
        confidence=0.9,
        source="observation",
    )

    # 2. Recognize need → Create goal
    goal = await goals.add_goal(
        goal_type="achievement",
        description="Build pipeline to 3x coverage",
        priority=9,
        target={"metric": "coverage", "value": 3.0},
    )

    # 3. Form intention to achieve goal
    intention = await intentions.add_intention(
        goal_id=goal.id,
        intention_type="strategy",
        description="Launch outbound campaign",
        plan={"type": "outbound", "accounts": 100},
        priority=9,
    )

    # 4. Execute intention
    await intentions.start_intention(intention.id)
    await intentions.complete_intention(
        intention_id=intention.id,
        outcome={"accounts_contacted": 100, "meetings_booked": 20},
    )

    # 5. Update belief based on outcome
    await beliefs.update_belief(
        subject="Pipeline",
        predicate="coverage",
        object={"value": 3.2, "target": 3.0},
        confidence=0.95,
        source="observation",
    )

    # 6. Complete goal
    await goals.update_goal_progress(
        goal_id=goal.id,
        progress={"coverage": 3.2},
    )
    await goals.complete_goal(goal.id)

    # Verify final state
    final_belief = await beliefs.get_belief("Pipeline", "coverage")
    assert final_belief.object["value"] == 3.2

    final_goal = await goals.get_goal(goal.id)
    assert final_goal.status == "completed"

    final_intention = await intentions.get_intention(intention.id)
    assert final_intention.status == "completed"

    await session.commit()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
