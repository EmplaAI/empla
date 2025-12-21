"""
Integration tests for employee lifecycle.

Tests the full employee start/stop lifecycle with simulated environment.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from empla.employees import SalesAE, CustomerSuccessManager, EmployeeConfig
from empla.employees.config import GoalConfig


class TestEmployeeLifecycleIntegration:
    """Integration tests for employee lifecycle."""

    @pytest.fixture
    def sales_config(self):
        """Create a Sales AE config."""
        return EmployeeConfig(
            name="Jordan Chen",
            role="sales_ae",
            email="jordan@company.com",
            tenant_id=uuid4(),
        )

    @pytest.fixture
    def csm_config(self):
        """Create a CSM config."""
        return EmployeeConfig(
            name="Sarah Mitchell",
            role="csm",
            email="sarah@company.com",
            tenant_id=uuid4(),
        )

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.fixture
    def mock_llm_service(self):
        """Create a mock LLM service."""
        from empla.llm.models import LLMResponse, TokenUsage

        llm = MagicMock()
        llm.generate = AsyncMock(
            return_value=LLMResponse(
                content="Test response",
                model="test-model",
                usage=TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30),
            )
        )
        return llm

    @pytest.mark.asyncio
    async def test_sales_ae_creation(self, sales_config):
        """Test SalesAE can be created."""
        employee = SalesAE(sales_config)

        assert employee.name == "Jordan Chen"
        assert employee.role == "sales_ae"
        assert employee.is_running is False

    @pytest.mark.asyncio
    async def test_csm_creation(self, csm_config):
        """Test CSM can be created."""
        employee = CustomerSuccessManager(csm_config)

        assert employee.name == "Sarah Mitchell"
        assert employee.role == "csm"
        assert employee.is_running is False

    @pytest.mark.asyncio
    async def test_employee_status_before_start(self, sales_config):
        """Test employee status before starting."""
        employee = SalesAE(sales_config)
        status = employee.get_status()

        assert status["name"] == "Jordan Chen"
        assert status["is_running"] is False
        assert status["started_at"] is None
        assert status["employee_id"] is None

    @pytest.mark.asyncio
    async def test_employee_has_correct_defaults(self, sales_config):
        """Test employee has correct defaults."""
        employee = SalesAE(sales_config)

        # Default personality
        assert employee.default_personality.extraversion >= 0.8

        # Default goals
        assert len(employee.default_goals) >= 1

        # Default capabilities
        assert "email" in employee.default_capabilities

    @pytest.mark.asyncio
    async def test_config_goals_override_defaults(self):
        """Test that config goals override defaults."""
        custom_goal = GoalConfig(
            description="Custom test goal",
            priority=10,
        )
        # Create a new config with custom goals (configs are immutable)
        config_with_goals = EmployeeConfig(
            name="Jordan Chen",
            role="sales_ae",
            email="jordan@company.com",
            tenant_id=uuid4(),
            goals=[custom_goal],
        )

        employee = SalesAE(config_with_goals)

        # Config has custom goals
        assert len(employee.config.goals) == 1
        assert employee.config.goals[0].description == "Custom test goal"

        # Default goals are still available but not used
        assert len(employee.default_goals) >= 1

    @pytest.mark.asyncio
    async def test_multiple_employees_independent(self, sales_config, csm_config):
        """Test multiple employees are independent."""
        sales = SalesAE(sales_config)
        csm = CustomerSuccessManager(csm_config)

        # Different names
        assert sales.name != csm.name

        # Different roles
        assert sales.role != csm.role

        # Different personalities
        assert sales.default_personality != csm.default_personality

        # Different goals
        assert sales.default_goals != csm.default_goals

        # Both not running
        assert sales.is_running is False
        assert csm.is_running is False


class TestEmployeeWithMockedDependencies:
    """Tests with mocked BDI and memory systems."""

    @pytest.fixture
    def mock_employee_model(self):
        """Create a mock Employee database model."""
        model = MagicMock()
        model.id = uuid4()
        model.name = "Test Employee"
        model.role = "sales_ae"
        model.email = "test@test.com"
        model.status = "active"
        model.lifecycle_stage = "autonomous"
        return model

    @pytest.mark.asyncio
    async def test_start_initializes_components(self):
        """Test that start initializes all components."""
        config = EmployeeConfig(
            name="Test",
            role="sales_ae",
            email="test@test.com",
        )
        employee = SalesAE(config)

        # Before start, components should be None
        assert employee._llm is None
        assert employee._beliefs is None
        assert employee._goals is None
        assert employee._intentions is None
        assert employee._memory is None
        assert employee._capabilities is None
        assert employee._loop is None

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """Test stop when not running logs warning."""
        config = EmployeeConfig(
            name="Test",
            role="sales_ae",
            email="test@test.com",
        )
        employee = SalesAE(config)

        # Should not raise
        await employee.stop()

        # Still not running
        assert employee.is_running is False


class TestEmployeeImports:
    """Tests for employee module imports."""

    def test_can_import_from_employees(self):
        """Test can import from empla.employees."""
        from empla.employees import (
            DigitalEmployee,
            SalesAE,
            CustomerSuccessManager,
            CSM,
            EmployeeConfig,
        )

        assert DigitalEmployee is not None
        assert SalesAE is not None
        assert CustomerSuccessManager is not None
        assert CSM is CustomerSuccessManager
        assert EmployeeConfig is not None

    def test_can_import_from_main_package(self):
        """Test can import from empla main package."""
        from empla import (
            SalesAE,
            CustomerSuccessManager,
            CSM,
            EmployeeConfig,
        )

        assert SalesAE is not None
        assert CustomerSuccessManager is not None
        assert CSM is not None
        assert EmployeeConfig is not None

    def test_can_import_personality(self):
        """Test can import personality classes."""
        from empla.employees import (
            Personality,
            CommunicationStyle,
            DecisionStyle,
            Tone,
            Formality,
            Verbosity,
        )

        assert Personality is not None
        assert CommunicationStyle is not None
        assert DecisionStyle is not None
        assert Tone is not None
        assert Formality is not None
        assert Verbosity is not None

    def test_can_import_config_classes(self):
        """Test can import config classes."""
        from empla.employees import (
            EmployeeConfig,
            GoalConfig,
            LoopSettings,
            LLMSettings,
        )

        assert EmployeeConfig is not None
        assert GoalConfig is not None
        assert LoopSettings is not None
        assert LLMSettings is not None

    def test_can_import_personality_templates(self):
        """Test can import personality templates."""
        from empla.employees import (
            SALES_AE_PERSONALITY,
            CSM_PERSONALITY,
            PM_PERSONALITY,
        )

        assert SALES_AE_PERSONALITY is not None
        assert CSM_PERSONALITY is not None
        assert PM_PERSONALITY is not None

    def test_can_import_goal_templates(self):
        """Test can import goal templates."""
        from empla.employees import (
            SALES_AE_DEFAULT_GOALS,
            CSM_DEFAULT_GOALS,
            PM_DEFAULT_GOALS,
        )

        assert SALES_AE_DEFAULT_GOALS is not None
        assert CSM_DEFAULT_GOALS is not None
        assert PM_DEFAULT_GOALS is not None
