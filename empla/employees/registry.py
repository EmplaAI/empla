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
    "pm": "empla.employees.pm:ProductManager",
    "sdr": "empla.employees.sdr:SDR",
    "recruiter": "empla.employees.recruiter:Recruiter",
}


def get_employee_class(role: str) -> type[DigitalEmployee] | None:
    """Return the DigitalEmployee subclass for *role*.

    Built-in roles (``sales_ae``, ``csm``, ``pm``, ``sdr``, ``recruiter``)
    return their dedicated subclass with role-specific helpers. Any other
    string — including ``custom`` for admin-generated employees — returns
    :class:`GenericEmployee`, which has no role-specific behavior and reads
    every value from the Employee row's persisted state (materialized at
    creation time from an admin-reviewed LLM draft).

    Returns ``None`` only if a built-in role's importlib resolution fails,
    which signals a code-path bug rather than user error.
    """
    path = _EMPLOYEE_ROLE_MAP.get(role)
    if path is None:
        # Unknown role → custom employee, runtime resolves to GenericEmployee.
        # No DB lookup, no role table; the Employee row is the source of truth.
        from empla.employees.generic import GenericEmployee

        return GenericEmployee

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
