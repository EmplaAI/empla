"""
Unit tests for CapabilityRegistry.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from empla.capabilities.base import (
    CAPABILITY_BROWSER,
    CAPABILITY_CALENDAR,
    CAPABILITY_EMAIL,
    Action,
    ActionResult,
    BaseCapability,
    CapabilityConfig,
    Observation,
)
from empla.capabilities.registry import CapabilityRegistry


class MockEmailCapability(BaseCapability):
    """Mock email capability for testing"""

    @property
    def capability_type(self) -> str:
        """
        Identify this capability's type as Email.

        Returns:
            CAPABILITY_EMAIL — the Email capability type.
        """
        return CAPABILITY_EMAIL

    async def initialize(self) -> None:
        """
        Mark the capability as initialized.

        Sets the internal `_initialized` flag to True so the capability is considered ready for use.
        """
        self._initialized = True

    async def perceive(self) -> list[Observation]:
        """
        Produce a list containing a single Observation representing a newly received email.

        Returns:
            list[Observation]: A list with one Observation whose source is "email",
            observation_type is "new_email", timestamp is the current UTC time,
            priority is 7, and content contains {"email_id": "123"}.
        """
        return [
            Observation(
                employee_id=self.employee_id,
                tenant_id=self.tenant_id,
                observation_type="new_email",
                source="email",
                content={"email_id": "123"},
                timestamp=datetime.now(UTC),
                priority=7,
            )
        ]

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        """
        Execute an action supported by this capability.

        This implements the capability-specific execution logic.
        The base class execute_action() handles retry logic and error handling.

        Parameters:
            action (Action): The action to perform; its `operation` field determines the behavior.

        Returns:
            ActionResult: An object indicating success and containing any result output or an error message. For `operation == "send_email"`, `success` is `true` and `output` contains `{"sent": True}`; otherwise `success` is `false` and `error` is `"Unknown operation"`.
        """
        if action.operation == "send_email":
            return ActionResult(success=True, output={"sent": True})
        return ActionResult(success=False, error="Unknown operation")


class MockCalendarCapability(BaseCapability):
    """Mock calendar capability for testing"""

    @property
    def capability_type(self) -> str:
        """
        Identify the capability type provided by this capability.

        Returns:
            str: CAPABILITY_CALENDAR representing a calendar capability.
        """
        return CAPABILITY_CALENDAR

    async def initialize(self) -> None:
        """
        Mark the capability as initialized.

        Sets the internal `_initialized` flag to True so the capability is considered ready for use.
        """
        self._initialized = True

    async def perceive(self) -> list[Observation]:
        """
        Return observations representing imminent calendar events.

        Returns:
            List[Observation]: A list containing a single Observation with source "calendar",
            observation_type "meeting_soon", the current UTC timestamp, priority 8,
            and content {"event_id": "456"}.
        """
        return [
            Observation(
                employee_id=self.employee_id,
                tenant_id=self.tenant_id,
                observation_type="meeting_soon",
                source="calendar",
                content={"event_id": "456"},
                timestamp=datetime.now(UTC),
                priority=8,
            )
        ]

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        """
        Execute the requested action for the calendar capability.

        This implements the capability-specific execution logic.
        The base class execute_action() handles retry logic and error handling.

        Handles the "schedule_meeting" operation by marking the action as successful and returning output indicating the meeting was scheduled; any other operation returns a failure with an "Unknown operation" error.

        Parameters:
            action (Action): The action to execute, including its operation name and parameters.

        Returns:
            ActionResult: For operation "schedule_meeting", `success` is True and `output` is {"scheduled": True}; otherwise `success` is False and `error` is "Unknown operation".
        """
        if action.operation == "schedule_meeting":
            return ActionResult(success=True, output={"scheduled": True})
        return ActionResult(success=False, error="Unknown operation")


class FailingCapability(BaseCapability):
    """Capability that fails during initialization"""

    @property
    def capability_type(self) -> str:
        """
        Identify this capability as a browser capability.

        Returns:
            str: CAPABILITY_BROWSER.
        """
        return CAPABILITY_BROWSER

    async def initialize(self) -> None:
        """
        Attempt to initialize the capability.

        This implementation always fails.

        Raises:
            Exception: Always raised with the message "Initialization failed".
        """
        raise Exception("Initialization failed")

    async def perceive(self) -> list[Observation]:
        """
        Indicates the capability perceives no observations.

        Returns:
            List[Observation]: An empty list of Observation objects.
        """
        return []

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        """
        Return an unsuccessful ActionResult indicating the capability is not initialized.

        This implements the capability-specific execution logic.
        The base class execute_action() handles retry logic and error handling.

        Parameters:
            action (Action): The action attempted to execute; ignored because the capability is not initialized.

        Returns:
            ActionResult: An unsuccessful result with the error message "Not initialized".
        """
        return ActionResult(success=False, error="Not initialized")


# Test CapabilityRegistry


def test_registry_initialization():
    """Test CapabilityRegistry initialization"""
    registry = CapabilityRegistry()

    assert len(registry._capabilities) == 0
    assert len(registry._instances) == 0


def test_registry_register_capability():
    """Test registering a capability"""
    registry = CapabilityRegistry()

    registry.register(CAPABILITY_EMAIL, MockEmailCapability)

    assert CAPABILITY_EMAIL in registry._capabilities
    assert registry._capabilities[CAPABILITY_EMAIL] == MockEmailCapability


def test_registry_register_invalid_capability():
    """Test registering invalid capability raises error"""
    registry = CapabilityRegistry()

    with pytest.raises(ValueError, match="must extend BaseCapability"):
        registry.register(CAPABILITY_EMAIL, str)  # Not a capability class


@pytest.mark.asyncio
async def test_registry_enable_capability():
    """Test enabling a capability for an employee"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, MockEmailCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    # Enable capability
    capability = await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )

    assert capability is not None
    assert capability.capability_type == CAPABILITY_EMAIL
    assert capability._initialized is True
    assert employee_id in registry._instances
    assert CAPABILITY_EMAIL in registry._instances[employee_id]


@pytest.mark.asyncio
async def test_registry_enable_unregistered_capability():
    """Test enabling unregistered capability raises error"""
    registry = CapabilityRegistry()

    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    with pytest.raises(ValueError, match="not registered"):
        await registry.enable_for_employee(
            employee_id=employee_id,
            tenant_id=tenant_id,
            capability_type=CAPABILITY_EMAIL,
            config=config,
        )


@pytest.mark.asyncio
async def test_registry_enable_capability_twice():
    """Test enabling same capability twice returns existing instance"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, MockEmailCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    # Enable first time
    cap1 = await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )

    # Enable second time
    cap2 = await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )

    # Should return same instance
    assert cap1 is cap2


@pytest.mark.asyncio
async def test_registry_enable_failing_capability():
    """Test enabling capability that fails during initialization"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_BROWSER, FailingCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    with pytest.raises(Exception, match="Initialization failed"):
        await registry.enable_for_employee(
            employee_id=employee_id,
            tenant_id=tenant_id,
            capability_type=CAPABILITY_BROWSER,
            config=config,
        )


@pytest.mark.asyncio
async def test_registry_disable_capability():
    """Test disabling a capability"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, MockEmailCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    # Enable
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )

    assert CAPABILITY_EMAIL in registry._instances[employee_id]

    # Disable
    await registry.disable_for_employee(employee_id=employee_id, capability_type=CAPABILITY_EMAIL)

    assert CAPABILITY_EMAIL not in registry._instances[employee_id]


@pytest.mark.asyncio
async def test_registry_disable_nonexistent_capability():
    """Test disabling capability that doesn't exist (should not raise error)"""
    registry = CapabilityRegistry()

    employee_id = uuid4()

    # Should not raise error
    await registry.disable_for_employee(employee_id=employee_id, capability_type=CAPABILITY_EMAIL)


@pytest.mark.asyncio
async def test_registry_disable_all_for_employee():
    """Test disabling all capabilities for an employee"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, MockEmailCapability)
    registry.register(CAPABILITY_CALENDAR, MockCalendarCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    # Enable both capabilities
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_CALENDAR,
        config=config,
    )

    assert len(registry._instances[employee_id]) == 2

    # Disable all
    await registry.disable_all_for_employee(employee_id=employee_id)

    assert employee_id not in registry._instances


def test_registry_get_capability():
    """Test getting a capability instance"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, MockEmailCapability)

    employee_id = uuid4()

    # Not enabled yet
    cap = registry.get_capability(employee_id, CAPABILITY_EMAIL)
    assert cap is None


@pytest.mark.asyncio
async def test_registry_get_capability_enabled():
    """
    Verify that an enabled capability can be retrieved for an employee.

    Enables the EMAIL capability for a generated tenant/employee and asserts that
    retrieving that capability returns a non-None instance with the expected type.
    """
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, MockEmailCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    # Enable
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )

    # Get
    cap = registry.get_capability(employee_id, CAPABILITY_EMAIL)
    assert cap is not None
    assert cap.capability_type == CAPABILITY_EMAIL


@pytest.mark.asyncio
async def test_registry_get_enabled_capabilities():
    """Test getting list of enabled capabilities"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, MockEmailCapability)
    registry.register(CAPABILITY_CALENDAR, MockCalendarCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    # No capabilities enabled
    enabled = registry.get_enabled_capabilities(employee_id)
    assert len(enabled) == 0

    # Enable email
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )

    enabled = registry.get_enabled_capabilities(employee_id)
    assert len(enabled) == 1
    assert CAPABILITY_EMAIL in enabled

    # Enable calendar
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_CALENDAR,
        config=config,
    )

    enabled = registry.get_enabled_capabilities(employee_id)
    assert len(enabled) == 2
    assert CAPABILITY_EMAIL in enabled
    assert CAPABILITY_CALENDAR in enabled


@pytest.mark.asyncio
async def test_registry_perceive_all():
    """Test perceiving from all capabilities"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, MockEmailCapability)
    registry.register(CAPABILITY_CALENDAR, MockCalendarCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    # Enable both
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_CALENDAR,
        config=config,
    )

    # Perceive
    observations = await registry.perceive_all(employee_id)

    assert len(observations) == 2
    sources = [obs.source for obs in observations]
    assert "email" in sources
    assert "calendar" in sources


@pytest.mark.asyncio
async def test_registry_perceive_all_no_capabilities():
    """Test perceiving when no capabilities enabled"""
    registry = CapabilityRegistry()
    employee_id = uuid4()

    observations = await registry.perceive_all(employee_id)

    assert len(observations) == 0


@pytest.mark.asyncio
async def test_registry_execute_action():
    """Test executing action via registry"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, MockEmailCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    # Enable
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )

    # Execute action
    action = Action(
        capability="email",
        operation="send_email",
        parameters={"to": ["test@example.com"]},
    )

    result = await registry.execute_action(employee_id, action)

    assert result.success is True
    assert result.output["sent"] is True


@pytest.mark.asyncio
async def test_registry_execute_action_unknown_capability():
    """Test executing action with unregistered capability type"""
    registry = CapabilityRegistry()
    employee_id = uuid4()

    action = Action(capability="nonexistent", operation="do_thing", parameters={})

    result = await registry.execute_action(employee_id, action)

    assert result.success is False
    assert "Unknown capability type" in result.error
    assert "nonexistent" in result.error


@pytest.mark.asyncio
async def test_registry_execute_action_capability_not_enabled():
    """Test executing action when capability is registered but not enabled for employee"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, MockEmailCapability)
    employee_id = uuid4()

    action = Action(capability="email", operation="send_email", parameters={})

    result = await registry.execute_action(employee_id, action)

    assert result.success is False
    assert "not enabled" in result.error
    assert "registered" in result.error.lower()


@pytest.mark.asyncio
async def test_registry_health_check():
    """Test health check for all capabilities"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, MockEmailCapability)
    registry.register(CAPABILITY_CALENDAR, MockCalendarCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    # Enable both
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_CALENDAR,
        config=config,
    )

    # Health check
    health = registry.health_check(employee_id)

    assert len(health) == 2
    assert health[CAPABILITY_EMAIL] is True
    assert health[CAPABILITY_CALENDAR] is True


def test_registry_repr():
    """Test registry string representation"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, MockEmailCapability)

    repr_str = repr(registry)
    assert "CapabilityRegistry" in repr_str
    assert "registered=1" in repr_str
    assert "employees_with_capabilities=0" in repr_str


# Tests for get_registered_types


def test_get_registered_types_empty():
    """Test get_registered_types on empty registry"""
    registry = CapabilityRegistry()

    assert registry.get_registered_types() == []


def test_get_registered_types_after_registration():
    """Test get_registered_types returns registered types"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, MockEmailCapability)
    registry.register(CAPABILITY_CALENDAR, MockCalendarCapability)

    types = registry.get_registered_types()

    assert len(types) == 2
    assert CAPABILITY_EMAIL in types
    assert CAPABILITY_CALENDAR in types


@pytest.mark.asyncio
async def test_get_registered_types_excludes_enabled_only():
    """get_registered_types reflects registered types, not enabled instances"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, MockEmailCapability)
    registry.register(CAPABILITY_CALENDAR, MockCalendarCapability)

    # Enable only email
    employee_id = uuid4()
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=uuid4(),
        capability_type=CAPABILITY_EMAIL,
        config=CapabilityConfig(),
    )

    # get_registered_types still returns both
    types = registry.get_registered_types()
    assert len(types) == 2
    assert CAPABILITY_EMAIL in types
    assert CAPABILITY_CALENDAR in types


# Tests for custom string capability routing


@pytest.mark.asyncio
async def test_registry_custom_string_capability():
    """Test that arbitrary strings work as capability types"""
    registry = CapabilityRegistry()
    registry.register("my_custom_tool", MockEmailCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type="my_custom_tool",
        config=config,
    )

    action = Action(
        capability="my_custom_tool",
        operation="send_email",
        parameters={"to": ["test@example.com"]},
    )

    result = await registry.execute_action(employee_id, action)
    assert result.success is True


# Tests for register() input validation


def test_register_rejects_empty_string():
    """Test that register() rejects empty capability type"""
    registry = CapabilityRegistry()

    with pytest.raises(ValueError, match="non-empty string"):
        registry.register("", MockEmailCapability)


def test_register_rejects_whitespace_only():
    """Test that register() rejects whitespace-only capability type"""
    registry = CapabilityRegistry()

    with pytest.raises(ValueError, match="non-empty string"):
        registry.register("   ", MockEmailCapability)


def test_register_rejects_uppercase():
    """Test that register() rejects non-lowercase capability type"""
    registry = CapabilityRegistry()

    with pytest.raises(ValueError, match="lowercase"):
        registry.register("Email", MockEmailCapability)


def test_register_rejects_padded_whitespace():
    """Test that register() rejects capability type with surrounding whitespace"""
    registry = CapabilityRegistry()

    with pytest.raises(ValueError, match="lowercase"):
        registry.register(" email ", MockEmailCapability)


# Tests for execute_action exception handling


class ExplodingCapability(BaseCapability):
    """Capability whose execute raises an exception"""

    @property
    def capability_type(self) -> str:
        return CAPABILITY_EMAIL

    async def initialize(self) -> None:
        self._initialized = True

    async def perceive(self) -> list[Observation]:
        return []

    async def _execute_action_impl(self, _action: Action) -> ActionResult:
        raise RuntimeError("connection lost")


@pytest.mark.asyncio
async def test_registry_execute_action_catches_exception():
    """Test that execute_action catches capability exceptions and returns failure"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, ExplodingCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = CapabilityConfig()

    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )

    action = Action(capability="email", operation="send_email", parameters={})

    result = await registry.execute_action(employee_id, action)

    assert result.success is False
    assert "RuntimeError" in result.error
    assert "connection lost" in result.error
