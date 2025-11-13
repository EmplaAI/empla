"""
Integration tests for capabilities + proactive loop integration.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from typing import List

from empla.capabilities import (
    BaseCapability,
    CapabilityType,
    CapabilityConfig,
    Observation,
    Action,
    ActionResult,
    CapabilityRegistry,
)
from empla.core.loop.execution import ProactiveExecutionLoop
from empla.core.loop.models import LoopConfig
from empla.models.employee import Employee


# Mock capability for testing
class MockTestCapability(BaseCapability):
    """Mock capability that generates test observations"""

    def __init__(self, tenant_id, employee_id, config):
        super().__init__(tenant_id, employee_id, config)
        self.observations_to_return = []

    @property
    def capability_type(self) -> CapabilityType:
        return CapabilityType.EMAIL

    async def initialize(self) -> None:
        self._initialized = True

    async def perceive(self) -> List[Observation]:
        # Return configured observations
        return self.observations_to_return

    async def execute_action(self, action: Action) -> ActionResult:
        return ActionResult(success=True, output={"test": "executed"})


# Mock BDI components
class MockBeliefSystem:
    async def update_beliefs(self, observations):
        return []


class MockGoalSystem:
    async def get_active_goals(self):
        return []

    async def update_goal_progress(self, goal, beliefs):
        pass


class MockIntentionStack:
    async def get_next_intention(self):
        return None

    async def dependencies_satisfied(self, intention):
        return True

    async def start_intention(self, intention):
        pass

    async def complete_intention(self, intention, result):
        pass

    async def fail_intention(self, intention, error):
        pass


class MockMemorySystem:
    pass


# Helper to create test employee
def create_test_employee():
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
            source="email",
            type="new_email",
            timestamp=datetime.now(timezone.utc),
            priority=7,
            data={"email_id": "123"},
        ),
        Observation(
            source="email",
            type="new_email",
            timestamp=datetime.now(timezone.utc),
            priority=5,
            data={"email_id": "456"},
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

    # Assert: Sources tracked
    assert "CapabilityType.EMAIL" in result.sources_checked


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
            source="email",
            type="new_opportunity",
            timestamp=datetime.now(timezone.utc),
            priority=8,
            data={"lead_id": "789"},
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
            source="email",
            type="customer_problem",
            timestamp=datetime.now(timezone.utc),
            priority=9,
            data={"issue": "System down"},
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
            source="email",
            type="urgent_email",
            timestamp=datetime.now(timezone.utc),
            priority=10,  # Very high priority
            data={"urgent": True},
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
            source="email",
            type="new_email",
            timestamp=datetime.now(timezone.utc),
            priority=5,
            data={"email_id": "123"},
        )
    ]

    calendar_cap.observations_to_return = [
        Observation(
            source="calendar",
            type="meeting_soon",
            timestamp=datetime.now(timezone.utc),
            priority=8,
            data={"event_id": "456"},
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
