"""
empla.services.employee_manager - Employee Runtime Manager

Singleton service that manages running digital employee instances.
Handles start, stop, pause, resume operations.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from empla.employees import CustomerSuccessManager, SalesAE
from empla.employees.base import DigitalEmployee
from empla.employees.config import EmployeeConfig
from empla.models.employee import Employee as EmployeeModel

logger = logging.getLogger(__name__)

# Circuit breaker settings for employee loop errors
MAX_CONSECUTIVE_ERRORS = 5
ERROR_BACKOFF_SECONDS = 30


class UnsupportedRoleError(ValueError):
    """Raised when attempting to start an employee with an unsupported role."""

    pass

# Map role strings to employee classes
EMPLOYEE_CLASSES: dict[str, type[DigitalEmployee]] = {
    "sales_ae": SalesAE,
    "csm": CustomerSuccessManager,
}


class EmployeeManager:
    """
    Singleton manager for running employee instances.

    Provides:
    - Start/stop/pause/resume employee lifecycle
    - Track running instances
    - Get runtime status

    Usage:
        manager = get_employee_manager()
        await manager.start_employee(employee_id, tenant_id, db)
        status = manager.get_status(employee_id)
        await manager.stop_employee(employee_id)
    """

    _instance: "EmployeeManager | None" = None
    # Initialize lock at class level to avoid race condition during lazy init
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls) -> "EmployeeManager":
        """Ensure singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize manager state."""
        if getattr(self, "_initialized", False):
            return

        self._instances: dict[UUID, DigitalEmployee] = {}
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._paused: set[UUID] = set()
        self._error_states: dict[UUID, str] = {}  # Track last error per employee
        self._initialized = True

        logger.info("EmployeeManager initialized")

    async def start_employee(
        self,
        employee_id: UUID,
        tenant_id: UUID,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """
        Start a digital employee.

        Args:
            employee_id: UUID of the employee to start
            tenant_id: UUID of the tenant (enforces tenant isolation)
            session: Database session for fetching employee data

        Returns:
            Status dictionary with employee info

        Raises:
            ValueError: If employee not found
            UnsupportedRoleError: If role is not supported
            RuntimeError: If employee is already running
        """
        async with self._lock:
            # Check if already running
            if employee_id in self._instances:
                raise RuntimeError(f"Employee {employee_id} is already running")

            # Fetch employee from database with tenant isolation
            result = await session.execute(
                select(EmployeeModel).where(
                    EmployeeModel.id == employee_id,
                    EmployeeModel.tenant_id == tenant_id,
                    EmployeeModel.deleted_at.is_(None),
                )
            )
            db_employee = result.scalar_one_or_none()

            if db_employee is None:
                raise ValueError(f"Employee {employee_id} not found")

            # Get employee class for role
            employee_class = EMPLOYEE_CLASSES.get(db_employee.role)
            if employee_class is None:
                raise UnsupportedRoleError(
                    f"Unsupported role '{db_employee.role}'. "
                    f"Supported roles: {list(EMPLOYEE_CLASSES.keys())}"
                )

            # Create employee config from database record
            config = EmployeeConfig(
                name=db_employee.name,
                role=db_employee.role,
                email=db_employee.email,
                tenant_id=db_employee.tenant_id,
                capabilities=db_employee.capabilities,
            )

            # Create employee instance
            employee = employee_class(config)

            # Start employee (non-blocking)
            logger.info(f"Starting employee {employee_id} ({db_employee.name})")
            await employee.start(run_loop=False)

            # Store instance
            self._instances[employee_id] = employee

            # Start the loop in background
            task = asyncio.create_task(self._run_employee_loop(employee_id, employee))
            self._tasks[employee_id] = task

            # Update database status
            # Only set activated_at on first transition into "active"
            if db_employee.status != "active":
                db_employee.activated_at = datetime.now(UTC)
            db_employee.status = "active"
            await session.commit()

            logger.info(f"Employee {employee_id} started successfully")

            return self.get_status(employee_id)

    async def _run_employee_loop(
        self,
        employee_id: UUID,
        employee: DigitalEmployee,
    ) -> None:
        """
        Run the employee's proactive loop in background.

        This task runs until the employee is stopped.
        Implements circuit breaker pattern to stop on repeated failures.
        """
        consecutive_errors = 0

        try:
            while employee.is_running and employee_id in self._instances:
                # Check if paused
                if employee_id in self._paused:
                    await asyncio.sleep(1)
                    continue

                # Run one cycle with circuit breaker pattern
                try:
                    await employee.run_once()
                    consecutive_errors = 0  # Reset on success
                except asyncio.CancelledError:
                    raise  # Let cancellation propagate
                except Exception as e:
                    consecutive_errors += 1
                    logger.error(
                        f"Error in employee {employee_id} cycle "
                        f"(attempt {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}",
                        exc_info=True,
                        extra={
                            "employee_id": str(employee_id),
                            "error_type": type(e).__name__,
                            "consecutive_errors": consecutive_errors,
                        },
                    )

                    # Circuit breaker: stop loop after too many consecutive errors
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        logger.error(
                            f"Employee {employee_id} exceeded max consecutive errors "
                            f"({MAX_CONSECUTIVE_ERRORS}), stopping loop",
                            extra={"employee_id": str(employee_id)},
                        )
                        # Mark as in error state but keep instance for status reporting
                        self._error_states[employee_id] = str(e)
                        break

                    # Back off on errors
                    await asyncio.sleep(ERROR_BACKOFF_SECONDS)
                    continue

                # Wait before next cycle
                await asyncio.sleep(employee.config.loop.cycle_interval_seconds)

        except asyncio.CancelledError:
            logger.info(f"Employee {employee_id} loop cancelled")
        except Exception as e:
            logger.error(
                f"Employee {employee_id} loop failed with unexpected error: {e}",
                exc_info=True,
                extra={"employee_id": str(employee_id)},
            )
            self._error_states[employee_id] = str(e)
        finally:
            # Clean up under lock to avoid race conditions
            async with self._lock:
                self._instances.pop(employee_id, None)
                self._tasks.pop(employee_id, None)
                self._paused.discard(employee_id)

    async def stop_employee(
        self,
        employee_id: UUID,
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """
        Stop a running employee.

        Args:
            employee_id: UUID of the employee to stop
            session: Optional database session to update status

        Returns:
            Final status dictionary

        Raises:
            ValueError: If employee is not running
        """
        async with self._lock:
            if employee_id not in self._instances:
                raise ValueError(f"Employee {employee_id} is not running")

            employee = self._instances[employee_id]
            status = self.get_status(employee_id)

            # Capture tenant_id before cleanup for DB update with tenant isolation
            tenant_id = employee.config.tenant_id

            logger.info(f"Stopping employee {employee_id}")

            # Cancel the background task
            if employee_id in self._tasks:
                task = self._tasks[employee_id]
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=10.0)
                except (TimeoutError, asyncio.CancelledError):
                    pass

            # Stop the employee
            await employee.stop()

            # Clean up
            self._instances.pop(employee_id, None)
            self._tasks.pop(employee_id, None)
            self._paused.discard(employee_id)
            self._error_states.pop(employee_id, None)

            # Update database if session provided
            # Note: Setting status to "stopped" (can be restarted, vs "terminated" = permanent)
            if session:
                result = await session.execute(
                    select(EmployeeModel).where(
                        EmployeeModel.id == employee_id,
                        EmployeeModel.tenant_id == tenant_id,
                    )
                )
                db_employee = result.scalar_one_or_none()
                if db_employee:
                    db_employee.status = "stopped"
                    await session.commit()

            logger.info(f"Employee {employee_id} stopped")

            status["is_running"] = False
            return status

    async def pause_employee(self, employee_id: UUID) -> dict[str, Any]:
        """
        Pause a running employee.

        Paused employees remain in memory but don't execute cycles.

        Args:
            employee_id: UUID of the employee to pause

        Returns:
            Status dictionary

        Raises:
            ValueError: If employee is not running or already paused
        """
        async with self._lock:
            if employee_id not in self._instances:
                raise ValueError(f"Employee {employee_id} is not running")

            if employee_id in self._paused:
                raise ValueError(f"Employee {employee_id} is already paused")

            self._paused.add(employee_id)
            logger.info(f"Employee {employee_id} paused")

            return self.get_status(employee_id)

    async def resume_employee(self, employee_id: UUID) -> dict[str, Any]:
        """
        Resume a paused employee.

        Args:
            employee_id: UUID of the employee to resume

        Returns:
            Status dictionary

        Raises:
            ValueError: If employee is not running or not paused
        """
        async with self._lock:
            if employee_id not in self._instances:
                raise ValueError(f"Employee {employee_id} is not running")

            if employee_id not in self._paused:
                raise ValueError(f"Employee {employee_id} is not paused")

            self._paused.discard(employee_id)
            logger.info(f"Employee {employee_id} resumed")

            return self.get_status(employee_id)

    def get_status(self, employee_id: UUID) -> dict[str, Any]:
        """
        Get runtime status for an employee.

        Args:
            employee_id: UUID of the employee

        Returns:
            Status dictionary with:
            - id: Employee ID
            - name: Employee name
            - role: Employee role
            - is_running: Whether instance exists in memory
            - is_paused: Whether execution is paused
            - has_error: Whether employee stopped due to error
            - last_error: Last error message (if any)
            - started_at: When started
            - cycle_count: Number of cycles run (if available)
        """
        error_state = self._error_states.get(employee_id)

        if employee_id not in self._instances:
            return {
                "id": str(employee_id),
                "is_running": False,
                "is_paused": False,
                "has_error": error_state is not None,
                "last_error": error_state,
            }

        employee = self._instances[employee_id]
        base_status = employee.get_status()

        return {
            "id": str(employee_id),
            "name": base_status.get("name"),
            "role": base_status.get("role"),
            "email": base_status.get("email"),
            "is_running": True,
            "is_paused": employee_id in self._paused,
            "has_error": error_state is not None,
            "last_error": error_state,
            "started_at": base_status.get("started_at"),
            "capabilities": base_status.get("capabilities"),
        }

    def list_running(self) -> list[UUID]:
        """
        Get list of running employee IDs.

        Returns:
            List of UUIDs for all running employees
        """
        return list(self._instances.keys())

    def is_running(self, employee_id: UUID) -> bool:
        """Check if an employee is currently running."""
        return employee_id in self._instances

    def is_paused(self, employee_id: UUID) -> bool:
        """Check if an employee is currently paused."""
        return employee_id in self._paused

    async def stop_all(self) -> dict[str, list[UUID]]:
        """
        Stop all running employees.

        Returns:
            Dictionary with 'stopped' and 'failed' lists of employee IDs.
            Callers should check 'failed' to handle partial failures.
        """
        employee_ids = list(self._instances.keys())
        stopped: list[UUID] = []
        failed: list[UUID] = []

        for employee_id in employee_ids:
            try:
                await self.stop_employee(employee_id)
                stopped.append(employee_id)
            except Exception as e:
                logger.error(
                    f"Error stopping employee {employee_id}: {e}",
                    exc_info=True,
                    extra={"employee_id": str(employee_id)},
                )
                failed.append(employee_id)

        if failed:
            logger.warning(
                f"Failed to stop {len(failed)} of {len(employee_ids)} employees",
                extra={"failed_employees": [str(eid) for eid in failed]},
            )

        return {"stopped": stopped, "failed": failed}


def get_employee_manager() -> EmployeeManager:
    """Get the singleton EmployeeManager instance."""
    return EmployeeManager()
