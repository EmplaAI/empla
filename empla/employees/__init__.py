"""
empla.employees - Production-Ready Digital Employees

This module provides ready-to-deploy digital employees and the
infrastructure to build custom ones.

Pre-Built Employees:
- SalesAE: Sales Account Executive - pipeline building, outreach, deal progression
- CustomerSuccessManager: CSM - customer health, retention, onboarding

Building Custom Employees:
    >>> from empla.employees import DigitalEmployee
    >>> from empla.employees.config import EmployeeConfig, GoalConfig
    >>> from empla.employees.personality import Personality
    >>>
    >>> class MyEmployee(DigitalEmployee):
    ...     @property
    ...     def default_personality(self) -> Personality:
    ...         return Personality(extraversion=0.8)
    ...
    ...     @property
    ...     def default_goals(self) -> list[GoalConfig]:
    ...         return [GoalConfig(description="My goal", priority=8)]
    ...
    ...     @property
    ...     def default_capabilities(self) -> list[str]:
    ...         return ["email", "calendar"]

Quick Start:
    >>> from empla.employees import SalesAE, EmployeeConfig
    >>>
    >>> # Create employee (role is a string for extensibility)
    >>> config = EmployeeConfig(
    ...     name="Jordan Chen",
    ...     role="sales_ae",
    ...     email="jordan@company.com"
    ... )
    >>> employee = SalesAE(config)
    >>>
    >>> # Start autonomous operation
    >>> await employee.start()
    >>>
    >>> # Check status
    >>> print(employee.get_status())
    >>>
    >>> # Stop when done
    >>> await employee.stop()
"""

# Base classes
from empla.employees.base import DigitalEmployee, MemorySystem

# Configuration
from empla.employees.config import (
    # Default goals
    CSM_DEFAULT_GOALS,
    PM_DEFAULT_GOALS,
    SALES_AE_DEFAULT_GOALS,
    EmployeeConfig,
    GoalConfig,
    LLMSettings,
    LoopSettings,
)
from empla.employees.csm import CustomerSuccessManager

# Exceptions
from empla.employees.exceptions import (
    EmployeeConfigError,
    EmployeeError,
    EmployeeNotStartedError,
    EmployeeShutdownError,
    EmployeeStartupError,
    LLMGenerationError,
)

# Personality
from empla.employees.personality import (
    # Pre-built personalities
    CSM_PERSONALITY,
    PM_PERSONALITY,
    SALES_AE_PERSONALITY,
    CommunicationStyle,
    DecisionStyle,
    Formality,
    Personality,
    Tone,
    Verbosity,
)

# Registry
from empla.employees.registry import get_employee_class, get_supported_roles

# Pre-built employees
from empla.employees.sales_ae import SalesAE

# Convenience alias
CSM = CustomerSuccessManager

__all__ = [
    "CSM",
    "CSM_DEFAULT_GOALS",
    "CSM_PERSONALITY",
    "PM_DEFAULT_GOALS",
    "PM_PERSONALITY",
    "SALES_AE_DEFAULT_GOALS",
    "SALES_AE_PERSONALITY",
    "CommunicationStyle",
    "CustomerSuccessManager",
    "DecisionStyle",
    "DigitalEmployee",
    "EmployeeConfig",
    "EmployeeConfigError",
    "EmployeeError",
    "EmployeeNotStartedError",
    "EmployeeShutdownError",
    "EmployeeStartupError",
    "Formality",
    "GoalConfig",
    "LLMGenerationError",
    "LLMSettings",
    "LoopSettings",
    "MemorySystem",
    "Personality",
    "SalesAE",
    "Tone",
    "Verbosity",
    "get_employee_class",
    "get_supported_roles",
]
