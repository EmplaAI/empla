"""
empla.employees.generic - Generic digital employee for custom roles.

``GenericEmployee`` is the runtime class for any employee whose ``role`` is
NOT one of the built-in roles (``sales_ae``, ``csm``, ``pm``, ``sdr``,
``recruiter``). It carries no role-specific behavior — every value the BDI
loop reads (personality, goals, capabilities, role description) comes from
the ``Employee`` row's persisted state, which was materialized at creation
time from an admin-reviewed LLM-generated draft.

Why this exists:
    PR #85 lets admins describe a job in plain English ("I want a marketing
    manager who runs campaigns") and have the LLM generate a working employee.
    There is no template/role abstraction — each custom employee is one-off.
    The runner needs *some* concrete ``DigitalEmployee`` subclass to
    instantiate, but it has nothing role-specific to add — the Employee row
    already holds everything.

Why the abstract methods are still overridden:
    ``DigitalEmployee.default_personality`` / ``default_goals`` /
    ``default_capabilities`` are ``@abstractmethod``. Python refuses to
    instantiate a subclass that leaves any abstract method unoverridden,
    even if the call site never reaches them. So ``GenericEmployee``
    physically implements all three with sensible fallbacks. In practice
    the runner pre-populates ``self.config`` from the DB, and the base class
    falls back to these defaults only when the row is empty.
"""

from __future__ import annotations

from empla.employees.base import DigitalEmployee
from empla.employees.config import GoalConfig
from empla.employees.personality import Personality


class GenericEmployee(DigitalEmployee):
    """``DigitalEmployee`` for custom roles. State lives on the Employee row."""

    @property
    def default_personality(self) -> Personality:
        return self.config.personality or Personality()

    @property
    def default_goals(self) -> list[GoalConfig]:
        return list(self.config.goals or [])

    @property
    def default_capabilities(self) -> list[str]:
        return list(self.config.capabilities or [])
