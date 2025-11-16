"""
Integration tests for BDI engine.

Tests the BeliefSystem, GoalSystem, and IntentionStack with real database.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import event

from empla.bdi import BeliefSystem, GoalSystem, IntentionStack
from empla.bdi.beliefs import BeliefExtractionResult, ExtractedBelief
from empla.core.loop.models import Observation
from empla.llm.models import LLMResponse, TokenUsage
from empla.models.database import get_engine, get_sessionmaker
from empla.models.employee import Employee
from empla.models.tenant import Tenant, User


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

    # Try to start intention2 before dependency is complete - should fail
    result = await intentions.start_intention(intention2.id)
    assert result.status == "planned"  # Should remain planned
    assert result.started_at is None  # Should not have started

    # Complete intention1
    await intentions.start_intention(intention1.id)
    await intentions.complete_intention(intention1.id)

    # Now intention2 should be next (dependencies satisfied)
    next_intention = await intentions.get_next_intention()
    assert next_intention.id == intention2.id

    # Now start_intention should succeed
    result = await intentions.start_intention(intention2.id)
    assert result.status == "in_progress"  # Should be started
    assert result.started_at is not None  # Should have start time

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


@pytest.mark.asyncio
async def test_belief_extraction_from_observation(session, employee, tenant):
    """Test extracting beliefs from observation using LLM."""
    beliefs = BeliefSystem(session, employee.id, tenant.id)

    # Create a test observation
    observation = Observation(
        observation_id=uuid4(),
        employee_id=employee.id,
        tenant_id=tenant.id,
        observation_type="email_received",
        source="email",
        content={
            "from": "ceo@acmecorp.com",
            "subject": "Ready to close $100k deal",
            "body": "We're excited to move forward. Can you send the final contract?",
            "sentiment": "positive",
        },
        timestamp=datetime.now(UTC),
        priority=8,
    )

    # Create mock LLM service that returns structured beliefs
    mock_llm = AsyncMock()

    # Define what the LLM should extract
    extraction_result = BeliefExtractionResult(
        beliefs=[
            ExtractedBelief(
                subject="Acme Corp",
                predicate="deal_stage",
                object={"stage": "contract_review", "amount": 100000},
                confidence=0.9,
                reasoning="Email subject mentions 'ready to close $100k deal' and asks for final contract",
                belief_type="state",
            ),
            ExtractedBelief(
                subject="Acme Corp",
                predicate="sentiment",
                object={"sentiment": "positive", "reason": "expressed excitement"},
                confidence=0.85,
                reasoning="Body says 'excited to move forward' indicating positive sentiment",
                belief_type="evaluative",
            ),
            ExtractedBelief(
                subject="Acme Corp",
                predicate="next_action",
                object={"action": "send_contract", "urgency": "high"},
                confidence=0.95,
                reasoning="Explicit request to 'send the final contract'",
                belief_type="event",
            ),
        ],
        observation_summary="Customer email expressing readiness to close $100k deal",
    )

    mock_response = LLMResponse(
        content="",  # Not used for structured output
        model="claude-sonnet-4",
        usage=TokenUsage(input_tokens=150, output_tokens=100, total_tokens=250),
        finish_reason="stop",
        structured_output=extraction_result,
    )

    # Mock the generate_structured method
    mock_llm.generate_structured = AsyncMock(return_value=(mock_response, extraction_result))

    # Extract beliefs
    extracted_beliefs = await beliefs.extract_beliefs_from_observation(observation, mock_llm)

    # Verify beliefs were created
    assert len(extracted_beliefs) == 3

    # Verify first belief (deal_stage)
    belief1 = extracted_beliefs[0]
    assert belief1.subject == "Acme Corp"
    assert belief1.predicate == "deal_stage"
    assert belief1.object["stage"] == "contract_review"
    assert belief1.object["amount"] == 100000
    assert belief1.confidence == 0.9
    assert belief1.source == "observation"
    assert str(observation.observation_id) in belief1.evidence

    # Verify second belief (sentiment)
    belief2 = extracted_beliefs[1]
    assert belief2.subject == "Acme Corp"
    assert belief2.predicate == "sentiment"
    assert belief2.object["sentiment"] == "positive"
    assert belief2.confidence == 0.85
    assert belief2.belief_type == "evaluative"

    # Verify third belief (next_action)
    belief3 = extracted_beliefs[2]
    assert belief3.subject == "Acme Corp"
    assert belief3.predicate == "next_action"
    assert belief3.object["action"] == "send_contract"
    assert belief3.confidence == 0.95
    assert belief3.belief_type == "event"

    # Verify all beliefs are persisted
    all_beliefs = await beliefs.get_all_beliefs()
    assert len(all_beliefs) == 3

    # Verify we can query beliefs about the subject
    acme_beliefs = await beliefs.get_beliefs_about("Acme Corp")
    assert len(acme_beliefs) == 3

    await session.commit()


@pytest.mark.asyncio
async def test_belief_extraction_updates_existing_beliefs(session, employee, tenant):
    """Test that belief extraction updates existing beliefs rather than duplicating."""
    beliefs = BeliefSystem(session, employee.id, tenant.id)

    # Create an existing belief
    existing = await beliefs.update_belief(
        subject="Acme Corp",
        predicate="deal_stage",
        object={"stage": "discovery", "amount": 50000},
        confidence=0.7,
        source="observation",
    )

    # Create observation with updated information
    observation = Observation(
        observation_id=uuid4(),
        employee_id=employee.id,
        tenant_id=tenant.id,
        observation_type="email_received",
        source="email",
        content={
            "from": "ceo@acmecorp.com",
            "subject": "Contract signed - $100k deal closed!",
        },
        timestamp=datetime.now(UTC),
        priority=9,
    )

    # Mock LLM to extract updated belief
    mock_llm = AsyncMock()
    extraction_result = BeliefExtractionResult(
        beliefs=[
            ExtractedBelief(
                subject="Acme Corp",
                predicate="deal_stage",
                object={"stage": "closed_won", "amount": 100000},
                confidence=0.98,
                reasoning="Email confirms contract signed and deal closed",
                belief_type="state",
            ),
        ],
        observation_summary="Deal closed confirmation",
    )

    mock_response = LLMResponse(
        content="",
        model="claude-sonnet-4",
        usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        finish_reason="stop",
        structured_output=extraction_result,
    )

    mock_llm.generate_structured = AsyncMock(return_value=(mock_response, extraction_result))

    # Extract beliefs
    extracted_beliefs = await beliefs.extract_beliefs_from_observation(observation, mock_llm)

    # Should have updated the existing belief, not created a new one
    assert len(extracted_beliefs) == 1
    updated_belief = extracted_beliefs[0]

    # Should be the same belief ID
    assert updated_belief.id == existing.id

    # Should have updated values
    assert updated_belief.object["stage"] == "closed_won"
    assert updated_belief.object["amount"] == 100000
    assert updated_belief.confidence == 0.98

    # Should still have only one belief
    all_beliefs = await beliefs.get_all_beliefs()
    assert len(all_beliefs) == 1

    # Verify belief history was recorded
    history = await beliefs.get_belief_history(subject="Acme Corp", predicate="deal_stage")
    assert len(history) >= 2  # Created + updated

    await session.commit()


@pytest.mark.asyncio
async def test_belief_extraction_with_empty_result(session, employee, tenant):
    """Test belief extraction when LLM returns no beliefs."""
    beliefs = BeliefSystem(session, employee.id, tenant.id)

    # Create observation with no actionable content
    observation = Observation(
        observation_id=uuid4(),
        employee_id=employee.id,
        tenant_id=tenant.id,
        observation_type="email_received",
        source="email",
        content={
            "from": "noreply@automated.com",
            "subject": "Out of office auto-reply",
            "body": "I'm currently out of office.",
        },
        timestamp=datetime.now(UTC),
        priority=1,
    )

    # Mock LLM to return no beliefs
    mock_llm = AsyncMock()
    extraction_result = BeliefExtractionResult(
        beliefs=[],  # No beliefs extracted
        observation_summary="Automated out-of-office reply with no actionable content",
    )

    mock_response = LLMResponse(
        content="",
        model="claude-sonnet-4",
        usage=TokenUsage(input_tokens=80, output_tokens=30, total_tokens=110),
        finish_reason="stop",
        structured_output=extraction_result,
    )

    mock_llm.generate_structured = AsyncMock(return_value=(mock_response, extraction_result))

    # Extract beliefs
    extracted_beliefs = await beliefs.extract_beliefs_from_observation(observation, mock_llm)

    # Should return empty list
    assert len(extracted_beliefs) == 0

    # Should not have created any beliefs
    all_beliefs = await beliefs.get_all_beliefs()
    assert len(all_beliefs) == 0

    await session.commit()


@pytest.mark.asyncio
async def test_belief_extraction_evidence_tracking(session, employee, tenant):
    """Test that belief extraction properly tracks observation as evidence."""
    beliefs = BeliefSystem(session, employee.id, tenant.id)

    # Create two observations about the same subject
    obs1 = Observation(
        observation_id=uuid4(),
        employee_id=employee.id,
        tenant_id=tenant.id,
        observation_type="email_received",
        source="email",
        content={"from": "ceo@acmecorp.com", "body": "We're interested in the product"},
        timestamp=datetime.now(UTC),
        priority=5,
    )

    obs2 = Observation(
        observation_id=uuid4(),
        employee_id=employee.id,
        tenant_id=tenant.id,
        observation_type="meeting_notes",
        source="calendar",
        content={"attendee": "CEO of Acme", "notes": "Very interested, wants demo next week"},
        timestamp=datetime.now(UTC),
        priority=7,
    )

    # Mock LLM for first observation
    mock_llm = AsyncMock()

    extraction1 = BeliefExtractionResult(
        beliefs=[
            ExtractedBelief(
                subject="Acme Corp",
                predicate="interest_level",
                object={"level": "moderate"},
                confidence=0.7,
                reasoning="Email expresses initial interest",
                belief_type="evaluative",
            ),
        ],
        observation_summary="Initial interest expressed",
    )

    mock_llm.generate_structured = AsyncMock(
        return_value=(
            LLMResponse(
                content="",
                model="claude-sonnet-4",
                usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                finish_reason="stop",
                structured_output=extraction1,
            ),
            extraction1,
        )
    )

    # Extract from first observation
    beliefs1 = await beliefs.extract_beliefs_from_observation(obs1, mock_llm)
    assert len(beliefs1) == 1
    assert str(obs1.observation_id) in beliefs1[0].evidence

    # Mock LLM for second observation (should update the same belief)
    extraction2 = BeliefExtractionResult(
        beliefs=[
            ExtractedBelief(
                subject="Acme Corp",
                predicate="interest_level",
                object={"level": "high"},
                confidence=0.9,
                reasoning="Meeting notes show strong interest and commitment to demo",
                belief_type="evaluative",
            ),
        ],
        observation_summary="High interest confirmed in meeting",
    )

    mock_llm.generate_structured = AsyncMock(
        return_value=(
            LLMResponse(
                content="",
                model="claude-sonnet-4",
                usage=TokenUsage(input_tokens=50, output_tokens=30, total_tokens=80),
                finish_reason="stop",
                structured_output=extraction2,
            ),
            extraction2,
        )
    )

    # Extract from second observation
    beliefs2 = await beliefs.extract_beliefs_from_observation(obs2, mock_llm)
    assert len(beliefs2) == 1

    # Should be the same belief (updated)
    assert beliefs2[0].id == beliefs1[0].id

    # Should have both observations as evidence
    assert str(obs1.observation_id) in beliefs2[0].evidence
    assert str(obs2.observation_id) in beliefs2[0].evidence

    # Should have updated confidence and value
    assert beliefs2[0].object["level"] == "high"
    assert beliefs2[0].confidence == 0.9

    await session.commit()


@pytest.mark.asyncio
async def test_belief_type_validation():
    """Test belief_type validation and normalization in ExtractedBelief."""
    from pydantic import ValidationError

    # Valid lowercase values should pass
    valid_types = ["state", "event", "causal", "evaluative"]
    for belief_type in valid_types:
        belief = ExtractedBelief(
            subject="Test",
            predicate="test",
            object={"value": "test"},
            confidence=0.8,
            reasoning="test",
            belief_type=belief_type,
        )
        assert belief.belief_type == belief_type

    # Capitalized values should be normalized to lowercase
    capitalized_tests = [
        ("State", "state"),
        ("EVENT", "event"),
        ("Causal", "causal"),
        ("EVALUATIVE", "evaluative"),
        ("  state  ", "state"),  # With whitespace
    ]
    for input_val, expected in capitalized_tests:
        belief = ExtractedBelief(
            subject="Test",
            predicate="test",
            object={"value": "test"},
            confidence=0.8,
            reasoning="test",
            belief_type=input_val,
        )
        assert belief.belief_type == expected

    # Common variants should be mapped to canonical values
    variant_tests = [
        ("status", "state"),
        ("condition", "state"),
        ("action", "event"),
        ("occurrence", "event"),
        ("cause", "causal"),
        ("cause-effect", "causal"),
        ("assessment", "evaluative"),
        ("evaluation", "evaluative"),
        ("judgment", "evaluative"),
    ]
    for input_val, expected in variant_tests:
        belief = ExtractedBelief(
            subject="Test",
            predicate="test",
            object={"value": "test"},
            confidence=0.8,
            reasoning="test",
            belief_type=input_val,
        )
        assert belief.belief_type == expected

    # Invalid values should raise ValidationError
    invalid_types = ["invalid", "unknown", "random", "xyz"]
    for invalid_type in invalid_types:
        with pytest.raises(ValidationError) as exc_info:
            ExtractedBelief(
                subject="Test",
                predicate="test",
                object={"value": "test"},
                confidence=0.8,
                reasoning="test",
                belief_type=invalid_type,
            )
        # Verify error message mentions the invalid value
        assert "belief_type" in str(exc_info.value).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
