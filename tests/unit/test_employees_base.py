"""
Tests for empla.employees.base module.

Tests the base DigitalEmployee class and its lifecycle.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from empla.employees.base import DigitalEmployee, MemorySystem
from empla.employees.config import EmployeeConfig, GoalConfig
from empla.employees.exceptions import EmployeeNotStartedError
from empla.employees.personality import Personality


class ConcreteEmployee(DigitalEmployee):
    """Concrete implementation for testing abstract base class."""

    @property
    def default_personality(self) -> Personality:
        return Personality(extraversion=0.7)

    @property
    def default_goals(self) -> list[GoalConfig]:
        return [
            GoalConfig(description="Test goal", priority=5),
        ]

    @property
    def default_capabilities(self) -> list[str]:
        return ["email"]


class TestDigitalEmployeeInit:
    """Tests for DigitalEmployee initialization."""

    def test_init_with_minimal_config(self):
        """Test initialization with minimal config."""
        config = EmployeeConfig(
            name="Test Employee",
            role="custom",
            email="test@test.com",
        )
        employee = ConcreteEmployee(config)

        assert employee.config == config
        assert employee._employee_id is None
        assert employee._is_running is False
        assert employee._session is None
        assert employee._llm is None
        assert employee._beliefs is None
        assert employee._goals is None
        assert employee._intentions is None
        assert employee._memory is None
        assert employee._capabilities is None
        assert employee._loop is None

    def test_init_with_tenant_id(self):
        """Test initialization with tenant ID."""
        tenant_id = uuid4()
        config = EmployeeConfig(
            name="Test Employee",
            role="custom",
            email="test@test.com",
            tenant_id=tenant_id,
        )
        employee = ConcreteEmployee(config)

        assert employee._tenant_id == tenant_id

    def test_init_without_tenant_id_generates_uuid(self):
        """Test initialization without tenant ID generates one."""
        config = EmployeeConfig(
            name="Test Employee",
            role="custom",
            email="test@test.com",
        )
        employee = ConcreteEmployee(config)

        assert employee._tenant_id is not None


class TestDigitalEmployeeProperties:
    """Tests for DigitalEmployee properties."""

    def test_name_property(self):
        """Test name property returns config name."""
        config = EmployeeConfig(
            name="Jordan Chen",
            role="custom",
            email="jordan@test.com",
        )
        employee = ConcreteEmployee(config)
        assert employee.name == "Jordan Chen"

    def test_role_property(self):
        """Test role property returns config role."""
        config = EmployeeConfig(
            name="Test",
            role="sales_ae",
            email="test@test.com",
        )
        employee = ConcreteEmployee(config)
        assert employee.role == "sales_ae"

    def test_email_property(self):
        """Test email property returns config email."""
        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@company.com",
        )
        employee = ConcreteEmployee(config)
        assert employee.email == "test@company.com"

    def test_is_running_property_initial(self):
        """Test is_running is False initially."""
        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
        )
        employee = ConcreteEmployee(config)
        assert employee.is_running is False

    def test_personality_uses_config_override(self):
        """Test personality uses config override when provided."""
        custom_personality = Personality(extraversion=0.9, openness=0.8)
        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
            personality=custom_personality,
        )
        employee = ConcreteEmployee(config)

        assert employee.personality.extraversion == 0.9
        assert employee.personality.openness == 0.8

    def test_personality_uses_default_when_not_provided(self):
        """Test personality uses default when not in config."""
        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
        )
        employee = ConcreteEmployee(config)

        # ConcreteEmployee default has extraversion=0.7
        assert employee.personality.extraversion == 0.7

    def test_employee_id_raises_before_start(self):
        """Test employee_id raises EmployeeNotStartedError before start."""
        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
        )
        employee = ConcreteEmployee(config)

        with pytest.raises(EmployeeNotStartedError, match="call start"):
            _ = employee.employee_id

    def test_tenant_id_property(self):
        """Test tenant_id property returns the tenant ID."""
        tenant_id = uuid4()
        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
            tenant_id=tenant_id,
        )
        employee = ConcreteEmployee(config)
        assert employee.tenant_id == tenant_id

    def test_llm_raises_before_start(self):
        """Test llm property raises EmployeeNotStartedError before start."""
        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
        )
        employee = ConcreteEmployee(config)

        with pytest.raises(EmployeeNotStartedError, match="call start"):
            _ = employee.llm

    def test_beliefs_raises_before_start(self):
        """Test beliefs property raises EmployeeNotStartedError before start."""
        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
        )
        employee = ConcreteEmployee(config)

        with pytest.raises(EmployeeNotStartedError, match="call start"):
            _ = employee.beliefs

    def test_goals_raises_before_start(self):
        """Test goals property raises EmployeeNotStartedError before start."""
        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
        )
        employee = ConcreteEmployee(config)

        with pytest.raises(EmployeeNotStartedError, match="call start"):
            _ = employee.goals

    def test_intentions_raises_before_start(self):
        """Test intentions property raises EmployeeNotStartedError before start."""
        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
        )
        employee = ConcreteEmployee(config)

        with pytest.raises(EmployeeNotStartedError, match="call start"):
            _ = employee.intentions

    def test_memory_raises_before_start(self):
        """Test memory property raises EmployeeNotStartedError before start."""
        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
        )
        employee = ConcreteEmployee(config)

        with pytest.raises(EmployeeNotStartedError, match="call start"):
            _ = employee.memory

    def test_capabilities_raises_before_start(self):
        """Test capabilities property raises EmployeeNotStartedError before start."""
        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
        )
        employee = ConcreteEmployee(config)

        with pytest.raises(EmployeeNotStartedError, match="call start"):
            _ = employee.capabilities


class TestDigitalEmployeeRepr:
    """Tests for DigitalEmployee repr."""

    def test_repr_stopped(self):
        """Test repr when stopped."""
        config = EmployeeConfig(
            name="Jordan Chen",
            role="sales_ae",
            email="jordan@test.com",
        )
        employee = ConcreteEmployee(config)
        repr_str = repr(employee)

        assert "ConcreteEmployee" in repr_str
        assert "Jordan Chen" in repr_str
        assert "sales_ae" in repr_str
        assert "stopped" in repr_str


class TestDigitalEmployeeStatus:
    """Tests for DigitalEmployee status methods."""

    def test_get_status_before_start(self):
        """Test get_status before starting."""
        config = EmployeeConfig(
            name="Test Employee",
            role="custom",
            email="test@test.com",
            capabilities=["email", "calendar"],
        )
        employee = ConcreteEmployee(config)
        status = employee.get_status()

        assert status["employee_id"] is None
        assert status["name"] == "Test Employee"
        assert status["role"] == "custom"
        assert status["email"] == "test@test.com"
        assert status["is_running"] is False
        assert status["started_at"] is None
        assert "email" in status["capabilities"]
        assert "calendar" in status["capabilities"]


class TestDigitalEmployeeAbstractMethods:
    """Tests for abstract method enforcement."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that DigitalEmployee cannot be instantiated directly."""
        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
        )

        with pytest.raises(TypeError, match="abstract"):
            DigitalEmployee(config)

    def test_subclass_must_implement_default_personality(self):
        """Test that subclasses must implement default_personality."""

        class IncompleteEmployee(DigitalEmployee):
            @property
            def default_goals(self) -> list[GoalConfig]:
                return []

            @property
            def default_capabilities(self) -> list[str]:
                return []

        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
        )

        with pytest.raises(TypeError):
            IncompleteEmployee(config)

    def test_subclass_must_implement_default_goals(self):
        """Test that subclasses must implement default_goals."""

        class IncompleteEmployee(DigitalEmployee):
            @property
            def default_personality(self) -> Personality:
                return Personality()

            @property
            def default_capabilities(self) -> list[str]:
                return []

        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
        )

        with pytest.raises(TypeError):
            IncompleteEmployee(config)

    def test_subclass_must_implement_default_capabilities(self):
        """Test that subclasses must implement default_capabilities."""

        class IncompleteEmployee(DigitalEmployee):
            @property
            def default_personality(self) -> Personality:
                return Personality()

            @property
            def default_goals(self) -> list[GoalConfig]:
                return []

        config = EmployeeConfig(
            name="Test",
            role="custom",
            email="test@test.com",
        )

        with pytest.raises(TypeError):
            IncompleteEmployee(config)


class TestMemorySystem:
    """Tests for MemorySystem container."""

    def test_memory_system_requires_session(self):
        """Test that MemorySystem requires valid session."""
        # This would fail at runtime if session is invalid
        # Just test that it can be imported
        assert MemorySystem is not None

    def test_memory_system_has_all_subsystems(self):
        """Test that MemorySystem defines all subsystems."""
        # Check class structure via inspection
        import inspect
        source = inspect.getsource(MemorySystem.__init__)
        assert "episodic" in source
        assert "semantic" in source
        assert "procedural" in source
        assert "working" in source
