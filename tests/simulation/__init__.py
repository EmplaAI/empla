"""
E2E Autonomous Employee Simulation Framework

This package provides a complete simulation environment for testing
autonomous employee behavior end-to-end without external API dependencies.

Components:
- environment.py: Simulated world (email, calendar, CRM)
- test_autonomous_behaviors.py: E2E test scenarios

Usage:
    from tests.simulation import SimulatedEnvironment

    # Create simulated world
    env = SimulatedEnvironment()

    # Setup scenario
    env.crm.set_pipeline_coverage(2.0)  # Below 3.0 target
    env.email.receive_email(SimulatedEmail(...))
    events = env.calendar.get_upcoming_events(hours=24)

Key Design Decisions:
- Uses ACTUAL BDI implementations (empla/bdi/beliefs.py, goals.py, intentions.py)
- Uses ACTUAL memory systems (empla/core/memory/*)
- Uses ACTUAL ProactiveExecutionLoop (empla/core/loop/execution.py)
- ONLY simulates the external environment (no real API calls)
- Fast, deterministic, debuggable tests
- Validates the actual code that will run in production
"""

from tests.simulation.environment import (
    CustomerHealth,
    DealStage,
    EmailPriority,
    SimulatedCalendarEvent,
    SimulatedComputeSystem,
    SimulatedContact,
    SimulatedCustomer,
    SimulatedDeal,
    SimulatedEmail,
    SimulatedEnvironment,
    SimulatedWorkspaceSystem,
)

__all__ = [
    "CustomerHealth",
    "DealStage",
    "EmailPriority",
    "SimulatedCalendarEvent",
    "SimulatedComputeSystem",
    "SimulatedContact",
    "SimulatedCustomer",
    "SimulatedDeal",
    "SimulatedEmail",
    "SimulatedEnvironment",
    "SimulatedWorkspaceSystem",
]
