"""
Unit tests for empla.core.hooks - BDI Lifecycle Hook Registry.

Tests the HookRegistry class: registration, emission, error isolation,
unregistration, clearing, and kwargs passthrough.
"""

import logging
from unittest.mock import AsyncMock

import pytest

from empla.core.hooks import (
    HOOK_CYCLE_END,
    HOOK_CYCLE_START,
    HookRegistry,
)

# ============================================================================
# Test: Registration and Emission
# ============================================================================


@pytest.mark.asyncio
async def test_register_and_emit():
    """Test basic registration and emission."""
    hooks = HookRegistry()
    handler = AsyncMock()

    hooks.register("test_event", handler)
    await hooks.emit("test_event", key="value")

    handler.assert_called_once_with(key="value")


@pytest.mark.asyncio
async def test_emit_no_handlers():
    """Test emit is a no-op when no handlers are registered."""
    hooks = HookRegistry()
    # Should not raise
    await hooks.emit("nonexistent_event", key="value")


@pytest.mark.asyncio
async def test_multiple_handlers_same_event():
    """Test all handlers are called in registration order."""
    hooks = HookRegistry()
    call_order: list[int] = []

    async def handler_1(**kwargs: object) -> None:
        call_order.append(1)

    async def handler_2(**kwargs: object) -> None:
        call_order.append(2)

    async def handler_3(**kwargs: object) -> None:
        call_order.append(3)

    hooks.register("event", handler_1)
    hooks.register("event", handler_2)
    hooks.register("event", handler_3)

    await hooks.emit("event")

    assert call_order == [1, 2, 3]


# ============================================================================
# Test: Error Isolation
# ============================================================================


@pytest.mark.asyncio
async def test_handler_error_isolated():
    """Test one handler failing doesn't affect others."""
    hooks = HookRegistry()
    call_order: list[int] = []

    async def handler_1(**kwargs: object) -> None:
        call_order.append(1)

    async def failing_handler(**kwargs: object) -> None:
        raise ValueError("boom")

    async def handler_3(**kwargs: object) -> None:
        call_order.append(3)

    hooks.register("event", handler_1)
    hooks.register("event", failing_handler)
    hooks.register("event", handler_3)

    await hooks.emit("event")

    # handler_1 and handler_3 should both have been called
    assert call_order == [1, 3]


@pytest.mark.asyncio
async def test_handler_error_logged(caplog: pytest.LogCaptureFixture):
    """Test errors produce log warnings."""
    hooks = HookRegistry()

    async def failing_handler(**kwargs: object) -> None:
        raise RuntimeError("test error")

    hooks.register("my_event", failing_handler)

    with caplog.at_level(logging.ERROR):
        await hooks.emit("my_event")

    assert any("my_event" in r.message for r in caplog.records)


# ============================================================================
# Test: Unregister
# ============================================================================


@pytest.mark.asyncio
async def test_unregister():
    """Test handler removal."""
    hooks = HookRegistry()
    handler = AsyncMock()

    hooks.register("event", handler)
    result = hooks.unregister("event", handler)

    assert result is True
    assert not hooks.has_handlers("event")

    # Emit should not call the handler
    await hooks.emit("event")
    handler.assert_not_called()


def test_unregister_nonexistent():
    """Test unregistering a handler that was never registered returns False."""
    hooks = HookRegistry()
    handler = AsyncMock()

    result = hooks.unregister("event", handler)
    assert result is False


def test_unregister_wrong_event():
    """Test unregistering from wrong event returns False."""
    hooks = HookRegistry()
    handler = AsyncMock()

    hooks.register("event_a", handler)
    result = hooks.unregister("event_b", handler)

    assert result is False
    assert hooks.has_handlers("event_a")


# ============================================================================
# Test: Clear
# ============================================================================


def test_clear_specific_event():
    """Test clearing handlers for a specific event."""
    hooks = HookRegistry()
    handler_a = AsyncMock()
    handler_b = AsyncMock()

    hooks.register("event_a", handler_a)
    hooks.register("event_b", handler_b)

    hooks.clear("event_a")

    assert not hooks.has_handlers("event_a")
    assert hooks.has_handlers("event_b")


def test_clear_all():
    """Test clearing all handlers."""
    hooks = HookRegistry()
    hooks.register("event_a", AsyncMock())
    hooks.register("event_b", AsyncMock())

    hooks.clear()

    assert not hooks.has_handlers("event_a")
    assert not hooks.has_handlers("event_b")


def test_clear_nonexistent_event():
    """Test clearing a nonexistent event is a no-op."""
    hooks = HookRegistry()
    # Should not raise
    hooks.clear("nonexistent")


# ============================================================================
# Test: has_handlers
# ============================================================================


def test_has_handlers_true():
    """Test has_handlers returns True when handlers exist."""
    hooks = HookRegistry()
    hooks.register("event", AsyncMock())

    assert hooks.has_handlers("event") is True


def test_has_handlers_false():
    """Test has_handlers returns False when no handlers exist."""
    hooks = HookRegistry()

    assert hooks.has_handlers("event") is False


def test_has_handlers_after_all_removed():
    """Test has_handlers returns False after all handlers removed."""
    hooks = HookRegistry()
    handler = AsyncMock()
    hooks.register("event", handler)
    hooks.unregister("event", handler)

    assert hooks.has_handlers("event") is False


# ============================================================================
# Test: kwargs passthrough
# ============================================================================


@pytest.mark.asyncio
async def test_kwargs_passed_through():
    """Test handlers receive correct kwargs."""
    hooks = HookRegistry()
    received: dict[str, object] = {}

    async def capture_handler(**kwargs: object) -> None:
        received.update(kwargs)

    hooks.register("event", capture_handler)
    await hooks.emit("event", employee_id="emp-1", cycle_count=42, extra="data")

    assert received == {"employee_id": "emp-1", "cycle_count": 42, "extra": "data"}


@pytest.mark.asyncio
async def test_emit_with_no_kwargs():
    """Test emit works with no kwargs."""
    hooks = HookRegistry()
    handler = AsyncMock()

    hooks.register("event", handler)
    await hooks.emit("event")

    handler.assert_called_once_with()


# ============================================================================
# Test: Custom event names
# ============================================================================


@pytest.mark.asyncio
async def test_custom_event_names():
    """Test arbitrary strings work as event names."""
    hooks = HookRegistry()
    handler = AsyncMock()

    hooks.register("my.custom.event.v2", handler)
    await hooks.emit("my.custom.event.v2", data="test")

    handler.assert_called_once_with(data="test")


def test_well_known_constants_are_strings():
    """Test well-known hook constants are plain strings."""
    assert isinstance(HOOK_CYCLE_START, str)
    assert isinstance(HOOK_CYCLE_END, str)
    assert HOOK_CYCLE_START == "cycle_start"
    assert HOOK_CYCLE_END == "cycle_end"
