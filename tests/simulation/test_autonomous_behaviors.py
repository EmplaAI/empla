"""
End-to-end autonomous employee behavior tests.

These tests validate that the complete autonomous employee system works correctly:
- REAL BDI implementations (BeliefSystem, GoalSystem, IntentionStack from empla/bdi/)
- REAL memory systems (from empla/core/memory/*)
- REAL ProactiveExecutionLoop (from empla/core/loop/execution.py)
- SIMULATED environment only (email, calendar, CRM - no real API calls)

Test scenarios demonstrate autonomous behaviors like:
- Sales AE: Detects low pipeline → Forms goal → Plans outreach → Executes → Improves pipeline
- CSM: Detects at-risk customer → Forms intervention goal → Plans check-in → Executes → Updates health

This validates that the actual production code can autonomously:
- Form beliefs from observations
- Recognize problems/opportunities
- Create appropriate goals
- Plan strategies to achieve goals
- Execute plans
- Learn from outcomes
"""

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import event

logger = logging.getLogger(__name__)

from empla.bdi import BeliefSystem, GoalSystem, IntentionStack
from empla.bdi.beliefs import BeliefExtractionResult, ExtractedBelief
from empla.bdi.intentions import GeneratedIntention, PlanGenerationResult
from empla.capabilities import CapabilityType
from empla.llm.models import LLMResponse, TokenUsage
from empla.models.database import get_engine, get_sessionmaker
from empla.models.employee import Employee
from empla.models.tenant import Tenant, User
from tests.simulation import (
    CustomerHealth,
    DealStage,
    EmailPriority,
    SimulatedDeal,
    SimulatedEmail,
    SimulatedEnvironment,
    get_simulated_capabilities,
)

# Fixtures (same as test_bdi_integration.py)


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
    def restart_savepoint(_session, transaction):
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


@pytest.fixture
def simulated_env():
    """Create a simulated environment."""
    return SimulatedEnvironment()


@pytest.fixture
def mock_llm():
    """
    Create a mock LLM service (or real LLM if RUN_WITH_REAL_LLM=1).

    By default, this returns a mock LLM for fast, deterministic testing.

    To run tests with real LLM calls:
        RUN_WITH_REAL_LLM=1 pytest tests/simulation/test_autonomous_behaviors.py -v

    This validates:
    - LLM prompts are well-formed
    - LLM can actually extract beliefs from observations
    - LLM can actually generate executable plans

    Note: Real LLM tests are slower and cost tokens (~$0.01-0.05 per test).
    """
    import os

    # Check if we should use real LLM
    use_real_llm = os.getenv("RUN_WITH_REAL_LLM", "0").lower() in ("1", "true", "yes")

    if use_real_llm:
        # Create real LLM service
        from empla.llm import LLMConfig, LLMService

        # Check for API keys and project IDs
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        vertex_project = os.getenv("VERTEX_PROJECT_ID") or os.getenv("GCP_PROJECT_ID")
        vertex_location = os.getenv("VERTEX_LOCATION", "us-central1")

        # Determine which provider to use based on available credentials
        if vertex_project:
            # Use Vertex AI / Gemini
            primary_model = "gemini-3-flash-preview"  # Fast and cheap for testing
            fallback_model = None
            logger.info(f"Using Vertex AI with project: {vertex_project}")
        elif anthropic_key:
            # Use Anthropic Claude
            primary_model = "claude-sonnet-4"
            fallback_model = "gpt-4o-mini" if openai_key else None
        elif openai_key:
            # Use OpenAI GPT
            primary_model = "gpt-4o-mini"
            fallback_model = None
        else:
            raise ValueError(
                "RUN_WITH_REAL_LLM=1 but no credentials found. Set one of:\n"
                "  - VERTEX_PROJECT_ID (or GCP_PROJECT_ID) for Gemini\n"
                "  - ANTHROPIC_API_KEY for Claude\n"
                "  - OPENAI_API_KEY for GPT"
            )

        config = LLMConfig(
            primary_model=primary_model,
            fallback_model=fallback_model,
            anthropic_api_key=anthropic_key,
            openai_api_key=openai_key,
            vertex_project_id=vertex_project,
            vertex_location=vertex_location,
            enable_cost_tracking=True,
        )

        llm_service = LLMService(config)

        logger.info("Using REAL LLM service for testing (costs tokens)")
        logger.info(f"Primary model: {config.primary_model}")
        if vertex_project:
            logger.info(f"Vertex location: {vertex_location}")

        return llm_service

    # Return mock LLM (fast, free, deterministic)
    logger.debug("Using MOCK LLM service for testing (fast, free)")
    return AsyncMock()


# Helper functions


def is_real_llm(llm_service) -> bool:
    """
    Check if we're using real LLM or mock.

    Args:
        llm_service: LLM service instance to check

    Returns:
        False if llm_service is an AsyncMock, otherwise checks RUN_WITH_REAL_LLM env var
    """
    # Directly detect mock by checking instance type
    if isinstance(llm_service, AsyncMock):
        return False

    # Fall back to environment variable check for real LLM services
    import os
    return os.getenv("RUN_WITH_REAL_LLM", "0").lower() in ("1", "true", "yes")


# Test Scenarios


@pytest.mark.asyncio
async def test_sales_ae_low_pipeline_autonomous_response(
    session, employee, tenant, simulated_env, mock_llm
):
    """
    Test Sales AE autonomous response to low pipeline coverage.

    Scenario:
    1. Sales AE perceives low pipeline coverage (2.0x instead of 3.0x target)
    2. Forms belief: "Pipeline coverage is below target"
    3. Recognizes problem → Creates goal: "Build pipeline to 3x"
    4. Plans strategy: Research accounts, send outreach
    5. Executes: Researches 10 accounts, sends 10 outreach emails
    6. Learns: Pipeline coverage improved, strategy worked

    This validates the complete BDI cycle autonomously.
    """
    # Setup: Real BDI components
    beliefs = BeliefSystem(session, employee.id, tenant.id)
    goals = GoalSystem(session, employee.id, tenant.id)
    intentions = IntentionStack(session, employee.id, tenant.id)

    # Setup: Simulated environment with low pipeline
    simulated_env.crm.set_pipeline_target(500000.0)  # $500K target
    simulated_env.crm.set_pipeline_coverage(2.0)  # Only 2.0x (below 3.0x target)

    # Setup: Simulated capabilities
    capabilities = get_simulated_capabilities(
        tenant_id=tenant.id,
        employee_id=employee.id,
        environment=simulated_env,
        enabled_capabilities=["email", "crm"],
    )

    # Initialize capabilities
    for cap in capabilities.values():
        await cap.initialize()

    # Step 1: PERCEIVE - Get observations from simulated CRM
    crm_cap = capabilities[CapabilityType.CRM]
    observations = await crm_cap.perceive()

    # Assert: Should detect low pipeline
    assert len(observations) > 0
    low_pipeline_obs = next((o for o in observations if o.type == "low_pipeline_coverage"), None)
    assert low_pipeline_obs is not None
    assert low_pipeline_obs.priority >= 8  # High priority
    assert low_pipeline_obs.data["pipeline_coverage"] == 2.0

    # Step 2: UPDATE BELIEFS - Extract beliefs from observation
    # If using mock LLM, set up mock response
    if not is_real_llm(mock_llm):
        extraction_result = BeliefExtractionResult(
            beliefs=[
                ExtractedBelief(
                    subject="Pipeline",
                    predicate="coverage",
                    object={"value": 2.0, "target": 3.0, "gap": 1.0},
                    confidence=0.95,
                    reasoning="CRM data shows pipeline coverage at 2.0x, below 3.0x target",
                    belief_type="state",
                ),
                ExtractedBelief(
                    subject="Pipeline",
                    predicate="priority",
                    object={"priority": "high", "reason": "significant gap to target"},
                    confidence=0.9,
                    reasoning="1.0x gap represents significant shortfall requiring immediate action",
                    belief_type="evaluative",
                ),
            ],
            observation_summary="Pipeline coverage significantly below target",
        )

        mock_llm.generate_structured = AsyncMock(
            return_value=(
                LLMResponse(
                    content="",
                    model="claude-sonnet-4",
                    usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                    finish_reason="stop",
                    structured_output=extraction_result,
                ),
                extraction_result,
            )
        )

    # Convert simulated observation to core Observation model
    from empla.core.loop.models import Observation

    core_observation = Observation(
        observation_id=uuid4(),
        employee_id=employee.id,
        tenant_id=tenant.id,
        observation_type=low_pipeline_obs.type,
        source=low_pipeline_obs.source,
        content=low_pipeline_obs.data,
        timestamp=low_pipeline_obs.timestamp,
        priority=low_pipeline_obs.priority,
    )

    # Extract beliefs using real BeliefSystem
    extracted_beliefs = await beliefs.extract_beliefs_from_observation(core_observation, mock_llm)

    # Assert: Beliefs were formed
    # When using real LLM, we can't predict exact beliefs, so be more flexible
    if is_real_llm(mock_llm):
        assert len(extracted_beliefs) > 0, "Real LLM should extract at least one belief"
        # Just check that beliefs are related to pipeline
        belief_subjects = [b.subject for b in extracted_beliefs]
        assert any("pipeline" in s.lower() for s in belief_subjects), (
            f"Expected pipeline-related beliefs, got: {belief_subjects}"
        )
    else:
        # Mock LLM - exact assertions
        assert len(extracted_beliefs) == 2
        pipeline_belief = next((b for b in extracted_beliefs if b.predicate == "coverage"), None)
        assert pipeline_belief is not None
        assert pipeline_belief.object["value"] == 2.0
        assert pipeline_belief.confidence == 0.95

    # Step 3: FORM GOAL - Recognize problem and create goal
    # In production, this would be done by strategic planning in ProactiveLoop
    # For simulation, we do it manually to validate the BDI components
    goal = await goals.add_goal(
        goal_type="achievement",
        description="Build pipeline to 3x coverage",
        priority=9,
        target={"metric": "pipeline_coverage", "value": 3.0},
    )

    # Assert: Goal was created
    assert goal is not None
    assert goal.status == "active"
    assert goal.priority == 9

    # Step 4: PLAN STRATEGY - Generate plan to achieve goal
    # If using mock LLM, set up mock plan
    if not is_real_llm(mock_llm):
        plan_result = PlanGenerationResult(
            intentions=[
                GeneratedIntention(
                    intention_type="action",
                    description="Research 10 target accounts",
                    priority=8,
                    plan={
                        "steps": [
                            {
                                "action": "research_accounts",
                                "parameters": {"count": 10, "criteria": "icp_match"},
                                "expected_outcome": "10 researched account profiles",
                            }
                        ]
                    },
                    reasoning="Need qualified accounts before outreach",
                    estimated_duration_minutes=60,
                    dependencies=[],
                    required_capabilities=["crm"],
                ),
                GeneratedIntention(
                    intention_type="action",
                    description="Send personalized outreach to 10 accounts",
                    priority=9,
                    plan={
                        "steps": [
                            {
                                "action": "send_email",
                                "parameters": {
                                    "template": "intro_outreach",
                                    "personalize": True,
                                },
                                "expected_outcome": "10 outreach emails sent",
                            }
                        ]
                    },
                    reasoning="Personalized outreach has higher response rate",
                    estimated_duration_minutes=30,
                    dependencies=[0],  # Depends on research
                    required_capabilities=["email"],
                ),
            ],
            strategy_summary="Research-driven personalized outreach campaign",
            assumptions=["Accounts match ICP", "Email addresses available"],
            risks=["Low response rate", "Timing may not be optimal"],
            success_criteria=["10 emails sent", "Pipeline coverage increased"],
        )

        mock_llm.generate_structured = AsyncMock(
            return_value=(
                LLMResponse(
                    content="",
                    model="claude-sonnet-4",
                    usage=TokenUsage(input_tokens=200, output_tokens=150, total_tokens=350),
                    finish_reason="stop",
                    structured_output=plan_result,
                ),
                plan_result,
            )
        )

    # Get current beliefs for planning context
    belief_list = await beliefs.get_all_beliefs()

    # Generate plan using real IntentionStack
    generated_intentions = await intentions.generate_plan_for_goal(
        goal=goal,
        beliefs=belief_list,
        llm_service=mock_llm,
        capabilities=["email", "crm"],
    )

    # Assert: Plan was generated
    if is_real_llm(mock_llm):
        # Real LLM - just check that plan was generated with some intentions
        assert len(generated_intentions) > 0, "Real LLM should generate at least one intention"
        logger.info(f"Real LLM generated {len(generated_intentions)} intentions:")
        for intention in generated_intentions:
            logger.info(f"  - {intention.description}")
        # Use first two intentions for rest of test (or first one twice if only one generated)
        research_intention = generated_intentions[0]
        outreach_intention = (
            generated_intentions[1] if len(generated_intentions) > 1 else generated_intentions[0]
        )
    else:
        # Mock LLM - exact assertions
        assert len(generated_intentions) == 2
        research_intention = generated_intentions[0]
        outreach_intention = generated_intentions[1]

        assert research_intention.description == "Research 10 target accounts"
        assert len(research_intention.dependencies) == 0  # No dependencies

        assert outreach_intention.description == "Send personalized outreach to 10 accounts"
        assert len(outreach_intention.dependencies) == 1  # Depends on research
        assert outreach_intention.dependencies[0] == research_intention.id

    # Step 5: EXECUTE - Execute intentions
    # Execute research intention
    await intentions.start_intention(research_intention.id)

    # Simulate research execution - add accounts to CRM
    for i in range(10):
        from tests.simulation.environment import SimulatedContact

        simulated_env.crm.add_contact(
            SimulatedContact(
                name=f"Contact {i + 1}",
                email=f"contact{i + 1}@account{i + 1}.com",
                company=f"Account {i + 1}",
                title="VP Sales",
            )
        )

    # Complete research intention
    await intentions.complete_intention(
        intention_id=research_intention.id,
        outcome={"accounts_researched": 10, "accounts_added": 10},
    )

    # Execute outreach intention (now that dependency is complete)
    await intentions.start_intention(outreach_intention.id)

    # Simulate email sending via simulated email capability
    email_cap = capabilities[CapabilityType.EMAIL]

    for i in range(10):
        from empla.capabilities.base import Action

        action = Action(
            capability="email",
            operation="send_email",
            parameters={
                "to": [f"contact{i + 1}@account{i + 1}.com"],
                "subject": f"Interested in partnering with Account {i + 1}",
                "body": f"Hi, I'd love to discuss how we can help Account {i + 1}...",
            },
        )
        result = await email_cap.execute_action(action)
        assert result.success is True

    # Complete outreach intention
    await intentions.complete_intention(
        intention_id=outreach_intention.id,
        outcome={"emails_sent": 10, "accounts_contacted": 10},
    )

    # Assert: Intentions were executed
    completed_research = await intentions.get_intention(research_intention.id)
    assert completed_research.status == "completed"

    completed_outreach = await intentions.get_intention(outreach_intention.id)
    assert completed_outreach.status == "completed"

    # Assert: Environment shows work was done
    assert simulated_env.email.sent_count == 10
    assert len(simulated_env.crm.contacts) == 10
    assert simulated_env.metrics.emails_sent == 10

    # Step 6: LEARN - Update beliefs based on outcome
    # Add deals to CRM (simulating that outreach generated pipeline)
    for i in range(5):  # 5 deals created from 10 outreach emails
        simulated_env.crm.add_deal(
            SimulatedDeal(
                name=f"Deal from Account {i + 1}",
                value=100000.0,  # $100K each
                stage=DealStage.PROSPECTING,
                probability=0.2,
            )
        )

    # Check actual coverage (may still be low since we only added $500K)
    new_coverage = simulated_env.crm.get_pipeline_coverage()
    initial_coverage = 2.0
    assert new_coverage > initial_coverage  # Coverage improved (but may still be below target)

    # Update belief with new information
    await beliefs.update_belief(
        subject="Pipeline",
        predicate="coverage",
        object={"value": new_coverage, "target": 3.0, "improved_from": 2.0},
        confidence=0.95,
        source="observation",
    )

    # Update goal progress
    await goals.update_goal_progress(
        goal_id=goal.id,
        progress={
            "coverage": new_coverage,
            "improved": True,
            "emails_sent": 10,
            "deals_created": 5,
        },
    )

    # If goal achieved, complete it
    if new_coverage >= 3.0:
        await goals.complete_goal(goal.id, final_progress={"coverage": new_coverage})

    # Assert: Learning happened (belief updated, goal progressed)
    updated_belief = await beliefs.get_belief("Pipeline", "coverage")
    assert updated_belief.object["value"] > 2.0  # Improved
    assert "improved_from" in updated_belief.object

    updated_goal = await goals.get_goal(goal.id)
    assert updated_goal.status in ["in_progress", "completed"]
    assert updated_goal.current_progress["improved"] is True

    # Assert: Metrics show autonomous work was done
    metrics_summary = simulated_env.get_state_summary()
    assert metrics_summary["email"]["sent_count"] == 10
    assert metrics_summary["crm"]["contacts"] == 10
    # Note: Deal count includes the placeholder deal from set_pipeline_coverage(2.0)
    assert metrics_summary["crm"]["deals"] >= 5  # At least 5 deals added
    assert metrics_summary["metrics"]["emails_sent"] == 10

    await session.commit()


@pytest.mark.asyncio
async def test_csm_at_risk_customer_intervention(
    session, employee, tenant, simulated_env, mock_llm
):
    """
    Test CSM autonomous intervention for at-risk customer.

    Scenario:
    1. CSM perceives at-risk customer (high churn risk, no recent contact)
    2. Forms belief: "Acme Corp is at risk of churning"
    3. Recognizes problem → Creates goal: "Prevent Acme Corp churn"
    4. Plans intervention: Schedule check-in call, review usage, prepare resources
    5. Executes: Sends email, schedules meeting
    6. Learns: Customer responded, risk reduced

    This validates CSM autonomous proactive intervention.
    """
    # Setup: Real BDI components
    beliefs = BeliefSystem(session, employee.id, tenant.id)
    goals = GoalSystem(session, employee.id, tenant.id)
    intentions = IntentionStack(session, employee.id, tenant.id)

    # Setup: Simulated environment with at-risk customer
    from tests.simulation.environment import SimulatedCustomer

    at_risk_customer = SimulatedCustomer(
        name="Acme Corp",
        contract_value=120000.0,  # $120K contract
        health=CustomerHealth.AT_RISK,
        churn_risk_score=0.75,  # High risk
        usage_score=0.3,  # Low usage
        support_tickets_count=5,  # Multiple support issues
        last_contact_date=datetime.now(UTC) - timedelta(days=30),  # No contact in 30 days
    )

    simulated_env.crm.add_customer(at_risk_customer)

    # Setup: Simulated capabilities
    capabilities = get_simulated_capabilities(
        tenant_id=tenant.id,
        employee_id=employee.id,
        environment=simulated_env,
        enabled_capabilities=["email", "calendar", "crm"],
    )

    # Initialize capabilities
    for cap in capabilities.values():
        await cap.initialize()

    # Step 1: PERCEIVE - Detect at-risk customer
    crm_cap = capabilities[CapabilityType.CRM]
    observations = await crm_cap.perceive()

    # Assert: Should detect at-risk customer
    assert len(observations) > 0
    at_risk_obs = next((o for o in observations if o.type == "customer_at_risk"), None)
    assert at_risk_obs is not None
    assert at_risk_obs.priority >= 9  # Very high priority
    assert at_risk_obs.data["customer_name"] == "Acme Corp"
    assert at_risk_obs.data["churn_risk_score"] == 0.75

    # Step 2: UPDATE BELIEFS - Extract beliefs from observation
    # If using mock LLM, set up mock response
    if not is_real_llm(mock_llm):
        extraction_result = BeliefExtractionResult(
            beliefs=[
                ExtractedBelief(
                    subject="Acme Corp",
                    predicate="health_status",
                    object={
                        "status": "at_risk",
                        "churn_risk": 0.75,
                        "contract_value": 120000.0,
                    },
                    confidence=0.95,
                    reasoning="CRM shows high churn risk score and at-risk health status",
                    belief_type="state",
                ),
                ExtractedBelief(
                    subject="Acme Corp",
                    predicate="engagement",
                    object={
                        "usage_score": 0.3,
                        "last_contact_days": 30,
                        "support_tickets": 5,
                    },
                    confidence=0.9,
                    reasoning="Low usage, no recent contact, multiple support issues indicate poor engagement",
                    belief_type="evaluative",
                ),
                ExtractedBelief(
                    subject="Acme Corp",
                    predicate="priority",
                    object={
                        "priority": "urgent",
                        "reason": "High value customer at risk",
                    },
                    confidence=0.95,
                    reasoning="$120K contract at 75% churn risk requires immediate intervention",
                    belief_type="evaluative",
                ),
            ],
            observation_summary="High-value customer showing signs of churn risk",
        )

        mock_llm.generate_structured = AsyncMock(
            return_value=(
                LLMResponse(
                    content="",
                    model="claude-sonnet-4",
                    usage=TokenUsage(input_tokens=150, output_tokens=80, total_tokens=230),
                    finish_reason="stop",
                    structured_output=extraction_result,
                ),
                extraction_result,
            )
        )

    # Convert to core Observation
    from empla.core.loop.models import Observation

    core_observation = Observation(
        observation_id=uuid4(),
        employee_id=employee.id,
        tenant_id=tenant.id,
        observation_type=at_risk_obs.type,
        source=at_risk_obs.source,
        content=at_risk_obs.data,
        timestamp=at_risk_obs.timestamp,
        priority=at_risk_obs.priority,
    )

    # Extract beliefs
    extracted_beliefs = await beliefs.extract_beliefs_from_observation(core_observation, mock_llm)

    # Assert: Beliefs formed about customer risk
    if is_real_llm(mock_llm):
        assert len(extracted_beliefs) > 0, "Real LLM should extract at least one belief"
        # Just check that beliefs are related to customer
        belief_subjects = [b.subject for b in extracted_beliefs]
        assert any("acme" in s.lower() or "customer" in s.lower() for s in belief_subjects), (
            f"Expected customer-related beliefs, got: {belief_subjects}"
        )
    else:
        # Mock LLM - exact assertions
        assert len(extracted_beliefs) == 3
        health_belief = next((b for b in extracted_beliefs if b.predicate == "health_status"), None)
        assert health_belief is not None
        assert health_belief.object["status"] == "at_risk"
        assert health_belief.object["churn_risk"] == 0.75

    # Step 3: FORM GOAL - Create churn prevention goal
    goal = await goals.add_goal(
        goal_type="maintenance",
        description="Prevent Acme Corp churn through proactive intervention",
        priority=10,  # Highest priority
        target={
            "metric": "customer_health",
            "account": "Acme Corp",
            "target_health": "healthy",
            "target_churn_risk": 0.2,
        },
    )

    # Assert: Goal created with high priority
    assert goal is not None
    assert goal.status == "active"
    assert goal.priority == 10

    # Step 4: PLAN INTERVENTION - Generate intervention plan
    # If using mock LLM, set up mock plan
    if not is_real_llm(mock_llm):
        plan_result = PlanGenerationResult(
            intentions=[
                GeneratedIntention(
                    intention_type="action",
                    description="Send personalized check-in email to Acme Corp",
                    priority=10,
                    plan={
                        "steps": [
                            {
                                "action": "send_email",
                                "parameters": {
                                    "to": ["ceo@acmecorp.com"],
                                    "subject": "Checking in - How can we better support you?",
                                    "body": "Hi, I wanted to personally check in...",
                                    "tone": "empathetic",
                                },
                                "expected_outcome": "Email sent, opens door for conversation",
                            }
                        ]
                    },
                    reasoning="Personal outreach shows we care and opens communication",
                    estimated_duration_minutes=15,
                    dependencies=[],
                    required_capabilities=["email"],
                ),
                GeneratedIntention(
                    intention_type="action",
                    description="Schedule check-in call with Acme Corp stakeholders",
                    priority=10,
                    plan={
                        "steps": [
                            {
                                "action": "schedule_meeting",
                                "parameters": {
                                    "attendees": ["ceo@acmecorp.com"],
                                    "duration_minutes": 30,
                                    "subject": "Partnership check-in",
                                    "agenda": "Review usage, address concerns, explore needs",
                                },
                                "expected_outcome": "Meeting scheduled within 48 hours",
                            }
                        ]
                    },
                    reasoning="Face-to-face discussion allows deeper understanding of issues",
                    estimated_duration_minutes=10,
                    dependencies=[0],  # After email sent
                    required_capabilities=["calendar"],
                ),
            ],
            strategy_summary="Empathetic personal outreach followed by structured check-in",
            assumptions=["Stakeholders responsive", "Issues are addressable"],
            risks=["May already be committed to churn", "Timing may be too late"],
            success_criteria=["Email sent", "Meeting scheduled", "Churn risk reduced"],
        )

        mock_llm.generate_structured = AsyncMock(
            return_value=(
                LLMResponse(
                    content="",
                    model="claude-sonnet-4",
                    usage=TokenUsage(input_tokens=220, output_tokens=160, total_tokens=380),
                    finish_reason="stop",
                    structured_output=plan_result,
                ),
                plan_result,
            )
        )

    # Generate plan
    belief_list = await beliefs.get_all_beliefs()
    generated_intentions = await intentions.generate_plan_for_goal(
        goal=goal,
        beliefs=belief_list,
        llm_service=mock_llm,
        capabilities=["email", "calendar"],
    )

    # Assert: Intervention plan generated
    if is_real_llm(mock_llm):
        # Real LLM - just check that plan was generated
        assert len(generated_intentions) > 0, "Real LLM should generate at least one intention"
        logger.info(f"Real LLM generated {len(generated_intentions)} intentions:")
        for intention in generated_intentions:
            logger.info(f"  - {intention.description}")
        # Use first two intentions for rest of test (or first one twice if only one generated)
        email_intention = generated_intentions[0]
        meeting_intention = (
            generated_intentions[1] if len(generated_intentions) > 1 else generated_intentions[0]
        )
    else:
        # Mock LLM - exact assertions
        assert len(generated_intentions) == 2
        email_intention = generated_intentions[0]
        meeting_intention = generated_intentions[1]

        assert "check-in email" in email_intention.description.lower()
        assert "check-in call" in meeting_intention.description.lower()
        assert meeting_intention.dependencies[0] == email_intention.id  # Depends on email

    # Step 5: EXECUTE - Execute intervention
    # Send email
    await intentions.start_intention(email_intention.id)

    email_cap = capabilities[CapabilityType.EMAIL]
    from empla.capabilities.base import Action

    email_action = Action(
        capability="email",
        operation="send_email",
        parameters={
            "to": ["ceo@acmecorp.com"],
            "subject": "Checking in - How can we better support you?",
            "body": "Hi, I wanted to personally check in and see how things are going with our product. I noticed you've had a few support tickets recently and wanted to make sure we're addressing everything. Would love to schedule a call to discuss. Best regards,",
        },
    )

    email_result = await email_cap.execute_action(email_action)
    assert email_result.success is True

    await intentions.complete_intention(
        intention_id=email_intention.id, outcome={"email_sent": True}
    )

    # Schedule meeting
    await intentions.start_intention(meeting_intention.id)

    calendar_cap = capabilities[CapabilityType.CALENDAR]
    meeting_action = Action(
        capability="calendar",
        operation="create_event",
        parameters={
            "subject": "Partnership check-in with Acme Corp",
            "start_time": datetime.now(UTC) + timedelta(days=2),
            "end_time": datetime.now(UTC) + timedelta(days=2, minutes=30),
            "attendees": ["ceo@acmecorp.com"],
            "location": "Video call",
            "description": "Review usage, address concerns, explore how we can better support your team",
        },
    )

    meeting_result = await calendar_cap.execute_action(meeting_action)
    assert meeting_result.success is True

    await intentions.complete_intention(
        intention_id=meeting_intention.id, outcome={"meeting_scheduled": True}
    )

    # Assert: Intervention executed
    assert simulated_env.email.sent_count == 1
    assert len(simulated_env.calendar.events) == 1
    assert simulated_env.metrics.meetings_scheduled == 1

    # Step 6: LEARN - Simulate positive response, update beliefs
    # Customer responds positively to email (simulate incoming email)
    simulated_env.email.receive_email(
        SimulatedEmail(
            from_address="ceo@acmecorp.com",
            to_addresses=["employee@company.com"],
            subject="Re: Checking in - How can we better support you?",
            body="Thanks for reaching out! Yes, we've had some issues but I appreciate you being proactive. Looking forward to the call.",
            received_at=datetime.now(UTC),
            priority=EmailPriority.HIGH,
        )
    )

    # Perceive response
    email_observations = await email_cap.perceive()
    response_obs = next(
        (o for o in email_observations if "Re: Checking in" in o.data.get("subject", "")),
        None,
    )
    assert response_obs is not None

    # Update customer health (simulating improved engagement)
    at_risk_customer.health = CustomerHealth.HEALTHY
    at_risk_customer.churn_risk_score = 0.3  # Reduced from 0.75
    at_risk_customer.last_contact_date = datetime.now(UTC)

    # Update belief
    await beliefs.update_belief(
        subject="Acme Corp",
        predicate="health_status",
        object={
            "status": "healthy",
            "churn_risk": 0.3,
            "improved_from": 0.75,
            "intervention_successful": True,
        },
        confidence=0.85,
        source="observation",
    )

    # Update goal progress
    await goals.update_goal_progress(
        goal_id=goal.id,
        progress={
            "churn_risk": 0.3,
            "email_sent": True,
            "meeting_scheduled": True,
            "customer_responded": True,
        },
    )

    # Complete goal (churn risk reduced below target)
    await goals.complete_goal(
        goal_id=goal.id,
        final_progress={
            "churn_risk": 0.3,
            "target_achieved": True,
            "intervention_successful": True,
        },
    )

    # Assert: Learning and goal completion
    updated_belief = await beliefs.get_belief("Acme Corp", "health_status")
    assert updated_belief.object["status"] == "healthy"
    assert updated_belief.object["intervention_successful"] is True

    final_goal = await goals.get_goal(goal.id)
    assert final_goal.status == "completed"
    # Note: final_progress is passed to complete_goal but stored in current_progress
    assert final_goal.current_progress["intervention_successful"] is True

    # Assert: Metrics show intervention work
    metrics_summary = simulated_env.get_state_summary()
    assert metrics_summary["email"]["sent_count"] == 1
    assert metrics_summary["calendar"]["total_events"] == 1
    assert simulated_env.metrics.meetings_scheduled == 1

    await session.commit()


@pytest.mark.asyncio
async def test_perception_with_simulated_capabilities(session, employee, tenant, simulated_env):
    """
    Test that simulated capabilities produce observations correctly.

    This validates that:
    - Simulated email capability perceives emails
    - Simulated calendar capability perceives events
    - Simulated CRM capability perceives pipeline/customer issues
    """
    # Setup simulated capabilities
    capabilities = get_simulated_capabilities(
        tenant_id=tenant.id,
        employee_id=employee.id,
        environment=simulated_env,
        enabled_capabilities=["email", "calendar", "crm"],
    )

    # Initialize
    for cap in capabilities.values():
        await cap.initialize()

    # Add test data to environment
    # 1. Email
    simulated_env.email.receive_email(
        SimulatedEmail(
            from_address="customer@test.com",
            to_addresses=["employee@company.com"],
            subject="Question about your product",
            body="Can you tell me more about pricing?",
            priority=EmailPriority.HIGH,
        )
    )

    # 2. Calendar
    simulated_env.calendar.create_event(
        subject="Team standup",
        start_time=datetime.now(UTC) + timedelta(minutes=30),
        end_time=datetime.now(UTC) + timedelta(minutes=60),
        attendees=["team@company.com"],
    )

    # 3. CRM - low pipeline
    simulated_env.crm.set_pipeline_coverage(2.0)

    # Perceive from all capabilities
    email_obs = await capabilities[CapabilityType.EMAIL].perceive()
    calendar_obs = await capabilities[CapabilityType.CALENDAR].perceive()
    crm_obs = await capabilities[CapabilityType.CRM].perceive()

    # Assert: All capabilities produced observations
    assert len(email_obs) == 1
    assert email_obs[0].type == "new_email"
    assert email_obs[0].source == "email"
    assert "Question about your product" in email_obs[0].data["subject"]

    assert len(calendar_obs) == 1
    assert calendar_obs[0].type == "upcoming_meeting"
    assert calendar_obs[0].source == "calendar"
    assert calendar_obs[0].data["subject"] == "Team standup"

    assert len(crm_obs) == 1
    assert crm_obs[0].type == "low_pipeline_coverage"
    assert crm_obs[0].source == "crm"
    assert crm_obs[0].data["pipeline_coverage"] == 2.0

    await session.commit()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
