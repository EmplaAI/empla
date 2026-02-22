"""
empla.core - Core Autonomous Engine

This package contains the fundamental components of empla's autonomous system:
- Proactive execution loop for continuous autonomous operation
- Memory systems (episodic, semantic, procedural, working)
- Lifecycle hooks for observing and extending the BDI cycle
- Strategic planning algorithms
"""

from empla.core.hooks import (
    HOOK_AFTER_BELIEF_UPDATE,
    HOOK_AFTER_INTENTION_EXECUTION,
    HOOK_AFTER_PERCEPTION,
    HOOK_AFTER_REFLECTION,
    HOOK_AFTER_STRATEGIC_PLANNING,
    HOOK_BEFORE_BELIEF_UPDATE,
    HOOK_BEFORE_INTENTION_EXECUTION,
    HOOK_BEFORE_PERCEPTION,
    HOOK_BEFORE_STRATEGIC_PLANNING,
    HOOK_CYCLE_END,
    HOOK_CYCLE_START,
    HOOK_EMPLOYEE_START,
    HOOK_EMPLOYEE_STOP,
    HookRegistry,
)

__all__: list[str] = [
    "HOOK_AFTER_BELIEF_UPDATE",
    "HOOK_AFTER_INTENTION_EXECUTION",
    "HOOK_AFTER_PERCEPTION",
    "HOOK_AFTER_REFLECTION",
    "HOOK_AFTER_STRATEGIC_PLANNING",
    "HOOK_BEFORE_BELIEF_UPDATE",
    "HOOK_BEFORE_INTENTION_EXECUTION",
    "HOOK_BEFORE_PERCEPTION",
    "HOOK_BEFORE_STRATEGIC_PLANNING",
    "HOOK_CYCLE_END",
    "HOOK_CYCLE_START",
    "HOOK_EMPLOYEE_START",
    "HOOK_EMPLOYEE_STOP",
    "HookRegistry",
]
