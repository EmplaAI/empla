"""
Integration tests for capabilities + proactive loop integration.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from empla.capabilities import (
    Action,
    ActionResult,
    BaseCapability,
    CapabilityConfig,
    CapabilityRegistry,
    CapabilityType,
    Observation,
)
from empla.core.loop.execution import ProactiveExecutionLoop
from empla.core.loop.models import LoopConfig
from empla.models.employee import Employee


# Mock capability for testing
class MockTestCapability(BaseCapability):
    """Mock capability that generates test observations"""

    def __init__(self, tenant_id, employee_id, config):
        """
        Initialize the mock capability with tenant, employee, and configuration.

        Parameters:
            tenant_id: Identifier for the tenant that owns this capability.
            employee_id: Identifier for the employee associated with this capability.
            config: Configuration object used to initialize the capability for testing.

        Attributes:
            observations_to_return (list): Mutable list of Observation objects that will be returned by the mock perceive method.
        """
        super().__init__(tenant_id, employee_id, config)
        self.observations_to_return = []

    @property
    def capability_type(self) -> CapabilityType:
        """
        Capability type associated with this capability.

        Returns:
            CapabilityType: The enum value identifying this capability (`CapabilityType.EMAIL`).
        """
        return CapabilityType.EMAIL

    async def initialize(self) -> None:
        """
        Mark the capability as initialized by setting its internal initialized flag.
        """
        self._initialized = True

    async def perceive(self) -> list[Observation]:
        # Return configured observations
        """
        Return the preconfigured observations for this mock capability.

        This method supplies the observations that were assigned to the mock (via its test setup) without modification.

        Returns:
            List[Observation]: The list of observations configured on the mock; may be empty.
        """
        return self.observations_to_return

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        """
        Execute the given action in the mock capability and report a successful result.

        Parameters:
            action (Action): The action to execute.

        Returns:
            ActionResult: An ActionResult with `success` set to `True` and an `output` payload `{"test": "executed"}`.
        """
        return ActionResult(success=True, output={"test": "executed"})


# Mock BDI components
class MockBeliefSystem:
    async def update_beliefs(self, observations):
        """
        Update beliefs from a collection of observations.

        Parameters:
            observations (Iterable): Observations to incorporate into the belief store.

        Returns:
            list: A list of belief entries created or updated from the provided observations (may be empty).
        """
        return []


class MockGoalSystem:
    async def get_active_goals(self):
        """
        Retrieve the currently active goals.

        Returns:
            list: Active goals for the agent; in this mock implementation an empty list.
        """
        return []

    async def update_goal_progress(self, goal_id: Any, progress: dict[str, Any]) -> Any:
        """
        Update the progress of a given goal.

        Parameters:
            goal_id: The goal's unique identifier.
            progress: Progress data to merge with current progress.

        Returns:
            Updated goal, or None. This mock returns None.

        Notes:
            This mock implementation performs no action.
        """
        return None


class MockIntentionStack:
    async def get_next_intention(self):
        """
        Retrieve the next intention to execute, or None if none are available.
        """
        return

    async def dependencies_satisfied(self, intention):
        """
        Unconditionally report that the dependencies required to start an intention are satisfied.

        Parameters:
            intention: The intention whose dependency status is being checked.

        Returns:
            `True` indicating the intention's dependencies are satisfied.
        """
        return True

    async def start_intention(self, intention):
        """
        Start processing the given intention.

        Parameters:
            intention: The intention object to start; in this mock implementation the call is a no-op.
        """

    async def complete_intention(self, intention, result):
        """
        Complete an intention and associate it with its result.

        Parameters:
            intention: The intention object or identifier to mark as completed.
            result: The outcome or result produced by the intention's execution.

        Note:
            This mock implementation performs no action.
        """

    async def fail_intention(self, intention, error):
        """
        No-op implementation invoked when an intention fails.

        Parameters:
            intention: The intention instance that failed.
            error: The exception or error information associated with the failure.
        """


class MockMemorySystem:
    pass


# Helper to create test employee
def create_test_employee():
    """
    Create a test Employee with randomized identifiers and fixed demo attributes.

    Returns:
        Employee: An Employee instance with a random `id` and `tenant_id`, name "Test Employee", email "test@example.com", role "sales_ae", and status "active".
    """
    return Employee(
        id=uuid4(),
        tenant_id=uuid4(),
        name="Test Employee",
        email="test@example.com",
        role="sales_ae",
        status="active",
    )


# Tests


@pytest.mark.asyncio
async def test_loop_perceives_from_capability_registry():
    """Test that loop uses capability registry for perception"""

    # Create employee
    employee = create_test_employee()

    # Create capability registry
    registry = CapabilityRegistry()
    registry.register(CapabilityType.EMAIL, MockTestCapability)

    # Enable capability
    capability = await registry.enable_for_employee(
        employee_id=employee.id,
        tenant_id=employee.tenant_id,
        capability_type=CapabilityType.EMAIL,
        config=CapabilityConfig(),
    )

    # Configure capability to return observations
    capability.observations_to_return = [
        Observation(
            employee_id=employee.id,
            tenant_id=employee.tenant_id,
            observation_type="new_email",
            source="email",
            content={"email_id": "123"},
            timestamp=datetime.now(UTC),
            priority=7,
        ),
        Observation(
            employee_id=employee.id,
            tenant_id=employee.tenant_id,
            observation_type="new_email",
            source="email",
            content={"email_id": "456"},
            timestamp=datetime.now(UTC),
            priority=5,
        ),
    ]

    # Create loop with capability registry
    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=MockBeliefSystem(),
        goals=MockGoalSystem(),
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        capability_registry=registry,
        config=LoopConfig(),
    )

    # Run perception
    result = await loop.perceive_environment()

    # Assert: Observations from capability were captured
    assert len(result.observations) == 2
    assert result.observations[0].source == "email"
    assert result.observations[0].observation_type == "new_email"
    assert result.observations[0].content["email_id"] == "123"
    assert result.observations[1].content["email_id"] == "456"

    # Assert: Sources tracked (uses enum value, not enum name)
    assert "email" in result.sources_checked


@pytest.mark.asyncio
async def test_loop_perception_without_capability_registry():
    """Test that loop works without capability registry (backward compatibility)"""

    # Create employee
    employee = create_test_employee()

    # Create loop WITHOUT capability registry
    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=MockBeliefSystem(),
        goals=MockGoalSystem(),
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        capability_registry=None,  # No registry
        config=LoopConfig(),
    )

    # Run perception
    result = await loop.perceive_environment()

    # Assert: No observations (no capabilities)
    assert len(result.observations) == 0
    assert len(result.sources_checked) == 0


@pytest.mark.asyncio
async def test_loop_perception_detects_opportunities():
    """Test that loop detects opportunities from observations"""

    employee = create_test_employee()
    registry = CapabilityRegistry()
    registry.register(CapabilityType.EMAIL, MockTestCapability)

    capability = await registry.enable_for_employee(
        employee_id=employee.id,
        tenant_id=employee.tenant_id,
        capability_type=CapabilityType.EMAIL,
        config=CapabilityConfig(),
    )

    # Configure capability to return opportunity observation
    capability.observations_to_return = [
        Observation(
            employee_id=employee.id,
            tenant_id=employee.tenant_id,
            observation_type="new_opportunity",
            source="email",
            content={"lead_id": "789"},
            timestamp=datetime.now(UTC),
            priority=8,
        )
    ]

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=MockBeliefSystem(),
        goals=MockGoalSystem(),
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        capability_registry=registry,
        config=LoopConfig(),
    )

    result = await loop.perceive_environment()

    # Assert: Opportunity detected
    assert result.opportunities_detected == 1
    assert result.problems_detected == 0
    assert result.risks_detected == 0


@pytest.mark.asyncio
async def test_loop_perception_detects_problems():
    """Test that loop detects problems from observations"""

    employee = create_test_employee()
    registry = CapabilityRegistry()
    registry.register(CapabilityType.EMAIL, MockTestCapability)

    capability = await registry.enable_for_employee(
        employee_id=employee.id,
        tenant_id=employee.tenant_id,
        capability_type=CapabilityType.EMAIL,
        config=CapabilityConfig(),
    )

    # Configure capability to return problem observation
    capability.observations_to_return = [
        Observation(
            employee_id=employee.id,
            tenant_id=employee.tenant_id,
            observation_type="customer_problem",
            source="email",
            content={"issue": "System down"},
            timestamp=datetime.now(UTC),
            priority=9,
        )
    ]

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=MockBeliefSystem(),
        goals=MockGoalSystem(),
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        capability_registry=registry,
        config=LoopConfig(),
    )

    result = await loop.perceive_environment()

    # Assert: Problem detected
    assert result.problems_detected == 1
    assert result.opportunities_detected == 0


@pytest.mark.asyncio
async def test_loop_perception_detects_high_priority_as_risk():
    """Test that high priority observations (>=9) are detected as risks"""

    employee = create_test_employee()
    registry = CapabilityRegistry()
    registry.register(CapabilityType.EMAIL, MockTestCapability)

    capability = await registry.enable_for_employee(
        employee_id=employee.id,
        tenant_id=employee.tenant_id,
        capability_type=CapabilityType.EMAIL,
        config=CapabilityConfig(),
    )

    # Configure capability to return high-priority observation
    capability.observations_to_return = [
        Observation(
            employee_id=employee.id,
            tenant_id=employee.tenant_id,
            observation_type="urgent_email",
            source="email",
            content={"urgent": True},
            timestamp=datetime.now(UTC),
            priority=10,  # Very high priority
        )
    ]

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=MockBeliefSystem(),
        goals=MockGoalSystem(),
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        capability_registry=registry,
        config=LoopConfig(),
    )

    result = await loop.perceive_environment()

    # Assert: High priority treated as risk
    assert result.risks_detected == 1


@pytest.mark.asyncio
async def test_loop_perception_handles_multiple_capabilities():
    """Test that loop perceives from multiple capabilities"""

    # Create a second mock capability type
    class MockCalendarCapability(MockTestCapability):
        @property
        def capability_type(self) -> CapabilityType:
            """
            Identifies this capability as the calendar capability.

            Returns:
                CapabilityType: The enum value `CapabilityType.CALENDAR`.
            """
            return CapabilityType.CALENDAR

    employee = create_test_employee()
    registry = CapabilityRegistry()
    registry.register(CapabilityType.EMAIL, MockTestCapability)
    registry.register(CapabilityType.CALENDAR, MockCalendarCapability)

    # Enable both capabilities
    email_cap = await registry.enable_for_employee(
        employee_id=employee.id,
        tenant_id=employee.tenant_id,
        capability_type=CapabilityType.EMAIL,
        config=CapabilityConfig(),
    )

    calendar_cap = await registry.enable_for_employee(
        employee_id=employee.id,
        tenant_id=employee.tenant_id,
        capability_type=CapabilityType.CALENDAR,
        config=CapabilityConfig(),
    )

    # Configure both to return observations
    email_cap.observations_to_return = [
        Observation(
            employee_id=employee.id,
            tenant_id=employee.tenant_id,
            observation_type="new_email",
            source="email",
            content={"email_id": "123"},
            timestamp=datetime.now(UTC),
            priority=5,
        )
    ]

    calendar_cap.observations_to_return = [
        Observation(
            employee_id=employee.id,
            tenant_id=employee.tenant_id,
            observation_type="meeting_soon",
            source="calendar",
            content={"event_id": "456"},
            timestamp=datetime.now(UTC),
            priority=8,
        )
    ]

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=MockBeliefSystem(),
        goals=MockGoalSystem(),
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        capability_registry=registry,
        config=LoopConfig(),
    )

    result = await loop.perceive_environment()

    # Assert: Observations from both capabilities
    assert len(result.observations) == 2
    sources = [obs.source for obs in result.observations]
    assert "email" in sources
    assert "calendar" in sources

    # Assert: Both sources tracked
    assert len(result.sources_checked) == 2
