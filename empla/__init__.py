"""
empla - Production-Ready Digital Employees + Extensible Platform

The operating system for autonomous AI workers.

This package provides:
1. Core autonomous engine (BDI architecture, proactive execution, memory systems)
2. Pre-built digital employees (Sales AE, CSM, Product Manager, etc.)
3. Extensible platform for building custom employees
4. Integration framework for external services
5. REST API and CLI for employee management

Example:
    >>> from empla.core.bdi import BeliefSystem, GoalSystem, IntentionStack
    >>> from empla.core.loop import ProactiveExecutionLoop
    >>> from empla.employees import SalesAE

    >>> # Create a Sales AE employee
    >>> employee = SalesAE(name="Jordan Chen")
    >>> await employee.start()

Architecture:
    - Core: BDI engine, memory systems, proactive loop
    - Capabilities: Email, calendar, messaging, meetings, research
    - Integrations: Microsoft 365, Google Workspace, CRMs
    - Employees: Pre-built roles (Sales AE, CSM, PM, etc.)

Documentation:
    - Architecture: See ARCHITECTURE.md
    - Getting Started: See docs/guides/getting-started.md
    - API Reference: See docs/api/
"""

__version__ = "0.1.0"
__author__ = "empla contributors"
__license__ = "Apache-2.0"

# Core components
from empla.bdi import BeliefSystem, GoalSystem, IntentionStack
from empla.core.loop import ProactiveExecutionLoop
from empla.core.memory import (
    EpisodicMemorySystem,
    ProceduralMemorySystem,
    SemanticMemorySystem,
    WorkingMemory,
)

# Pre-built employees
from empla.employees import (
    CSM,
    CustomerSuccessManager,
    DigitalEmployee,
    EmployeeConfig,
    SalesAE,
)

__all__ = [
    "CSM",
    "BeliefSystem",
    "CustomerSuccessManager",
    "DigitalEmployee",
    "EmployeeConfig",
    "EpisodicMemorySystem",
    "GoalSystem",
    "IntentionStack",
    "ProactiveExecutionLoop",
    "ProceduralMemorySystem",
    "SalesAE",
    "SemanticMemorySystem",
    "WorkingMemory",
    "__version__",
]
