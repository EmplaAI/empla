"""
E2E Autonomous Employee Simulation Framework

This package provides a complete simulation environment for testing
autonomous employee behavior end-to-end without external API dependencies.

Components:
- environment.py: Simulated world (email, calendar, CRM)
- capabilities.py: Simulated capabilities that interact with the environment
- test_autonomous_behaviors.py: E2E test scenarios

Usage:
    from tests.simulation import SimulatedEnvironment, get_simulated_capabilities

    # Create simulated world
    env = SimulatedEnvironment()

    # Setup scenario (e.g., low pipeline)
    env.crm.set_pipeline_coverage(2.0)  # Below 3.0 target

    # Create employee with simulated capabilities
    capabilities = get_simulated_capabilities(tenant_id, employee_id, env)
    employee = SalesAE(capabilities=capabilities)

    # Run autonomous cycles
    await employee.run_cycle()

    # Assert autonomous behavior
    assert env.email.sent_count > 0  # Employee sent outreach
    assert env.crm.get_pipeline_coverage() > 2.0  # Improved pipeline

Key Design Decisions:
- Uses ACTUAL BDI implementations (empla/bdi/beliefs.py, goals.py, intentions.py)
- Uses ACTUAL memory systems (empla/core/memory/*)
- Uses ACTUAL ProactiveExecutionLoop (empla/core/loop/execution.py)
- ONLY simulates the external environment (no real API calls)
- Fast, deterministic, debuggable tests
- Validates the actual code that will run in production
"""

from tests.simulation.capabilities import (
    SimulatedCalendarCapability,
    SimulatedCRMCapability,
    SimulatedEmailCapability,
    get_simulated_capabilities,
)
from tests.simulation.environment import (
    CustomerHealth,
    DealStage,
    EmailPriority,
    SimulatedCalendarEvent,
    SimulatedContact,
    SimulatedCustomer,
    SimulatedDeal,
    SimulatedEmail,
    SimulatedEnvironment,
)

__all__ = [
    # Environment
    "SimulatedEnvironment",
    "SimulatedEmail",
    "SimulatedCalendarEvent",
    "SimulatedContact",
    "SimulatedDeal",
    "SimulatedCustomer",
    "EmailPriority",
    "DealStage",
    "CustomerHealth",
    # Capabilities
    "SimulatedEmailCapability",
    "SimulatedCalendarCapability",
    "SimulatedCRMCapability",
    "get_simulated_capabilities",
]
