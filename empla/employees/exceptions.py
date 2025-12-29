"""
empla.employees.exceptions - Custom exceptions for employee operations

Provides a hierarchy of domain-specific exceptions for better error handling
and debugging of employee-related operations.

Example:
    >>> from empla.employees.exceptions import EmployeeStartupError
    >>>
    >>> try:
    ...     await employee.start()
    ... except EmployeeStartupError as e:
    ...     logger.error(f"Failed to start employee: {e}")
"""


class EmployeeError(Exception):
    """Base exception for all employee-related errors."""


class EmployeeStartupError(EmployeeError):
    """
    Raised when an employee fails to start.

    This can occur due to:
    - Database connection failures
    - Missing API keys
    - Invalid configuration
    - Component initialization failures
    """


class EmployeeConfigError(EmployeeError):
    """
    Raised when employee configuration is invalid.

    This can occur due to:
    - Missing required fields
    - Invalid field values
    - Missing environment variables (e.g., API keys)
    - Invalid capability specifications
    """


class EmployeeNotStartedError(EmployeeError):
    """
    Raised when accessing employee components before start() is called.

    Use this when trying to access:
    - employee_id
    - beliefs, goals, intentions
    - memory systems
    - capabilities
    - LLM service
    """


class EmployeeShutdownError(EmployeeError):
    """
    Raised when an employee fails to shut down cleanly.

    This can occur due to:
    - Failed capability shutdowns
    - Database errors during cleanup
    - Loop cancellation issues
    """


class LLMGenerationError(EmployeeError):
    """
    Raised when LLM generation fails.

    This can occur due to:
    - API rate limits
    - Network errors
    - Invalid prompts
    - Service unavailability
    """


__all__ = [
    "EmployeeConfigError",
    "EmployeeError",
    "EmployeeNotStartedError",
    "EmployeeShutdownError",
    "EmployeeStartupError",
    "LLMGenerationError",
]
