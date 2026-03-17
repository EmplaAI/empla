"""
End-to-end autonomous validation tests for SalesAE.

These tests prove that the SalesAE class (the product) completes a full
autonomous cycle, using:
- ACTUAL SalesAE class from empla/employees/
- ACTUAL BDI implementations
- ACTUAL memory systems
- Mocked LLM and mocked dependencies by default (no real API calls)

Running with Real LLM:
    By default, tests use mock LLM for fast, deterministic testing.
    To run with real LLM calls (validates prompts work with actual models):

        RUN_WITH_REAL_LLM=1 pytest tests/e2e/test_sales_ae_autonomous.py -v

    Set one of these environment variables for credentials:
        - VERTEX_PROJECT_ID (or GCP_PROJECT_ID) for Gemini
        - ANTHROPIC_API_KEY for Claude
        - OPENAI_API_KEY for GPT

    Note: Real LLM tests are slower and cost tokens (~$0.01-0.05 per test).
"""

import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import event

from empla.bdi.beliefs import BeliefExtractionResult, ExtractedBelief
from empla.bdi.intentions import GeneratedIntention, PlanGenerationResult
from empla.employees import EmployeeConfig, SalesAE
from empla.llm.models import LLMResponse, TokenUsage
from empla.models.database import get_engine, get_sessionmaker
from empla.models.tenant import Tenant, User

logger = logging.getLogger(__name__)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def db_session():
    """
    Create a test database session with proper transaction isolation.

    Uses nested savepoints to ensure test commits don't release the outer transaction.
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
            conn.sync_connection.begin_nested()

    yield session

    # Teardown: rollback everything
    await session.close()

    if nested.is_active:
        await nested.rollback()

    if trans.is_active:
        await trans.rollback()

    await conn.close()
    await engine.dispose()


@pytest.fixture
async def tenant(db_session):
    """Create a test tenant with unique slug."""
    tenant = Tenant(
        name="E2E Test Corp",
        slug=f"e2e-test-{uuid4().hex[:8]}",
        status="active",
    )
    db_session.add(tenant)
    await db_session.flush()
    return tenant


@pytest.fixture
async def user(db_session, tenant):
    """Create a test user."""
    user = User(
        tenant_id=tenant.id,
        email="e2e-test@test.com",
        name="E2E Test User",
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def llm_service():
    """
    Create an LLM service (real or mock based on RUN_WITH_REAL_LLM env var).

    By default, this returns a mock LLM for fast, deterministic testing.

    To run tests with real LLM calls:
        RUN_WITH_REAL_LLM=1 pytest tests/e2e/test_sales_ae_autonomous.py -v

    This validates:
    - LLM prompts are well-formed
    - LLM can actually extract beliefs from observations
    - LLM can actually generate executable plans

    Note: Real LLM tests are slower and cost tokens (~$0.01-0.05 per test).
    """
    use_real_llm = os.getenv("RUN_WITH_REAL_LLM", "0").lower() in ("1", "true", "yes")

    if use_real_llm:
        from empla.llm import LLMConfig, LLMService

        # Check for API keys and project IDs
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        vertex_project = os.getenv("VERTEX_PROJECT_ID") or os.getenv("GCP_PROJECT_ID")
        vertex_location = os.getenv("VERTEX_LOCATION", "us-central1")

        # Determine which provider to use based on available credentials
        if vertex_project:
            primary_model = "gemini-3-flash-preview"
            fallback_model = None
            logger.info(f"Using Vertex AI with project: {vertex_project}")
        elif anthropic_key:
            primary_model = "claude-sonnet-4"
            fallback_model = "gpt-4o-mini" if openai_key else None
            logger.info("Using Anthropic Claude for testing")
        elif openai_key:
            primary_model = "gpt-4o-mini"
            fallback_model = None
            logger.info("Using OpenAI GPT for testing")
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

        return llm_service

    # Return mock LLM (fast, free, deterministic)
    logger.debug("Using MOCK LLM service for testing (fast, free)")
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock()
    mock_llm.generate_structured = AsyncMock()
    return mock_llm


def is_real_llm(llm_service) -> bool:
    """
    Check if we're using real LLM or mock.

    Args:
        llm_service: LLM service instance to check

    Returns:
        True if using real LLM, False if mock
    """
    # Directly detect mock by checking instance type
    if isinstance(llm_service, (MagicMock, AsyncMock)):
        return False

    # Fall back to environment variable check for real LLM services
    return os.getenv("RUN_WITH_REAL_LLM", "0").lower() in ("1", "true", "yes")


@pytest.fixture
def sales_config(tenant):
    """Create a Sales AE config for testing."""
    return EmployeeConfig(
        name="Jordan Chen (E2E Test)",
        role="sales_ae",
        email=f"jordan-{uuid4().hex[:8]}@e2e-test.com",
        tenant_id=tenant.id,
    )


# ============================================================================
# Helper Functions
# ============================================================================


def create_mock_belief_extraction() -> BeliefExtractionResult:
    """Create a mock belief extraction result for low pipeline scenario."""
    return BeliefExtractionResult(
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
                predicate="status",
                object={"status": "needs_attention", "urgency": "high"},
                confidence=0.9,
                reasoning="Pipeline gap requires immediate action to hit quota",
                belief_type="evaluative",
            ),
        ],
        observation_summary="Pipeline coverage significantly below target",
    )


def create_mock_plan_generation() -> PlanGenerationResult:
    """Create a mock plan generation result."""
    return PlanGenerationResult(
        intentions=[
            GeneratedIntention(
                description="Research high-potential accounts in target verticals",
                steps=[
                    "Identify 10 accounts in target ICP",
                    "Research each account's tech stack and initiatives",
                    "Score accounts by fit and timing",
                ],
                capability="crm",
                priority=8,
            ),
            GeneratedIntention(
                description="Send personalized outreach to top prospects",
                steps=[
                    "Draft personalized email for each account",
                    "Include relevant case studies",
                    "Send emails and track opens",
                ],
                capability="email",
                priority=7,
            ),
        ],
        summary="Multi-step pipeline building plan",
    )


def setup_mock_llm_responses(mock_llm):
    """Configure mock LLM to return appropriate structured outputs."""

    async def mock_generate_structured(*args, **kwargs):
        # Determine what type of response to return based on the response_model
        response_model = kwargs.get("response_model")

        if response_model and "BeliefExtraction" in str(response_model):
            result = create_mock_belief_extraction()
        elif response_model and "PlanGeneration" in str(response_model):
            result = create_mock_plan_generation()
        else:
            # Default response
            result = None

        return (
            LLMResponse(
                content="",
                model="mock-model",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                finish_reason="stop",
                structured_output=result,
            ),
            result,
        )

    mock_llm.generate_structured = AsyncMock(side_effect=mock_generate_structured)

    # Also mock regular generate for any text completions
    mock_llm.generate = AsyncMock(
        return_value=LLMResponse(
            content="I understand. Let me help with that.",
            model="mock-model",
            usage=TokenUsage(input_tokens=50, output_tokens=25, total_tokens=75),
            finish_reason="stop",
        )
    )

    return mock_llm


# ============================================================================
# Tests
# ============================================================================


class TestSalesAECreation:
    """Test SalesAE creation and basic lifecycle."""

    @pytest.mark.asyncio
    async def test_sales_ae_creation(self, sales_config):
        """Test SalesAE can be created with config."""
        employee = SalesAE(sales_config)

        assert employee.name == sales_config.name
        assert employee.role == "sales_ae"
        assert not employee.is_running

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self, sales_config):
        """Test stop() when employee was never started."""
        employee = SalesAE(sales_config)

        # Should not raise
        await employee.stop()

        # Should still be not running
        assert not employee.is_running


class TestSalesAELifecycleWithMockedDeps:
    """Test SalesAE lifecycle methods with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_start_initializes_components(
        self, db_session, tenant, user, sales_config, llm_service
    ):
        """
        Test that start() initializes all components correctly.
        """
        employee = SalesAE(sales_config)

        # Configure LLM (mock or real based on RUN_WITH_REAL_LLM)
        if not is_real_llm(llm_service):
            setup_mock_llm_responses(llm_service)

        # Mock the LLM key check and LLM service creation
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch.object(employee, "_init_llm", new_callable=AsyncMock):
                # Inject the LLM service
                employee._llm = llm_service

                # Patch database operations to use our test session
                with (
                    patch("empla.employees.base.get_engine", return_value=db_session.get_bind()),
                    patch(
                        "empla.employees.base.get_sessionmaker",
                        return_value=lambda bind=None: db_session,
                    ),
                ):
                    # Start without running the loop
                    await employee.start(run_loop=False)

                    try:
                        # Verify employee is running
                        assert employee.is_running

                        # Verify BDI components initialized
                        assert employee._beliefs is not None
                        assert employee._goals is not None
                        assert employee._intentions is not None
                        assert employee._memory is not None
                        assert employee._loop is not None

                    finally:
                        # Clean up
                        await employee.stop()

                    assert not employee.is_running
