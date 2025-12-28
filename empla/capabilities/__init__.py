"""
Capabilities Layer - The "Hands" of Digital Employees

This module provides the plugin-based capability system that enables
employees to interact with the external world.

Capabilities include:
- Email: Monitor inbox, send emails, triage
- Calendar: Schedule meetings, find optimal times
- Messaging: Slack/Teams integration
- Browser: Web research, data extraction
- Document: Generate presentations, reports
- And more...

Usage:
    from empla.capabilities import CapabilityRegistry, CapabilityType
    from empla.capabilities.email import EmailCapability, EmailConfig

    # Create registry
    registry = CapabilityRegistry()

    # Enable capability for employee
    await registry.enable_for_employee(
        employee_id=employee.employee_id,
        tenant_id=employee.tenant_id,
        capability_type=CapabilityType.EMAIL,
        config=EmailConfig(...)
    )

    # Perceive environment
    observations = await registry.perceive_all(employee.employee_id)

    # Execute action
    result = await registry.execute_action(employee.employee_id, action)
"""

from empla.capabilities.base import (
    Action,
    ActionResult,
    BaseCapability,
    CapabilityConfig,
    CapabilityType,
    Observation,
)
from empla.capabilities.email import (
    Email,
    EmailCapability,
    EmailConfig,
    EmailPriority,
    EmailProvider,
)
from empla.capabilities.registry import CapabilityRegistry

__all__ = [
    "Action",
    "ActionResult",
    # Base abstractions
    "BaseCapability",
    "CapabilityConfig",
    "CapabilityRegistry",
    "CapabilityType",
    "Email",
    # Email capability
    "EmailCapability",
    "EmailConfig",
    "EmailPriority",
    "EmailProvider",
    "Observation",
]
