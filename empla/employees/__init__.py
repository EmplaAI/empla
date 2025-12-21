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
    EmployeeConfig,
    GoalConfig,
    LLMSettings,
    LoopSettings,
    # Default goals
    CSM_DEFAULT_GOALS,
    PM_DEFAULT_GOALS,
    SALES_AE_DEFAULT_GOALS,
)

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
    CommunicationStyle,
    DecisionStyle,
    Formality,
    Personality,
    Tone,
    Verbosity,
    # Pre-built personalities
    CSM_PERSONALITY,
    PM_PERSONALITY,
    SALES_AE_PERSONALITY,
)

# Pre-built employees
from empla.employees.sales_ae import SalesAE
from empla.employees.csm import CustomerSuccessManager

# Convenience alias
CSM = CustomerSuccessManager

__all__ = [
    # Base classes
    "DigitalEmployee",
    "MemorySystem",
    # Configuration
    "EmployeeConfig",
    "GoalConfig",
    "LLMSettings",
    "LoopSettings",
    # Exceptions
    "EmployeeConfigError",
    "EmployeeError",
    "EmployeeNotStartedError",
    "EmployeeShutdownError",
    "EmployeeStartupError",
    "LLMGenerationError",
    # Personality
    "CommunicationStyle",
    "DecisionStyle",
    "Formality",
    "Personality",
    "Tone",
    "Verbosity",
    # Pre-built personalities
    "CSM_PERSONALITY",
    "PM_PERSONALITY",
    "SALES_AE_PERSONALITY",
    # Default goals
    "CSM_DEFAULT_GOALS",
    "PM_DEFAULT_GOALS",
    "SALES_AE_DEFAULT_GOALS",
    # Pre-built employees
    "SalesAE",
    "CustomerSuccessManager",
    "CSM",  # Alias
]
