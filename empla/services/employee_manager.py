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
        await manager.start_employee(employee_id, db)
        status = manager.get_status(employee_id)
        await manager.stop_employee(employee_id)
    """

    _instance: "EmployeeManager | None" = None
    _lock = asyncio.Lock()

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
        self._initialized = True

        logger.info("EmployeeManager initialized")

    async def start_employee(
        self,
        employee_id: UUID,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """
        Start a digital employee.

        Args:
            employee_id: UUID of the employee to start
            session: Database session for fetching employee data

        Returns:
            Status dictionary with employee info

        Raises:
            ValueError: If employee not found or role not supported
            RuntimeError: If employee is already running
        """
        async with self._lock:
            # Check if already running
            if employee_id in self._instances:
                raise RuntimeError(f"Employee {employee_id} is already running")

            # Fetch employee from database
            result = await session.execute(
                select(EmployeeModel).where(
                    EmployeeModel.id == employee_id,
                    EmployeeModel.deleted_at.is_(None),
                )
            )
            db_employee = result.scalar_one_or_none()

            if db_employee is None:
                raise ValueError(f"Employee {employee_id} not found")

            # Get employee class for role
            employee_class = EMPLOYEE_CLASSES.get(db_employee.role)
            if employee_class is None:
                raise ValueError(
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
            db_employee.status = "active"
            db_employee.activated_at = datetime.now(UTC)
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
        """
        try:
            while employee.is_running and employee_id in self._instances:
                # Check if paused
                if employee_id in self._paused:
                    await asyncio.sleep(1)
                    continue

                # Run one cycle
                try:
                    await employee.run_once()
                except Exception as e:
                    logger.error(
                        f"Error in employee {employee_id} cycle: {e}",
                        exc_info=True,
                    )

                # Wait before next cycle
                await asyncio.sleep(employee.config.loop.cycle_interval_seconds)

        except asyncio.CancelledError:
            logger.info(f"Employee {employee_id} loop cancelled")
        except Exception as e:
            logger.error(f"Employee {employee_id} loop failed: {e}", exc_info=True)
        finally:
            # Clean up if still in instances
            if employee_id in self._instances:
                del self._instances[employee_id]
            if employee_id in self._tasks:
                del self._tasks[employee_id]
            if employee_id in self._paused:
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
            if employee_id in self._instances:
                del self._instances[employee_id]
            if employee_id in self._tasks:
                del self._tasks[employee_id]
            if employee_id in self._paused:
                self._paused.discard(employee_id)

            # Update database if session provided
            if session:
                result = await session.execute(
                    select(EmployeeModel).where(EmployeeModel.id == employee_id)
                )
                db_employee = result.scalar_one_or_none()
                if db_employee:
                    db_employee.status = "paused"
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
            ValueError: If employee is not running
        """
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
            ValueError: If employee is not paused
        """
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
            - is_running: Whether running
            - is_paused: Whether paused
            - started_at: When started
            - cycle_count: Number of cycles run (if available)
        """
        if employee_id not in self._instances:
            return {
                "id": str(employee_id),
                "is_running": False,
                "is_paused": False,
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

    async def stop_all(self) -> None:
        """Stop all running employees."""
        employee_ids = list(self._instances.keys())
        for employee_id in employee_ids:
            try:
                await self.stop_employee(employee_id)
            except Exception as e:
                logger.error(f"Error stopping employee {employee_id}: {e}")


def get_employee_manager() -> EmployeeManager:
    """Get the singleton EmployeeManager instance."""
    return EmployeeManager()
