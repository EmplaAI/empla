"""
empla.core.hooks - BDI Lifecycle Hook Registry

Lightweight hook system for observing and extending the BDI cycle.
Handlers are async callables that receive keyword arguments specific
to each hook point. Hook failures are logged but never propagate.

Example:
    >>> hooks = HookRegistry()
    >>> async def on_cycle(employee_id, cycle_count, **kwargs):
    ...     print(f"Cycle {cycle_count}")
    >>> hooks.register("cycle_start", on_cycle)
    >>> await hooks.emit("cycle_start", employee_id=eid, cycle_count=1)
"""

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# Type alias for hook handlers
HookHandler = Callable[..., Awaitable[None]]

# Well-known hook names (string constants for discoverability).
# Each hook emits specific kwargs:
#
# cycle_start:                employee_id, cycle_count
# cycle_end:                  employee_id, cycle_count, duration_seconds, success
# before_perception:          employee_id, cycle_count
# after_perception:           employee_id, cycle_count, perception_result
# before_belief_update:       employee_id, observations
# after_belief_update:        employee_id, changed_beliefs
# before_strategic_planning:  employee_id
# after_strategic_planning:   employee_id
# before_intention_execution: employee_id
# after_intention_execution:  employee_id, result
# after_reflection:           employee_id, result
# employee_start:             employee_id, name, role
# employee_stop:              employee_id, name
HOOK_CYCLE_START = "cycle_start"
HOOK_CYCLE_END = "cycle_end"
HOOK_BEFORE_PERCEPTION = "before_perception"
HOOK_AFTER_PERCEPTION = "after_perception"
HOOK_BEFORE_BELIEF_UPDATE = "before_belief_update"
HOOK_AFTER_BELIEF_UPDATE = "after_belief_update"
HOOK_BEFORE_STRATEGIC_PLANNING = "before_strategic_planning"
HOOK_AFTER_STRATEGIC_PLANNING = "after_strategic_planning"
HOOK_BEFORE_INTENTION_EXECUTION = "before_intention_execution"
HOOK_AFTER_INTENTION_EXECUTION = "after_intention_execution"
HOOK_AFTER_REFLECTION = "after_reflection"
HOOK_EMPLOYEE_START = "employee_start"
HOOK_EMPLOYEE_STOP = "employee_stop"


class HookRegistry:
    """Registry for BDI lifecycle hooks.

    Handlers are async callables that receive keyword arguments
    specific to each hook point. Hook failures are logged but
    never propagate to the caller.

    Example:
        >>> hooks = HookRegistry()
        >>> async def on_cycle(employee_id, cycle_count, **kwargs):
        ...     print(f"Cycle {cycle_count}")
        >>> hooks.register("cycle_start", on_cycle)
        >>> await hooks.emit("cycle_start", employee_id=eid, cycle_count=1)
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[HookHandler]] = defaultdict(list)

    def register(self, event: str, handler: HookHandler) -> None:
        """Register a handler for an event."""
        self._handlers[event].append(handler)

    def unregister(self, event: str, handler: HookHandler) -> bool:
        """Unregister a handler. Returns True if found."""
        handlers = self._handlers.get(event)
        if handlers and handler in handlers:
            handlers.remove(handler)
            return True
        return False

    async def emit(self, event: str, **kwargs: Any) -> None:
        """Emit an event, calling all registered handlers.

        Each handler is called with **kwargs. Errors are logged
        but do not propagate or affect other handlers.
        """
        handlers = self._handlers.get(event)
        if not handlers:
            return
        for handler in handlers:
            try:
                await handler(**kwargs)
            except Exception:
                handler_name = getattr(handler, "__qualname__", repr(handler))
                logger.error(
                    "Hook handler %r failed for event '%s'",
                    handler_name,
                    event,
                    exc_info=True,
                    extra={
                        "hook_event": event,
                        "hook_handler": handler_name,
                    },
                )

    def clear(self, event: str | None = None) -> None:
        """Clear handlers for an event, or all handlers if None."""
        if event is None:
            self._handlers.clear()
        else:
            self._handlers.pop(event, None)

    def has_handlers(self, event: str) -> bool:
        """Check if any handlers are registered for an event."""
        return bool(self._handlers.get(event))
