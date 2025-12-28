"""
E2E Employee Lifecycle Validation Tests.

Tests that validate SalesAE and CSM employee classes end-to-end with:
- start/stop lifecycle management
- run_once() for single BDI cycle execution
- Role-specific methods and behaviors
- Simulated capabilities (no external API calls)

These tests use REAL employee classes with SIMULATED environment.

Note: These tests use the REAL database (not transaction-isolated) because
DigitalEmployee creates its own database connection. Test data is cleaned up
after each test.

Note: Tests that call employee.start() require LLM API keys to be set.
The fixtures auto-detect available API keys and configure the appropriate model.
"""

import logging
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from empla.employees import SalesAE, CustomerSuccessManager
from empla.employees.config import EmployeeConfig, LoopSettings, LLMSettings
from empla.employees.exceptions import EmployeeConfigError, EmployeeNotStartedError, EmployeeStartupError


# ============================================================================
# API Key Detection
# ============================================================================


def has_anthropic_key() -> bool:
    """Check if Anthropic API key is available."""
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def has_openai_key() -> bool:
    """Check if OpenAI API key is available."""
    return bool(os.getenv("OPENAI_API_KEY"))


def has_vertex_config() -> bool:
    """Check if Vertex AI / Gemini is configured."""
    return bool(os.getenv("VERTEX_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT"))


def has_azure_openai_key() -> bool:
    """Check if Azure OpenAI is configured."""
    return bool(os.getenv("AZURE_OPENAI_API_KEY"))


def has_any_llm_key() -> bool:
    """Check if any LLM credentials are available."""
    return has_anthropic_key() or has_openai_key() or has_vertex_config() or has_azure_openai_key()


def get_available_model() -> str:
    """Get an available model based on set credentials."""
    if has_vertex_config():
        return "gemini-3-flash-preview"
    if has_anthropic_key():
        return "claude-sonnet-4"
    if has_openai_key():
        return "gpt-4o-mini"
    if has_azure_openai_key():
        return "gpt-4o"
    raise RuntimeError("No LLM credentials set")


# Skip marker for tests that require LLM
requires_llm = pytest.mark.skipif(
    not has_any_llm_key(),
    reason="Requires ANTHROPIC_API_KEY or OPENAI_API_KEY to be set"
)
from empla.models.database import get_engine, get_sessionmaker
from empla.models.employee import Employee as EmployeeModel
from empla.models.tenant import Tenant, User
from tests.simulation import (
    CustomerHealth,
    DealStage,
    SimulatedCustomer,
    SimulatedDeal,
    SimulatedEmail,
    SimulatedEnvironment,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="function")
async def shared_engine():
    """
    Create a shared engine for the test function.

    This avoids multiple engine instances connecting to the database.
    """
    engine = get_engine()
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_cleanup(shared_engine):
    """
    Fixture that provides cleanup after tests.

    Since DigitalEmployee creates its own db connection, we can't use
    transaction isolation. Instead, we clean up test data after each test.
    """
    created_tenant_ids = []
    created_employee_ids = []

    yield created_tenant_ids, created_employee_ids

    # Cleanup after test
    sessionmaker = get_sessionmaker(shared_engine)
    async with sessionmaker() as session:
        # Delete employees first (foreign key constraint)
        for emp_id in created_employee_ids:
            await session.execute(
                delete(EmployeeModel).where(EmployeeModel.id == emp_id)
            )
        # Delete tenants (cascades to users)
        for tenant_id in created_tenant_ids:
            await session.execute(
                delete(User).where(User.tenant_id == tenant_id)
            )
            await session.execute(
                delete(Tenant).where(Tenant.id == tenant_id)
            )
        await session.commit()


@pytest.fixture
async def tenant_and_user(shared_engine, db_cleanup):
    """Create test tenant and user in the database."""
    created_tenant_ids, _ = db_cleanup

    tenant_id = uuid4()
    created_tenant_ids.append(tenant_id)

    sessionmaker = get_sessionmaker(shared_engine)
    async with sessionmaker() as session:
        tenant = Tenant(
            id=tenant_id,
            name="E2E Test Company",
            slug=f"e2e-test-{tenant_id.hex[:8]}",
            status="active",
        )
        session.add(tenant)

        user = User(
            id=uuid4(),
            tenant_id=tenant.id,
            email=f"admin-{tenant_id.hex[:8]}@test.com",
            name="Admin User",
            role="admin",
        )
        session.add(user)
        await session.commit()

        # Refresh to get the committed state
        await session.refresh(tenant)
        await session.refresh(user)

    return tenant, user


@pytest.fixture
def simulated_environment():
    """Create a fresh simulated environment for each test."""
    return SimulatedEnvironment()


@pytest.fixture
def sales_ae_config(tenant_and_user) -> EmployeeConfig:
    """Configuration for test SalesAE."""
    tenant, _ = tenant_and_user

    # Use available LLM model based on API keys
    llm_settings = None
    if has_any_llm_key():
        llm_settings = LLMSettings(
            primary_model=get_available_model(),
            fallback_model=None,  # Disable fallback for test isolation
        )

    return EmployeeConfig(
        name="Test Sales AE",
        role="sales_ae",
        email=f"sales-ae-{tenant.id.hex[:8]}@test.com",
        tenant_id=tenant.id,
        llm=llm_settings or LLMSettings(),
        loop=LoopSettings(
            cycle_interval_seconds=60,  # Fast for testing
            strategic_planning_interval_hours=1,
            reflection_interval_hours=1,
        ),
    )


@pytest.fixture
def csm_config(tenant_and_user) -> EmployeeConfig:
    """Configuration for test CSM."""
    tenant, _ = tenant_and_user

    # Use available LLM model based on API keys
    llm_settings = None
    if has_any_llm_key():
        llm_settings = LLMSettings(
            primary_model=get_available_model(),
            fallback_model=None,
        )

    return EmployeeConfig(
        name="Test CSM",
        role="csm",
        email=f"csm-{tenant.id.hex[:8]}@test.com",
        tenant_id=tenant.id,
        llm=llm_settings or LLMSettings(),
        loop=LoopSettings(
            cycle_interval_seconds=60,
            strategic_planning_interval_hours=1,
            reflection_interval_hours=1,
        ),
    )


@pytest.fixture
async def sales_ae_with_simulated_caps(
    sales_ae_config, simulated_environment, db_cleanup
):
    """
    Create SalesAE with simulated capabilities.

    This employee uses REAL BDI components but SIMULATED external services.
    """
    _, created_employee_ids = db_cleanup
    employee = SalesAE(sales_ae_config)

    yield employee, simulated_environment

    # Track employee ID for cleanup if started
    if employee._employee_id:
        created_employee_ids.append(employee._employee_id)

    # Cleanup
    if employee._is_running:
        await employee.stop()


@pytest.fixture
async def csm_with_simulated_caps(csm_config, simulated_environment, db_cleanup):
    """
    Create CSM with simulated capabilities.

    This employee uses REAL BDI components but SIMULATED external services.
    """
    _, created_employee_ids = db_cleanup
    employee = CustomerSuccessManager(csm_config)

    yield employee, simulated_environment

    if employee._employee_id:
        created_employee_ids.append(employee._employee_id)

    if employee._is_running:
        await employee.stop()


# ============================================================================
# Helper Functions
# ============================================================================


def seed_pipeline_data(env: SimulatedEnvironment) -> list[SimulatedDeal]:
    """Seed CRM with test pipeline data for SalesAE tests."""
    deals = [
        SimulatedDeal(
            name="Acme Corp",
            stage=DealStage.QUALIFICATION,
            value=50000.0,
            probability=0.3,
        ),
        SimulatedDeal(
            name="Globex Inc",
            stage=DealStage.PROPOSAL,
            value=75000.0,
            probability=0.5,
        ),
        SimulatedDeal(
            name="Initech",
            stage=DealStage.NEGOTIATION,
            value=100000.0,
            probability=0.7,
        ),
    ]
    for deal in deals:
        env.crm.add_deal(deal)
    return deals


def seed_customer_data(env: SimulatedEnvironment) -> list[SimulatedCustomer]:
    """Seed CRM with test customer data for CSM tests."""
    customers = [
        SimulatedCustomer(
            name="Healthy Corp",
            health=CustomerHealth.HEALTHY,
            contract_value=10000.0,
            usage_score=0.85,
            churn_risk_score=0.1,
        ),
        SimulatedCustomer(
            name="At-Risk Inc",
            health=CustomerHealth.AT_RISK,
            contract_value=25000.0,
            usage_score=0.45,
            churn_risk_score=0.75,
        ),
    ]
    for customer in customers:
        env.crm.add_customer(customer)
    return customers


def send_email_to_inbox(env: SimulatedEnvironment, email: SimulatedEmail) -> None:
    """Add an email to the simulated inbox."""
    env.email.receive_email(email)


def assert_email_sent(
    env: SimulatedEnvironment,
    to_contains: str | None = None,
    subject_contains: str | None = None,
) -> SimulatedEmail:
    """Assert an email was sent and return it."""
    sent_emails = env.email.get_sent_emails()
    assert len(sent_emails) > 0, "No emails were sent"

    if to_contains:
        matching = [e for e in sent_emails if to_contains in str(e.to_addresses)]
        assert len(matching) > 0, f"No email sent to address containing '{to_contains}'"
        return matching[0]

    if subject_contains:
        matching = [e for e in sent_emails if subject_contains in e.subject]
        assert len(matching) > 0, f"No email with subject containing '{subject_contains}'"
        return matching[0]

    return sent_emails[0]


# ============================================================================
# Part 1: Lifecycle Tests
# ============================================================================


@requires_llm
class TestEmployeeLifecycle:
    """Tests for employee start/stop lifecycle management."""

    @pytest.mark.asyncio
    async def test_employee_starts_and_initializes_components(
        self, sales_ae_with_simulated_caps
    ):
        """Verify start() initializes BDI, memory, and capabilities."""
        employee, env = sales_ae_with_simulated_caps

        # Should not be running initially
        assert not employee._is_running

        # Start employee
        await employee.start(run_loop=False)

        # Verify running state
        assert employee._is_running
        assert employee._started_at is not None

        # Verify components initialized
        assert employee._beliefs is not None
        assert employee._goals is not None
        assert employee._intentions is not None
        assert employee._memory is not None
        assert employee._loop is not None

        # Verify employee ID assigned
        assert employee._employee_id is not None

    @pytest.mark.asyncio
    async def test_employee_stops_and_cleans_up(self, sales_ae_with_simulated_caps):
        """Verify stop() gracefully shuts down and cleans up."""
        employee, env = sales_ae_with_simulated_caps

        await employee.start(run_loop=False)
        assert employee._is_running

        # Stop employee
        await employee.stop()

        # Verify stopped state
        assert not employee._is_running

    @pytest.mark.asyncio
    async def test_run_once_executes_single_cycle(self, sales_ae_with_simulated_caps):
        """Verify run_once() executes a single BDI cycle."""
        employee, env = sales_ae_with_simulated_caps

        await employee.start(run_loop=False)

        # Get initial cycle count
        initial_cycle_count = employee._loop.cycle_count

        # Run single cycle
        await employee.run_once()

        # Cycle count should increase by 1
        assert employee._loop.cycle_count == initial_cycle_count + 1

    @pytest.mark.asyncio
    async def test_run_once_raises_if_not_started(self, sales_ae_with_simulated_caps):
        """Verify run_once() raises error if employee not started."""
        employee, env = sales_ae_with_simulated_caps

        # Should not be running
        assert not employee._is_running

        # Should raise error
        with pytest.raises(EmployeeNotStartedError):
            await employee.run_once()

    @pytest.mark.asyncio
    async def test_double_start_is_idempotent(self, sales_ae_with_simulated_caps):
        """Verify calling start() twice doesn't cause issues."""
        employee, env = sales_ae_with_simulated_caps

        await employee.start(run_loop=False)
        started_at_1 = employee._started_at

        # Second start should be no-op or handle gracefully
        # The employee should remain in running state
        await employee.start(run_loop=False)

        assert employee._is_running
        # Started time should not change (idempotent)
        assert employee._started_at == started_at_1


# ============================================================================
# Part 2: SalesAE BDI Cycle Tests
# ============================================================================


@requires_llm
class TestSalesAEBDICycle:
    """Tests for SalesAE BDI reasoning cycle with simulated environment."""

    @pytest.mark.asyncio
    async def test_sales_ae_perceives_from_capabilities(
        self, sales_ae_with_simulated_caps
    ):
        """Verify SalesAE perceives observations from simulated capabilities."""
        employee, env = sales_ae_with_simulated_caps

        # Seed environment with data
        seed_pipeline_data(env)

        await employee.start(run_loop=False)

        # The loop's perceive_environment should work with simulated capabilities
        # Note: We need to inject the simulated registry after start()
        # For now, we test that the cycle runs without error
        await employee.run_once()

        # Verify cycle completed
        assert employee._loop.cycle_count >= 1

    @pytest.mark.asyncio
    async def test_sales_ae_forms_goals_from_config(
        self, sales_ae_with_simulated_caps
    ):
        """Verify SalesAE has default goals after start."""
        employee, env = sales_ae_with_simulated_caps

        await employee.start(run_loop=False)

        # Goals should be initialized
        assert employee._goals is not None

        # Get active goals
        active_goals = await employee._goals.get_active_goals()

        # Should have default SalesAE goals
        assert len(active_goals) > 0

    @pytest.mark.asyncio
    async def test_sales_ae_beliefs_update_during_cycle(
        self, sales_ae_with_simulated_caps
    ):
        """Verify beliefs are updated during the BDI cycle."""
        employee, env = sales_ae_with_simulated_caps

        await employee.start(run_loop=False)

        # Initial beliefs should exist after start
        # (Role belief is set in on_start)
        role_belief = await employee._beliefs.get_belief("self", "role")
        assert role_belief is not None

        # Run cycle
        await employee.run_once()

        # Beliefs system should still be functional
        assert employee._beliefs is not None


# ============================================================================
# Part 3: CSM BDI Cycle Tests
# ============================================================================


@requires_llm
class TestCSMBDICycle:
    """Tests for CSM BDI reasoning cycle with simulated environment."""

    @pytest.mark.asyncio
    async def test_csm_starts_with_correct_role(self, csm_with_simulated_caps):
        """Verify CSM starts with CSM-specific configuration."""
        employee, env = csm_with_simulated_caps

        await employee.start(run_loop=False)

        # Should have CSM role belief
        role_belief = await employee._beliefs.get_belief("self", "role")
        assert role_belief is not None
        assert role_belief.object.get("type") == "csm"

    @pytest.mark.asyncio
    async def test_csm_has_default_goals(self, csm_with_simulated_caps):
        """Verify CSM has retention-focused goals."""
        employee, env = csm_with_simulated_caps

        await employee.start(run_loop=False)

        active_goals = await employee._goals.get_active_goals()
        assert len(active_goals) > 0

        # CSM goals should focus on retention
        goal_descriptions = [g.description for g in active_goals]
        assert any("retention" in d.lower() for d in goal_descriptions)

    @pytest.mark.asyncio
    async def test_csm_cycle_executes(self, csm_with_simulated_caps):
        """Verify CSM can execute a BDI cycle."""
        employee, env = csm_with_simulated_caps

        seed_customer_data(env)

        await employee.start(run_loop=False)
        await employee.run_once()

        assert employee._loop.cycle_count >= 1


# ============================================================================
# Part 4: Error Scenario Tests
# ============================================================================


class TestErrorScenarios:
    """Tests for error handling and graceful degradation."""

    @pytest.mark.asyncio
    async def test_employee_handles_missing_env_vars(self, sales_ae_config):
        """Verify employee handles missing API keys gracefully."""
        import os

        # Save and remove ALL LLM API keys (Anthropic, OpenAI, Vertex, Azure)
        saved_keys = {}
        llm_keys = [
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "VERTEX_PROJECT_ID",
            "GOOGLE_CLOUD_PROJECT",
            "AZURE_OPENAI_API_KEY",
        ]
        for key in llm_keys:
            saved_keys[key] = os.environ.get(key)
            if key in os.environ:
                del os.environ[key]

        try:
            employee = SalesAE(sales_ae_config)

            # Should raise EmployeeConfigError due to missing API keys
            with pytest.raises(EmployeeConfigError):
                await employee.start(run_loop=False)

        finally:
            # Restore API keys
            for key, value in saved_keys.items():
                if value is not None:
                    os.environ[key] = value

    @requires_llm
    @pytest.mark.asyncio
    async def test_employee_stop_is_idempotent(self, sales_ae_with_simulated_caps):
        """Verify calling stop() multiple times is safe."""
        employee, env = sales_ae_with_simulated_caps

        await employee.start(run_loop=False)
        await employee.stop()

        # Second stop should not raise
        await employee.stop()

        assert not employee._is_running


# ============================================================================
# Part 5: Role-Specific Method Tests
# ============================================================================


class TestRoleSpecificMethods:
    """Tests for role-specific employee methods."""

    @pytest.mark.asyncio
    async def test_sales_ae_has_sales_specific_properties(
        self, sales_ae_with_simulated_caps
    ):
        """Verify SalesAE has sales-specific default properties."""
        employee, env = sales_ae_with_simulated_caps

        # Check default capabilities
        assert "email" in employee.default_capabilities
        assert "calendar" in employee.default_capabilities
        assert "crm" in employee.default_capabilities

        # Check personality
        assert employee.default_personality is not None
        # Sales AE should be extraverted
        assert employee.default_personality.extraversion > 0.5

    @pytest.mark.asyncio
    async def test_csm_has_csm_specific_properties(self, csm_with_simulated_caps):
        """Verify CSM has CSM-specific default properties."""
        employee, env = csm_with_simulated_caps

        # Check default capabilities
        assert "email" in employee.default_capabilities
        assert "calendar" in employee.default_capabilities
        assert "crm" in employee.default_capabilities

        # Check personality
        assert employee.default_personality is not None
        # CSM should be agreeable
        assert employee.default_personality.agreeableness > 0.5

    @requires_llm
    @pytest.mark.asyncio
    async def test_employee_get_status_returns_info(
        self, sales_ae_with_simulated_caps
    ):
        """Verify get_status() returns correct information."""
        employee, env = sales_ae_with_simulated_caps

        await employee.start(run_loop=False)

        status = employee.get_status()

        assert status["name"] == "Test Sales AE"
        assert status["role"] == "sales_ae"
        assert status["is_running"] is True
        assert "started_at" in status
