"""
E2E Runner Smoke Test.

Verifies the full startup → one BDI cycle → shutdown path works
with a mocked LLM. This proves:
1. LLM is wired into the loop (bug #1 fix)
2. Goal creation with free-form types works (bug #2 fix)
3. The entire BDI reasoning pipeline runs without errors

No real LLM API keys required — uses deterministic mock responses.
"""

import logging
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from empla.core.loop.execution import SituationAnalysis
from empla.employees import SalesAE
from empla.employees.config import EmployeeConfig, LLMSettings, LoopSettings
from empla.llm.models import LLMResponse, TokenUsage
from empla.models.database import get_engine, get_sessionmaker
from empla.models.employee import Employee as EmployeeModel
from empla.models.employee import EmployeeGoal, EmployeeIntention
from empla.models.tenant import Tenant, User

logger = logging.getLogger(__name__)


# ============================================================================
# Mock LLM responses
# ============================================================================

MOCK_SITUATION_ANALYSIS = SituationAnalysis(
    current_state_summary="Employee just started, no pipeline data yet",
    gaps=["No active deals in pipeline"],
    opportunities=["Reach out to inbound leads from website"],
    problems=["Pipeline coverage below target"],
    recommended_focus="Build initial pipeline through outbound prospecting",
)

MOCK_LLM_RESPONSE = LLMResponse(
    content="Understood. Focusing on pipeline building.",
    model="mock-model",
    usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
    finish_reason="end_turn",
)


def make_mock_llm_service() -> AsyncMock:
    """Create a mock LLM service that returns deterministic responses."""
    mock = AsyncMock()

    # generate_structured returns (LLMResponse, parsed_model)
    mock.generate_structured = AsyncMock(return_value=(MOCK_LLM_RESPONSE, MOCK_SITUATION_ANALYSIS))

    # generate returns LLMResponse
    mock.generate = AsyncMock(return_value=MOCK_LLM_RESPONSE)

    # generate_with_tools returns LLMResponse (no tool calls)
    mock.generate_with_tools = AsyncMock(
        return_value=LLMResponse(
            content="No actions needed right now.",
            model="mock-model",
            usage=TokenUsage(input_tokens=50, output_tokens=20, total_tokens=70),
            finish_reason="end_turn",
            tool_calls=None,
        )
    )

    # close is a no-op
    mock.close = AsyncMock()

    return mock


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="function")
async def shared_engine() -> AsyncGenerator[AsyncEngine]:
    """Create a shared engine for the test function."""
    engine = get_engine()
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_cleanup(shared_engine: AsyncEngine) -> AsyncGenerator[list[UUID]]:
    """Clean up test data after each test."""
    created_tenant_ids: list[UUID] = []

    yield created_tenant_ids

    sessionmaker = get_sessionmaker(shared_engine)
    async with sessionmaker() as session:
        for tenant_id in created_tenant_ids:
            # Delete in order respecting foreign keys
            await session.execute(
                delete(EmployeeIntention).where(EmployeeIntention.tenant_id == tenant_id)
            )
            await session.execute(delete(EmployeeGoal).where(EmployeeGoal.tenant_id == tenant_id))
            await session.execute(delete(EmployeeModel).where(EmployeeModel.tenant_id == tenant_id))
            await session.execute(delete(User).where(User.tenant_id == tenant_id))
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        await session.commit()


@pytest.fixture
async def tenant_and_user(
    shared_engine: AsyncEngine, db_cleanup: list[UUID]
) -> tuple[Tenant, User]:
    """Create test tenant and user in the database."""
    created_tenant_ids = db_cleanup

    tenant_id = uuid4()
    created_tenant_ids.append(tenant_id)

    sessionmaker = get_sessionmaker(shared_engine)
    async with sessionmaker() as session:
        tenant = Tenant(
            id=tenant_id,
            name="Runner Smoke Test",
            slug=f"runner-smoke-{tenant_id.hex[:8]}",
            status="active",
        )
        session.add(tenant)

        user = User(
            id=uuid4(),
            tenant_id=tenant.id,
            email=f"admin-{tenant_id.hex[:8]}@smoke-test.com",
            name="Admin User",
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(tenant)
        await session.refresh(user)

    return tenant, user


# ============================================================================
# Tests
# ============================================================================


class TestRunnerSmoke:
    """Smoke tests for the full employee → loop → BDI cycle path."""

    @pytest.mark.asyncio
    async def test_sales_ae_runs_one_bdi_cycle_with_llm(
        self, tenant_and_user: tuple[Tenant, User]
    ) -> None:
        """
        Verify a SalesAE can start, run one BDI cycle, and stop cleanly.

        This is the primary smoke test. It proves:
        - LLM service is wired into the loop (bug #1)
        - The full BDI cycle runs (perceive → beliefs → strategic planning → execute)
        - No DB constraint violations on goal creation (bug #2)
        """
        tenant, _ = tenant_and_user

        config = EmployeeConfig(
            name="Smoke Test Sales AE",
            role="sales_ae",
            email=f"smoke-ae-{tenant.id.hex[:8]}@test.com",
            tenant_id=tenant.id,
            llm=LLMSettings(primary_model="mock-model"),
            loop=LoopSettings(
                cycle_interval_seconds=60,
                strategic_planning_interval_hours=1,
                reflection_interval_hours=1,
            ),
        )

        employee = SalesAE(config)
        mock_llm = make_mock_llm_service()

        try:
            # Patch LLMService construction so employee.start() uses our mock
            with patch("empla.employees.base.LLMService", return_value=mock_llm):
                await employee.start(run_loop=False)

            # Verify the loop has an LLM service (bug #1 fix)
            assert employee._loop is not None, "Loop should be initialized"
            assert employee._loop.llm_service is not None, (
                "LLM service should be wired into the loop"
            )

            # Run one BDI cycle
            await employee.run_once()

            # The LLM should have been called (strategic planning ran)
            assert mock_llm.generate_structured.call_count > 0, (
                "LLM generate_structured should have been called during strategic planning"
            )

            logger.info(
                f"LLM calls: generate_structured={mock_llm.generate_structured.call_count}, "
                f"generate={mock_llm.generate.call_count}"
            )

        finally:
            if employee._is_running:
                await employee.stop()

    @pytest.mark.asyncio
    async def test_loop_llm_service_is_not_none(self, tenant_and_user: tuple[Tenant, User]) -> None:
        """
        Directly verify that _init_loop wires llm_service into the loop.

        Minimal test that specifically targets bug #1.
        """
        tenant, _ = tenant_and_user

        config = EmployeeConfig(
            name="LLM Wire Test",
            role="sales_ae",
            email=f"wire-test-{tenant.id.hex[:8]}@test.com",
            tenant_id=tenant.id,
            llm=LLMSettings(primary_model="mock-model"),
            loop=LoopSettings(cycle_interval_seconds=60),
        )

        employee = SalesAE(config)
        mock_llm = make_mock_llm_service()

        try:
            with patch("empla.employees.base.LLMService", return_value=mock_llm):
                await employee.start(run_loop=False)

            # The critical assertion: loop.llm_service should be the mock, not None
            assert employee._loop is not None
            assert employee._loop.llm_service is mock_llm, (
                "Loop's llm_service should be the same instance as employee._llm"
            )

        finally:
            if employee._is_running:
                await employee.stop()

    @pytest.mark.asyncio
    async def test_freeform_goal_types_persisted_in_db(
        self,
        tenant_and_user: tuple[Tenant, User],
        shared_engine: AsyncEngine,
    ) -> None:
        """
        Verify that goals with free-form types are actually persisted in the DB.

        The mock LLM returns a SituationAnalysis with opportunities and problems,
        which triggers _manage_goals_from_analysis to create goals with
        goal_type='opportunity' and 'problem'. Before bug #2 fix, this would
        violate the DB CHECK constraint and the error was silently swallowed.

        This test queries the DB to prove goals were actually created, not just
        that the cycle completed without raising.
        """
        tenant, _ = tenant_and_user

        config = EmployeeConfig(
            name="Goal Type Test AE",
            role="sales_ae",
            email=f"goal-test-{tenant.id.hex[:8]}@test.com",
            tenant_id=tenant.id,
            llm=LLMSettings(primary_model="mock-model"),
            loop=LoopSettings(
                cycle_interval_seconds=60,
                strategic_planning_interval_hours=1,
                reflection_interval_hours=1,
            ),
        )

        employee = SalesAE(config)
        mock_llm = make_mock_llm_service()

        try:
            with patch("empla.employees.base.LLMService", return_value=mock_llm):
                await employee.start(run_loop=False)

            # Run cycle — this triggers strategic planning which calls
            # _manage_goals_from_analysis with opportunity/problem goal types
            await employee.run_once()

            # Verify that strategic planning actually ran
            assert mock_llm.generate_structured.call_count > 0

            # Query through the employee's own GoalSystem to verify goals with
            # free-form types were actually persisted. We use the employee's
            # session because goals are flushed (not committed) during the cycle,
            # so an external session wouldn't see them.
            all_goals = await employee._goals.get_active_goals()
            freeform_goals = [g for g in all_goals if g.goal_type in ("opportunity", "problem")]
            assert len(freeform_goals) > 0, (
                "Expected goals with type 'opportunity' or 'problem' to be persisted. "
                "If this fails, the CHECK constraint may still be blocking goal creation."
            )

        finally:
            if employee._is_running:
                await employee.stop()

    @pytest.mark.asyncio
    async def test_employee_start_stop_lifecycle(
        self, tenant_and_user: tuple[Tenant, User]
    ) -> None:
        """Verify clean start → stop lifecycle with mocked LLM."""
        tenant, _ = tenant_and_user

        config = EmployeeConfig(
            name="Lifecycle Test AE",
            role="sales_ae",
            email=f"lifecycle-{tenant.id.hex[:8]}@test.com",
            tenant_id=tenant.id,
            llm=LLMSettings(primary_model="mock-model"),
            loop=LoopSettings(cycle_interval_seconds=60),
        )

        employee = SalesAE(config)
        mock_llm = make_mock_llm_service()

        with patch("empla.employees.base.LLMService", return_value=mock_llm):
            await employee.start(run_loop=False)

        assert employee._is_running
        assert employee._beliefs is not None
        assert employee._goals is not None
        assert employee._intentions is not None
        assert employee._loop is not None

        await employee.stop()
        assert not employee._is_running
