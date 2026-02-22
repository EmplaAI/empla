"""
empla.employees.registry - Employee Class Registry

Maps role strings to employee class implementations. Used by both the
EmployeeManager (control plane) and the runner (execution plane).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from empla.employees.base import DigitalEmployee

logger = logging.getLogger(__name__)

# Lazy imports to avoid circular dependency issues at module load time.
# The actual classes are imported inside get_employee_class().
_EMPLOYEE_ROLE_MAP: dict[str, str] = {
    "sales_ae": "empla.employees.sales_ae:SalesAE",
    "csm": "empla.employees.csm:CustomerSuccessManager",
}


def get_employee_class(role: str) -> type[DigitalEmployee] | None:
    """Return the DigitalEmployee subclass for *role*, or None if unknown."""
    path = _EMPLOYEE_ROLE_MAP.get(role)
    if path is None:
        return None

    module_path, class_name = path.rsplit(":", 1)
    import importlib

    try:
        module = importlib.import_module(module_path)
        return getattr(module, class_name)  # type: ignore[no-any-return]
    except (ImportError, AttributeError):
        logger.error(
            f"Failed to load employee class for role '{role}' from '{path}'",
            exc_info=True,
        )
        return None


def get_supported_roles() -> list[str]:
    """Return list of all supported role strings."""
    return list(_EMPLOYEE_ROLE_MAP.keys())
