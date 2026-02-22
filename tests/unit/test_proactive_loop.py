"""
Unit tests for ProactiveExecutionLoop.

Tests the core loop logic, timing, error handling, and integration with BDI components.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from empla.core.hooks import (
    HOOK_AFTER_BELIEF_UPDATE,
    HOOK_AFTER_INTENTION_EXECUTION,
    HOOK_AFTER_PERCEPTION,
    HOOK_BEFORE_BELIEF_UPDATE,
    HOOK_BEFORE_INTENTION_EXECUTION,
    HOOK_BEFORE_PERCEPTION,
    HOOK_CYCLE_END,
    HOOK_CYCLE_START,
    HookRegistry,
)
from empla.core.loop.execution import (
    ProactiveExecutionLoop,
)
from empla.core.loop.models import IntentionResult, LoopConfig, PerceptionResult
from empla.models.employee import Employee

# ============================================================================
# Mock Implementations of BDI Components
# ============================================================================


class MockBeliefChange:
    """Mock belief change for testing"""

    def __init__(
        self,
        subject: str = "test",
        predicate: str = "test",
        importance: float = 0.5,
        old_confidence: float = 0.5,
        new_confidence: float = 0.7,
    ):
        self.subject = subject
        self.predicate = predicate
        self.importance = importance
        self.old_confidence = old_confidence
        self.new_confidence = new_confidence


class MockBeliefSystem:
    """Mock BeliefSystem for testing"""

    def __init__(self):
        self.update_beliefs = AsyncMock(return_value=[])


class MockGoalSystem:
    """Mock GoalSystem for testing"""

    def __init__(self):
        self.get_active_goals = AsyncMock(return_value=[])
        self.update_goal_progress = AsyncMock()


class MockIntentionStack:
    """Mock IntentionStack for testing"""

    def __init__(self):
        self.get_next_intention = AsyncMock(return_value=None)
        self.dependencies_satisfied = AsyncMock(return_value=True)
        self.start_intention = AsyncMock()
        self.complete_intention = AsyncMock()
        self.fail_intention = AsyncMock()


class MockMemorySystem:
    """Mock MemorySystem for testing"""


class MockIntention:
    """Mock intention for testing"""

    def __init__(
        self,
        id: str | None = None,
        description: str = "Test intention",
        intention_type: str = "action",
        priority: int = 5,
    ):
        self.id = uuid4() if id is None else id
        self.description = description
        self.intention_type = intention_type
        self.priority = priority


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_employee():
    """Create mock employee for testing"""
    employee = Mock(spec=Employee)
    employee.id = uuid4()
    employee.name = "Test Employee"
    employee.status = "active"
    employee.role = "sales_ae"
    return employee


@pytest.fixture
def mock_beliefs():
    """Create mock belief system"""
    return MockBeliefSystem()


@pytest.fixture
def mock_goals():
    """Create mock goal system"""
    return MockGoalSystem()


@pytest.fixture
def mock_intentions():
    """Create mock intention stack"""
    return MockIntentionStack()


@pytest.fixture
def mock_memory():
    """Create mock memory system"""
    return MockMemorySystem()


@pytest.fixture
def loop_config():
    """Create test loop configuration"""
    return LoopConfig(
        cycle_interval_seconds=1,  # Fast cycles for testing
        error_backoff_seconds=1,
        strategic_planning_interval_hours=1,
    )


@pytest.fixture
def proactive_loop(
    mock_employee, mock_beliefs, mock_goals, mock_intentions, mock_memory, loop_config
):
    """Create proactive execution loop for testing"""
    return ProactiveExecutionLoop(
        employee=mock_employee,
        beliefs=mock_beliefs,
        goals=mock_goals,
        intentions=mock_intentions,
        memory=mock_memory,
        config=loop_config,
    )


# ============================================================================
# Test: Initialization
# ============================================================================


def test_loop_initialization(proactive_loop, mock_employee, loop_config):
    """Test loop initializes correctly"""
    assert proactive_loop.employee == mock_employee
    assert proactive_loop.config == loop_config
    assert proactive_loop.cycle_interval == loop_config.cycle_interval_seconds
    assert not proactive_loop.is_running
    assert proactive_loop.cycle_count == 0
    assert proactive_loop.last_strategic_planning is None


# ============================================================================
# Test: Perception
# ============================================================================


@pytest.mark.asyncio
async def test_perceive_environment_returns_result(proactive_loop):
    """Test perception returns PerceptionResult"""
    result = await proactive_loop.perceive_environment()

    assert isinstance(result, PerceptionResult)
    assert isinstance(result.observations, list)
    assert result.perception_duration_ms > 0


@pytest.mark.asyncio
async def test_perceive_environment_empty_observations(proactive_loop):
    """Test perception returns empty observations (placeholder implementation)"""
    result = await proactive_loop.perceive_environment()

    # Placeholder implementation returns empty observations
    assert len(result.observations) == 0
    assert result.opportunities_detected == 0
    assert result.problems_detected == 0


# ============================================================================
# Test: Strategic Planning Decision Logic
# ============================================================================


def test_should_run_strategic_planning_never_run_before(proactive_loop):
    """Test strategic planning runs if never run before"""
    proactive_loop.last_strategic_planning = None

    assert proactive_loop.should_run_strategic_planning([])


def test_should_run_strategic_planning_scheduled_interval(proactive_loop):
    """Test strategic planning runs on scheduled interval"""
    # Set last planning to 2 hours ago (interval is 1 hour)
    proactive_loop.last_strategic_planning = datetime.now(UTC) - timedelta(hours=2)

    assert proactive_loop.should_run_strategic_planning([])


def test_should_run_strategic_planning_significant_belief_change(proactive_loop):
    """Test strategic planning runs on significant belief change"""
    proactive_loop.last_strategic_planning = datetime.now(UTC)  # Just ran

    # High-importance belief changed significantly
    belief_change = MockBeliefChange(
        importance=0.9,  # High importance
        old_confidence=0.3,
        new_confidence=0.8,  # Significant change (0.5 diff)
    )

    assert proactive_loop.should_run_strategic_planning([belief_change])


def test_should_run_strategic_planning_goal_belief_change(proactive_loop):
    """Test strategic planning runs when goal-related belief changes"""
    proactive_loop.last_strategic_planning = datetime.now(UTC)  # Just ran

    # Goal achievability belief changed
    belief_change = MockBeliefChange(
        predicate="achievable",  # Goal-related predicate
        importance=0.5,
        old_confidence=0.8,
        new_confidence=0.7,
    )

    assert proactive_loop.should_run_strategic_planning([belief_change])


def test_should_not_run_strategic_planning_minor_change(proactive_loop):
    """Test strategic planning does NOT run on minor changes"""
    proactive_loop.last_strategic_planning = datetime.now(UTC)  # Just ran

    # Low-importance belief with small change
    belief_change = MockBeliefChange(
        importance=0.3,  # Low importance
        old_confidence=0.5,
        new_confidence=0.6,  # Small change
    )

    assert not proactive_loop.should_run_strategic_planning([belief_change])


# ============================================================================
# Test: Deep Reflection Decision Logic
# ============================================================================


def test_should_run_deep_reflection_never_run_before(proactive_loop):
    """Test deep reflection runs if never run before"""
    proactive_loop.last_deep_reflection = None

    assert proactive_loop.should_run_deep_reflection()


def test_should_run_deep_reflection_scheduled_interval(proactive_loop):
    """Test deep reflection runs on scheduled interval"""
    # Set last reflection to 25 hours ago (interval is 24 hours)
    proactive_loop.last_deep_reflection = datetime.now(UTC) - timedelta(hours=25)

    assert proactive_loop.should_run_deep_reflection()


def test_should_not_run_deep_reflection_too_soon(proactive_loop):
    """Test deep reflection does NOT run if too soon"""
    # Set last reflection to 1 hour ago (interval is 24 hours)
    proactive_loop.last_deep_reflection = datetime.now(UTC) - timedelta(hours=1)

    assert not proactive_loop.should_run_deep_reflection()


# ============================================================================
# Test: Intention Execution
# ============================================================================


@pytest.mark.asyncio
async def test_execute_intentions_no_work(proactive_loop, mock_intentions):
    """Test execute_intentions returns None when no work to do"""
    mock_intentions.get_next_intention.return_value = None

    result = await proactive_loop.execute_intentions()

    assert result is None
    mock_intentions.get_next_intention.assert_called_once()


@pytest.mark.asyncio
async def test_execute_intentions_dependencies_not_satisfied(proactive_loop, mock_intentions):
    """Test execute_intentions returns None when dependencies not satisfied"""
    mock_intention = MockIntention()
    mock_intentions.get_next_intention.return_value = mock_intention
    mock_intentions.dependencies_satisfied.return_value = False

    result = await proactive_loop.execute_intentions()

    assert result is None
    mock_intentions.dependencies_satisfied.assert_called_once_with(mock_intention)


@pytest.mark.asyncio
async def test_execute_intentions_successful(proactive_loop, mock_intentions):
    """Test execute_intentions succeeds and returns result"""
    mock_intention = MockIntention()
    mock_intentions.get_next_intention.return_value = mock_intention
    mock_intentions.dependencies_satisfied.return_value = True

    result = await proactive_loop.execute_intentions()

    assert result is not None
    assert isinstance(result, IntentionResult)
    assert result.success is True
    assert result.intention_id == mock_intention.id

    mock_intentions.start_intention.assert_called_once_with(mock_intention)
    mock_intentions.complete_intention.assert_called_once()


# ============================================================================
# Test: Reflection
# ============================================================================


@pytest.mark.asyncio
async def test_reflection_cycle_called(proactive_loop):
    """Test reflection cycle is called with result"""
    result = IntentionResult(
        intention_id=uuid4(),
        success=True,
        outcome={"test": True},
    )

    # Should not raise - just logs for now
    await proactive_loop.reflection_cycle(result)


# ============================================================================
# Test: Loop Start/Stop
# ============================================================================


@pytest.mark.asyncio
async def test_loop_start_stop(proactive_loop, mock_employee):
    """Test loop can be started and stopped"""
    # Start loop in background
    loop_task = asyncio.create_task(proactive_loop.start())

    # Wait for loop to start
    await asyncio.sleep(0.1)

    assert proactive_loop.is_running

    # Stop loop
    await proactive_loop.stop()

    # Wait for loop to stop
    await loop_task

    assert not proactive_loop.is_running


@pytest.mark.asyncio
async def test_loop_cannot_start_twice(proactive_loop):
    """Test loop cannot be started twice"""
    # Start loop
    loop_task = asyncio.create_task(proactive_loop.start())

    await asyncio.sleep(0.1)

    # Try to start again - should be ignored
    await proactive_loop.start()

    # Stop and cleanup
    await proactive_loop.stop()
    await loop_task


@pytest.mark.asyncio
async def test_loop_stops_when_employee_inactive(proactive_loop, mock_employee):
    """Test loop stops when employee becomes inactive"""
    # Start loop
    loop_task = asyncio.create_task(proactive_loop.start())

    await asyncio.sleep(0.1)

    # Deactivate employee
    mock_employee.status = "terminated"

    # Wait for loop to detect and stop (needs time for next cycle)
    await asyncio.sleep(1.5)

    # Stop loop explicitly (in case it's still running)
    await proactive_loop.stop()

    try:
        await asyncio.wait_for(loop_task, timeout=1.0)
    except TimeoutError:
        pass

    # Loop should have stopped
    assert not proactive_loop.is_running


@pytest.mark.asyncio
async def test_loop_can_restart_after_natural_shutdown(proactive_loop, mock_employee, mock_beliefs):
    """Test loop can be restarted after natural shutdown (employee deactivated)"""
    mock_beliefs.update_beliefs.return_value = []

    # Start loop
    loop_task = asyncio.create_task(proactive_loop.start())
    await asyncio.sleep(0.1)
    assert proactive_loop.is_running

    # Deactivate employee (natural shutdown)
    mock_employee.status = "terminated"
    await asyncio.sleep(1.5)  # Wait for loop to detect and stop

    # Wait for task to complete
    try:
        await asyncio.wait_for(loop_task, timeout=1.0)
    except TimeoutError:
        pass

    # Verify loop stopped and flag cleared
    assert not proactive_loop.is_running

    # Reactivate employee
    mock_employee.status = "active"

    # Restart loop - should work since is_running was cleared
    loop_task2 = asyncio.create_task(proactive_loop.start())
    await asyncio.sleep(0.1)

    # Verify loop restarted successfully
    assert proactive_loop.is_running

    # Clean up
    await proactive_loop.stop()
    await loop_task2


# ============================================================================
# Test: Loop Cycle Execution
# ============================================================================


@pytest.mark.asyncio
async def test_loop_executes_cycle(proactive_loop, mock_beliefs, mock_goals):
    """Test loop executes a complete cycle"""
    # Configure mocks
    mock_beliefs.update_beliefs.return_value = []
    mock_goals.get_active_goals.return_value = []

    # Start loop
    loop_task = asyncio.create_task(proactive_loop.start())

    # Let it run for 1.5 seconds (should complete at least 1 cycle)
    await asyncio.sleep(1.5)

    # Stop loop
    await proactive_loop.stop()
    await loop_task

    # Verify cycle executed
    assert proactive_loop.cycle_count >= 1

    # Verify BDI components were called
    mock_beliefs.update_beliefs.assert_called()
    mock_goals.get_active_goals.assert_called()


@pytest.mark.asyncio
async def test_loop_handles_errors_gracefully(proactive_loop, mock_beliefs):
    """Test loop continues after errors"""
    # Make beliefs.update_beliefs raise error on first call
    error_raised = False

    async def raise_once(*args):
        nonlocal error_raised
        if not error_raised:
            error_raised = True
            raise ValueError("Test error")
        return []

    mock_beliefs.update_beliefs = AsyncMock(side_effect=raise_once)

    # Start loop
    loop_task = asyncio.create_task(proactive_loop.start())

    # Let it run for 2.5 seconds (should handle error and continue)
    await asyncio.sleep(2.5)

    # Stop loop
    await proactive_loop.stop()
    await loop_task

    # Loop should have continued after error
    # First cycle errors, waits 1s, then continues
    assert proactive_loop.cycle_count >= 1


# ============================================================================
# Test: Strategic Planning Integration
# ============================================================================


@pytest.mark.asyncio
async def test_strategic_planning_called_on_first_cycle(proactive_loop, mock_beliefs):
    """Test strategic planning is called on first cycle"""
    mock_beliefs.update_beliefs.return_value = []

    # Verify it hasn't run yet
    assert proactive_loop.last_strategic_planning is None

    # Start loop
    loop_task = asyncio.create_task(proactive_loop.start())

    # Let it run for 1.5 seconds (should complete at least 1 cycle)
    await asyncio.sleep(1.5)

    # Stop loop
    await proactive_loop.stop()
    await loop_task

    # Strategic planning should have been called (never run before)
    # Note: It runs in first cycle because last_strategic_planning is None
    assert proactive_loop.last_strategic_planning is not None


# ============================================================================
# Test: Configuration
# ============================================================================


def test_loop_uses_custom_config():
    """Test loop respects custom configuration"""
    custom_config = LoopConfig(
        cycle_interval_seconds=10,
        strategic_planning_interval_hours=48,
    )

    loop = ProactiveExecutionLoop(
        employee=Mock(),
        beliefs=MockBeliefSystem(),
        goals=MockGoalSystem(),
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        config=custom_config,
    )

    assert loop.cycle_interval == 10
    assert loop.config.strategic_planning_interval_hours == 48


def test_loop_uses_default_config():
    """Test loop uses default config if none provided"""
    loop = ProactiveExecutionLoop(
        employee=Mock(),
        beliefs=MockBeliefSystem(),
        goals=MockGoalSystem(),
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        config=None,  # No config
    )

    # Should use defaults
    assert loop.cycle_interval == 300  # Default 5 minutes
    assert loop.config.strategic_planning_interval_hours == 24  # Default daily


@pytest.mark.asyncio
async def test_loop_stops_promptly_without_sleep_delay(proactive_loop, mock_beliefs):
    """Test loop exits promptly when stop() is called, without waiting for sleep"""
    mock_beliefs.update_beliefs.return_value = []

    # Start loop
    loop_task = asyncio.create_task(proactive_loop.start())

    # Wait for at least one cycle to start
    await asyncio.sleep(0.1)

    # Call stop() - this should exit promptly without waiting for full cycle_interval
    start_stop_time = asyncio.get_event_loop().time()
    await proactive_loop.stop()

    # Wait for loop to actually stop
    await loop_task
    stop_duration = asyncio.get_event_loop().time() - start_stop_time

    # Verify loop stopped
    assert not proactive_loop.is_running

    # Verify it stopped quickly (< 0.5s) and didn't wait for full cycle_interval (1s)
    # This confirms the is_running check before sleep is working
    assert stop_duration < 0.5, f"Loop took {stop_duration}s to stop, should be < 0.5s"


@pytest.mark.asyncio
async def test_loop_stops_promptly_after_error(proactive_loop, mock_beliefs):
    """Test loop exits promptly when stop() is called during error backoff"""
    # Make beliefs.update_beliefs always raise errors
    mock_beliefs.update_beliefs = AsyncMock(side_effect=ValueError("Test error"))

    # Start loop
    loop_task = asyncio.create_task(proactive_loop.start())

    # Wait for error to occur
    await asyncio.sleep(0.2)

    # Call stop() during error backoff - should exit promptly
    start_stop_time = asyncio.get_event_loop().time()
    await proactive_loop.stop()

    # Wait for loop to actually stop
    await loop_task
    stop_duration = asyncio.get_event_loop().time() - start_stop_time

    # Verify loop stopped
    assert not proactive_loop.is_running

    # Verify it stopped quickly and didn't wait for full error_backoff_interval (1s)
    assert stop_duration < 0.5, f"Loop took {stop_duration}s to stop, should be < 0.5s"


# ============================================================================
# Test: Pause-via-DB
# ============================================================================


@pytest.mark.asyncio
async def test_loop_pauses_when_status_set_to_paused(mock_employee, mock_beliefs, mock_goals):
    """Test loop sleeps instead of exiting when employee.status is 'paused'."""
    mock_beliefs.update_beliefs.return_value = []
    mock_goals.get_active_goals.return_value = []

    cycle_ran = False

    async def set_paused_then_active(employee):
        """After one real cycle, pause, then resume."""
        nonlocal cycle_ran
        if not cycle_ran:
            # First call: let the cycle run normally (status is "active")
            return
        # After first cycle ran, set to paused briefly then back to active
        employee.status = "paused"

    loop = ProactiveExecutionLoop(
        employee=mock_employee,
        beliefs=mock_beliefs,
        goals=mock_goals,
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        config=LoopConfig(cycle_interval_seconds=1, error_backoff_seconds=1),
        status_checker=set_paused_then_active,
    )

    loop_task = asyncio.create_task(loop.start())

    # Let the first cycle run
    await asyncio.sleep(0.3)
    cycle_ran = True

    # Loop should still be running (paused, not exited)
    assert loop.is_running
    assert loop.cycle_count >= 1

    # Resume by setting active and stop
    mock_employee.status = "active"
    await asyncio.sleep(0.2)
    await loop.stop()
    await loop_task


@pytest.mark.asyncio
async def test_loop_exits_on_stopped_status(mock_employee, mock_beliefs, mock_goals):
    """Test loop exits when employee.status becomes 'stopped'."""
    mock_beliefs.update_beliefs.return_value = []
    mock_goals.get_active_goals.return_value = []

    loop = ProactiveExecutionLoop(
        employee=mock_employee,
        beliefs=mock_beliefs,
        goals=mock_goals,
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        config=LoopConfig(cycle_interval_seconds=1, error_backoff_seconds=1),
    )

    loop_task = asyncio.create_task(loop.start())
    await asyncio.sleep(0.2)

    # Set status to "stopped" — loop should exit
    mock_employee.status = "stopped"
    await asyncio.wait_for(loop_task, timeout=2.0)

    assert not loop.is_running


@pytest.mark.asyncio
async def test_status_checker_callback_is_called(mock_employee, mock_beliefs, mock_goals):
    """Test that the status_checker callback is invoked each cycle."""
    mock_beliefs.update_beliefs.return_value = []
    mock_goals.get_active_goals.return_value = []

    checker_calls = 0

    async def counting_checker(employee):
        nonlocal checker_calls
        checker_calls += 1

    loop = ProactiveExecutionLoop(
        employee=mock_employee,
        beliefs=mock_beliefs,
        goals=mock_goals,
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        config=LoopConfig(cycle_interval_seconds=1, error_backoff_seconds=1),
        status_checker=counting_checker,
    )

    loop_task = asyncio.create_task(loop.start())
    await asyncio.sleep(0.5)
    await loop.stop()
    await loop_task

    # Checker should have been called at least once per cycle
    assert checker_calls >= loop.cycle_count


@pytest.mark.asyncio
async def test_status_checker_failure_does_not_kill_loop(mock_employee, mock_beliefs, mock_goals):
    """Test that status_checker exceptions are caught and the loop continues."""
    mock_beliefs.update_beliefs.return_value = []
    mock_goals.get_active_goals.return_value = []

    call_count = 0

    async def failing_checker(employee):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("DB connection failed")

    loop = ProactiveExecutionLoop(
        employee=mock_employee,
        beliefs=mock_beliefs,
        goals=mock_goals,
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        config=LoopConfig(cycle_interval_seconds=1, error_backoff_seconds=1),
        status_checker=failing_checker,
    )

    loop_task = asyncio.create_task(loop.start())
    await asyncio.sleep(0.5)
    await loop.stop()
    await loop_task

    # Loop should have survived the failing checker and run cycles
    assert loop.cycle_count >= 1
    assert call_count >= 1


# ============================================================================
# Test: Lifecycle Hooks
# ============================================================================


@pytest.mark.asyncio
async def test_hooks_emitted_during_single_cycle(mock_employee, mock_beliefs, mock_goals):
    """Test hooks are emitted at each phase boundary during _run_cycle()."""
    mock_beliefs.update_beliefs.return_value = []
    mock_goals.get_active_goals.return_value = []

    hooks = HookRegistry()

    # Register a tracker for each expected hook
    expected_hooks = [
        HOOK_CYCLE_START,
        HOOK_BEFORE_PERCEPTION,
        HOOK_AFTER_PERCEPTION,
        HOOK_BEFORE_BELIEF_UPDATE,
        HOOK_AFTER_BELIEF_UPDATE,
        HOOK_BEFORE_INTENTION_EXECUTION,
        HOOK_AFTER_INTENTION_EXECUTION,
        HOOK_CYCLE_END,
    ]

    trackers: dict[str, AsyncMock] = {}
    for hook_name in expected_hooks:
        mock_handler = AsyncMock()
        trackers[hook_name] = mock_handler
        hooks.register(hook_name, mock_handler)

    loop = ProactiveExecutionLoop(
        employee=mock_employee,
        beliefs=mock_beliefs,
        goals=mock_goals,
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        config=LoopConfig(cycle_interval_seconds=1),
        hooks=hooks,
    )

    await loop._run_cycle()

    # All expected hooks should have been called
    for hook_name in expected_hooks:
        assert trackers[hook_name].called, f"Hook '{hook_name}' was not emitted"

    # cycle_start should have received employee_id and cycle_count
    call_kwargs = trackers[HOOK_CYCLE_START].call_args.kwargs
    assert call_kwargs["employee_id"] == mock_employee.id
    assert call_kwargs["cycle_count"] == 1

    # cycle_end should have received success=True
    call_kwargs = trackers[HOOK_CYCLE_END].call_args.kwargs
    assert call_kwargs["success"] is True
    assert "duration_seconds" in call_kwargs


@pytest.mark.asyncio
async def test_hooks_not_required(mock_employee, mock_beliefs, mock_goals):
    """Test loop works fine without hooks (None passed)."""
    mock_beliefs.update_beliefs.return_value = []
    mock_goals.get_active_goals.return_value = []

    loop = ProactiveExecutionLoop(
        employee=mock_employee,
        beliefs=mock_beliefs,
        goals=mock_goals,
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        config=LoopConfig(cycle_interval_seconds=1),
        hooks=None,  # Explicitly None
    )

    # Should run without errors
    result = await loop._run_cycle()
    assert loop.cycle_count == 1


@pytest.mark.asyncio
async def test_hook_failure_doesnt_crash_cycle(mock_employee, mock_beliefs, mock_goals):
    """Test a failing hook handler doesn't crash the BDI cycle."""
    mock_beliefs.update_beliefs.return_value = []
    mock_goals.get_active_goals.return_value = []

    hooks = HookRegistry()

    async def failing_handler(**kwargs: object) -> None:
        raise RuntimeError("hook explosion")

    hooks.register(HOOK_CYCLE_START, failing_handler)
    hooks.register(HOOK_BEFORE_PERCEPTION, failing_handler)

    loop = ProactiveExecutionLoop(
        employee=mock_employee,
        beliefs=mock_beliefs,
        goals=mock_goals,
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        config=LoopConfig(cycle_interval_seconds=1),
        hooks=hooks,
    )

    # Cycle should complete despite hook failures
    await loop._run_cycle()
    assert loop.cycle_count == 1


@pytest.mark.asyncio
async def test_hooks_emitted_during_continuous_loop(mock_employee, mock_beliefs, mock_goals):
    """Test hooks fire during run_continuous_loop()."""
    mock_beliefs.update_beliefs.return_value = []
    mock_goals.get_active_goals.return_value = []

    hooks = HookRegistry()
    cycle_start_count = 0
    cycle_end_count = 0

    async def count_cycle_start(**kwargs: object) -> None:
        nonlocal cycle_start_count
        cycle_start_count += 1

    async def count_cycle_end(**kwargs: object) -> None:
        nonlocal cycle_end_count
        cycle_end_count += 1

    hooks.register(HOOK_CYCLE_START, count_cycle_start)
    hooks.register(HOOK_CYCLE_END, count_cycle_end)

    loop = ProactiveExecutionLoop(
        employee=mock_employee,
        beliefs=mock_beliefs,
        goals=mock_goals,
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        config=LoopConfig(cycle_interval_seconds=1),
        hooks=hooks,
    )

    loop_task = asyncio.create_task(loop.start())
    await asyncio.sleep(1.5)
    await loop.stop()
    await loop_task

    # At least one cycle should have fired hooks
    assert cycle_start_count >= 1
    assert cycle_end_count >= 1
    assert cycle_start_count == cycle_end_count


@pytest.mark.asyncio
async def test_cycle_end_hook_emitted_with_success_false_on_error(
    mock_employee, mock_beliefs, mock_goals
):
    """Test HOOK_CYCLE_END fires with success=False when a cycle errors."""
    mock_beliefs.update_beliefs = AsyncMock(side_effect=RuntimeError("db down"))
    mock_goals.get_active_goals.return_value = []

    hooks = HookRegistry()
    cycle_end_kwargs_list: list[dict[str, object]] = []

    async def capture_cycle_end(**kwargs: object) -> None:
        cycle_end_kwargs_list.append(kwargs)

    hooks.register(HOOK_CYCLE_END, capture_cycle_end)

    loop = ProactiveExecutionLoop(
        employee=mock_employee,
        beliefs=mock_beliefs,
        goals=mock_goals,
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        config=LoopConfig(cycle_interval_seconds=1, error_backoff_seconds=1),
        hooks=hooks,
    )

    loop_task = asyncio.create_task(loop.start())
    await asyncio.sleep(0.5)
    await loop.stop()
    await loop_task

    assert len(cycle_end_kwargs_list) >= 1
    assert cycle_end_kwargs_list[0]["success"] is False
    assert "duration_seconds" in cycle_end_kwargs_list[0]
    assert cycle_end_kwargs_list[0]["employee_id"] == mock_employee.id


@pytest.mark.asyncio
async def test_cycle_end_hook_success_false_in_run_cycle(mock_employee, mock_beliefs, mock_goals):
    """Test _run_cycle() emits HOOK_CYCLE_END with success=False on error."""
    mock_beliefs.update_beliefs = AsyncMock(side_effect=RuntimeError("db down"))
    mock_goals.get_active_goals.return_value = []

    hooks = HookRegistry()
    cycle_end_handler = AsyncMock()
    hooks.register(HOOK_CYCLE_END, cycle_end_handler)

    loop = ProactiveExecutionLoop(
        employee=mock_employee,
        beliefs=mock_beliefs,
        goals=mock_goals,
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        config=LoopConfig(cycle_interval_seconds=1),
        hooks=hooks,
    )

    with pytest.raises(RuntimeError, match="db down"):
        await loop._run_cycle()

    # HOOK_CYCLE_END should have been emitted with success=False before re-raise
    cycle_end_handler.assert_called_once()
    assert cycle_end_handler.call_args.kwargs["success"] is False


@pytest.mark.asyncio
async def test_after_reflection_hook_emitted_when_intention_executed(
    mock_employee, mock_beliefs, mock_goals
):
    """Test HOOK_AFTER_REFLECTION fires when an intention produces a result."""
    mock_beliefs.update_beliefs.return_value = []
    mock_goals.get_active_goals.return_value = []

    intentions = MockIntentionStack()
    mock_intention = MockIntention()
    intentions.get_next_intention.return_value = mock_intention
    intentions.dependencies_satisfied.return_value = True

    hooks = HookRegistry()
    from empla.core.hooks import HOOK_AFTER_REFLECTION

    reflection_handler = AsyncMock()
    hooks.register(HOOK_AFTER_REFLECTION, reflection_handler)

    loop = ProactiveExecutionLoop(
        employee=mock_employee,
        beliefs=mock_beliefs,
        goals=mock_goals,
        intentions=intentions,
        memory=MockMemorySystem(),
        config=LoopConfig(cycle_interval_seconds=1),
        hooks=hooks,
    )

    await loop._run_cycle()

    reflection_handler.assert_called_once()
    call_kwargs = reflection_handler.call_args.kwargs
    assert call_kwargs["employee_id"] == mock_employee.id
    assert "result" in call_kwargs


@pytest.mark.asyncio
async def test_hooks_fire_in_correct_order(mock_employee, mock_beliefs, mock_goals):
    """Test hooks fire in the correct BDI phase order."""
    mock_beliefs.update_beliefs.return_value = []
    mock_goals.get_active_goals.return_value = []

    hooks = HookRegistry()
    order: list[str] = []

    for hook_name in [
        HOOK_CYCLE_START,
        HOOK_BEFORE_PERCEPTION,
        HOOK_AFTER_PERCEPTION,
        HOOK_BEFORE_BELIEF_UPDATE,
        HOOK_AFTER_BELIEF_UPDATE,
        HOOK_BEFORE_INTENTION_EXECUTION,
        HOOK_AFTER_INTENTION_EXECUTION,
        HOOK_CYCLE_END,
    ]:

        async def tracker(n: str = hook_name, **kwargs: object) -> None:
            order.append(n)

        hooks.register(hook_name, tracker)

    loop = ProactiveExecutionLoop(
        employee=mock_employee,
        beliefs=mock_beliefs,
        goals=mock_goals,
        intentions=MockIntentionStack(),
        memory=MockMemorySystem(),
        config=LoopConfig(cycle_interval_seconds=1),
        hooks=hooks,
    )

    await loop._run_cycle()

    assert order == [
        "cycle_start",
        "before_perception",
        "after_perception",
        "before_belief_update",
        "after_belief_update",
        "before_intention_execution",
        "after_intention_execution",
        "cycle_end",
    ]
