"""
empla.employees.catalog_backed - Catalog-backed base employee.

``CatalogBackedEmployee`` reads its ``default_personality`` / ``default_goals``
/ ``default_capabilities`` from :data:`empla.employees.catalog.ROLE_CATALOG`
using a class-level ``role_code``, and provides templated ``on_start`` /
``on_stop`` handlers that record the role belief and startup/shutdown
episodes. Role-specific helper methods live on the subclass.

Example:
    >>> from empla.employees.catalog_backed import CatalogBackedEmployee
    >>>
    >>> class ProductManager(CatalogBackedEmployee):
    ...     role_code = "pm"
"""

from __future__ import annotations

import copy
import logging
from typing import ClassVar

from empla.employees.base import DigitalEmployee
from empla.employees.catalog import RoleDefinition, get_role
from empla.employees.config import GoalConfig
from empla.employees.exceptions import EmployeeStartupError
from empla.employees.personality import Personality

logger = logging.getLogger(__name__)


class CatalogBackedEmployee(DigitalEmployee):
    """Base ``DigitalEmployee`` that reads its defaults from ``ROLE_CATALOG``."""

    role_code: ClassVar[str] = ""

    @classmethod
    def _role(cls) -> RoleDefinition:
        """Resolve the RoleDefinition for this class, raising if missing."""
        if not cls.role_code:
            raise RuntimeError(f"{cls.__name__} must set a non-empty role_code class attribute")
        role = get_role(cls.role_code)
        if role is None:
            raise RuntimeError(f"{cls.__name__}.role_code={cls.role_code!r} is not in ROLE_CATALOG")
        return role

    @property
    def default_personality(self) -> Personality:
        return copy.deepcopy(self._role().personality)

    @property
    def default_goals(self) -> list[GoalConfig]:
        return list(self._role().default_goals)

    @property
    def default_capabilities(self) -> list[str]:
        return list(self._role().default_capabilities)

    async def on_start(self) -> None:
        """Record the role belief and a startup episode."""
        role = self._role()
        logger.info(f"{role.title} {self.name} initializing...")

        focus = role.focus_keyword or role.code
        try:
            await self.beliefs.update_belief(
                subject="self",
                predicate="role",
                belief_object={"type": role.code, "focus": focus},
                confidence=1.0,
                source="prior",
            )
        except Exception as e:
            logger.error(f"Failed to initialize beliefs for {self.name}: {e}", exc_info=True)
            raise EmployeeStartupError(f"Belief initialization failed: {e}") from e

        try:
            await self.memory.episodic.record_episode(
                episode_type="event",
                description=f"{role.title} {self.name} started and ready for autonomous operation",
                content={
                    "event": "employee_started",
                    "role": role.code,
                    "capabilities": self.default_capabilities,
                    "goals": [g.description for g in self.default_goals],
                },
                importance=0.5,
            )
        except Exception as e:
            logger.warning(f"Failed to record start episode for {self.name}: {e}")

        logger.info(f"{role.title} {self.name} ready for autonomous operation")

    async def on_stop(self) -> None:
        """Record a shutdown episode (non-fatal if it fails)."""
        role = self._role()
        logger.info(f"{role.title} {self.name} shutting down...")

        if self._memory:
            try:
                await self.memory.episodic.record_episode(
                    episode_type="event",
                    description=f"{role.title} {self.name} stopped",
                    content={"event": "employee_stopped"},
                    importance=0.3,
                )
            except Exception as e:
                logger.warning(f"Failed to record stop episode for {self.name}: {e}")


__all__ = ["CatalogBackedEmployee"]
