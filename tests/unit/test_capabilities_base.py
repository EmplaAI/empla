"""
Unit tests for base capability abstractions.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from empla.capabilities.base import (
    Action,
    ActionResult,
    BaseCapability,
    CapabilityConfig,
    CapabilityType,
    Observation,
)


class MockCapability(BaseCapability):
    """Mock capability for testing"""

    def __init__(self, tenant_id, employee_id, config):
        """
        Initialize a MockCapability instance and set internal state tracking flags.

        Parameters:
            tenant_id (str): Identifier of the tenant owning the capability.
            employee_id (str): Identifier of the employee associated with the capability.
            config (CapabilityConfig): Configuration for this capability instance.
        """
        super().__init__(tenant_id, employee_id, config)
        self.init_called = False
        self.perceive_called = False
        self.action_executed = None
        self.shutdown_called = False

    @property
    def capability_type(self) -> CapabilityType:
        """
        The capability type for this capability implementation.

        Returns:
            CapabilityType: The enum member `CapabilityType.EMAIL`.
        """
        return CapabilityType.EMAIL

    async def initialize(self) -> None:
        """
        Mark the capability as initialized.

        Sets internal flags to record that initialization was performed and that the capability is initialized.
        """
        self.init_called = True
        self._initialized = True

    async def perceive(self) -> list[Observation]:
        """
        Produce mock observations for testing.

        Also sets the instance flag `perceive_called` to True.

        Returns:
            list[Observation]: A list containing a single Observation with source "mock", type "test_observation", the current UTC timestamp, priority 5, and data {"test": "data"}.
        """
        self.perceive_called = True
        return [
            Observation(
                source="mock",
                type="test_observation",
                timestamp=datetime.now(UTC),
                priority=5,
                data={"test": "data"},
            )
        ]

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        """
        Execute the provided action and return a simulated execution result for testing.

        This implements the capability-specific execution logic.
        The base class execute_action() handles retry logic and error handling.

        Parameters:
                action (Action): The action to execute; its `operation` field controls simulated outcome.

        Returns:
                ActionResult: `success` is `False` with `error` set to "Simulated failure" when `action.operation == "fail"`, otherwise `success` is `True` and `output` contains {"result": "success"}.
        """
        self.action_executed = action
        if action.operation == "fail":
            return ActionResult(success=False, error="Simulated failure")
        return ActionResult(success=True, output={"result": "success"})

    async def shutdown(self) -> None:
        """
        Mark the capability as shut down for test verification.

        Sets an internal flag indicating shutdown was invoked so tests can verify shutdown behavior.
        """
        self.shutdown_called = True


# Test Models


def test_capability_type_enum():
    """Test CapabilityType enum values"""
    assert CapabilityType.EMAIL == "email"
    assert CapabilityType.CALENDAR == "calendar"
    assert CapabilityType.MESSAGING == "messaging"
    assert CapabilityType.BROWSER == "browser"


def test_capability_config():
    """Test CapabilityConfig model"""
    config = CapabilityConfig(enabled=True, rate_limit=100, timeout_seconds=60)

    assert config.enabled is True
    assert config.rate_limit == 100
    assert config.timeout_seconds == 60
    assert config.retry_policy == {"max_retries": 3, "backoff": "exponential"}


def test_observation_model():
    """Test Observation model"""
    obs = Observation(
        source="email",
        type="new_email",
        timestamp=datetime.now(UTC),
        priority=8,
        data={"email_id": "123", "from": "test@example.com"},
        requires_action=True,
    )

    assert obs.source == "email"
    assert obs.type == "new_email"
    assert obs.priority == 8
    assert obs.requires_action is True
    assert obs.data["email_id"] == "123"


def test_observation_priority_validation():
    """Test Observation priority is validated to 1-10"""
    # Valid priorities
    obs1 = Observation(
        source="test",
        type="test",
        timestamp=datetime.now(UTC),
        priority=1,
        data={},
    )
    assert obs1.priority == 1

    obs10 = Observation(
        source="test",
        type="test",
        timestamp=datetime.now(UTC),
        priority=10,
        data={},
    )
    assert obs10.priority == 10

    # Invalid priorities should raise validation error
    with pytest.raises(Exception):  # Pydantic ValidationError
        Observation(
            source="test",
            type="test",
            timestamp=datetime.now(UTC),
            priority=11,  # Too high
            data={},
        )

    with pytest.raises(Exception):
        Observation(
            source="test",
            type="test",
            timestamp=datetime.now(UTC),
            priority=0,  # Too low
            data={},
        )


def test_action_model():
    """Test Action model"""
    action = Action(
        capability="email",
        operation="send_email",
        parameters={"to": ["test@example.com"], "subject": "Test"},
        priority=7,
        context={"thread_id": "thread-123"},
    )

    assert action.capability == "email"
    assert action.operation == "send_email"
    assert action.priority == 7
    assert action.parameters["to"] == ["test@example.com"]
    assert action.context["thread_id"] == "thread-123"


def test_action_result_model():
    """Test ActionResult model"""
    # Success result
    result = ActionResult(
        success=True,
        output={"id": "456"},
        metadata={"duration_ms": 123},
    )

    assert result.success is True
    assert result.output["id"] == "456"
    assert result.error is None

    # Failure result
    result_fail = ActionResult(success=False, error="Something went wrong")

    assert result_fail.success is False
    assert result_fail.error == "Something went wrong"
    assert result_fail.output is None


# Test BaseCapability


@pytest.mark.asyncio
async def test_base_capability_initialization():
    """Test BaseCapability initialization"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    capability = MockCapability(tenant_id, employee_id, config)

    assert capability.tenant_id == tenant_id
    assert capability.employee_id == employee_id
    assert capability.config == config
    assert capability._initialized is False
    assert capability.is_healthy() is False

    # Initialize
    await capability.initialize()

    assert capability.init_called is True
    assert capability._initialized is True
    assert capability.is_healthy() is True


@pytest.mark.asyncio
async def test_base_capability_perceive():
    """Test BaseCapability perception"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    capability = MockCapability(tenant_id, employee_id, config)
    await capability.initialize()

    # Perceive
    observations = await capability.perceive()

    assert capability.perceive_called is True
    assert len(observations) == 1
    assert observations[0].source == "mock"
    assert observations[0].type == "test_observation"


@pytest.mark.asyncio
async def test_base_capability_execute_action():
    """Test BaseCapability action execution"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    capability = MockCapability(tenant_id, employee_id, config)
    await capability.initialize()

    # Execute action
    action = Action(
        capability="email",
        operation="send_email",
        parameters={"to": ["test@example.com"]},
    )

    result = await capability.execute_action(action)

    assert capability.action_executed == action
    assert result.success is True
    assert result.output["result"] == "success"


@pytest.mark.asyncio
async def test_base_capability_execute_action_failure():
    """Test BaseCapability action execution failure"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    capability = MockCapability(tenant_id, employee_id, config)
    await capability.initialize()

    # Execute action that fails
    action = Action(
        capability="email",
        operation="fail",  # This will trigger failure in mock
        parameters={},
    )

    result = await capability.execute_action(action)

    assert result.success is False
    assert result.error == "Simulated failure"


@pytest.mark.asyncio
async def test_base_capability_shutdown():
    """Test BaseCapability shutdown"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    capability = MockCapability(tenant_id, employee_id, config)
    await capability.initialize()

    # Shutdown
    await capability.shutdown()

    assert capability.shutdown_called is True


def test_base_capability_repr():
    """Test BaseCapability string representation"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    capability = MockCapability(tenant_id, employee_id, config)

    repr_str = repr(capability)
    assert "MockCapability" in repr_str
    assert "CapabilityType.EMAIL" in repr_str  # capability type (enum repr)
    assert str(employee_id) in repr_str
    assert "initialized=False" in repr_str
