"""
empla.runner.main - Employee Process Entry Point

Runs a single digital employee as a persistent process:
1. Loads employee from DB
2. Creates the DigitalEmployee instance
3. Starts a health check server
4. Starts employee as a background task alongside a signal handler
5. Waits for either natural exit or SIGTERM/SIGINT for graceful shutdown
6. Updates DB status to "stopped" on exit
"""

import asyncio
import contextlib
import json
import logging
import signal
import sys
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from empla.employees.config import EmployeeConfig, GoalConfig, LLMSettings, LoopSettings
from empla.employees.personality import Personality
from empla.employees.registry import get_employee_class
from empla.models.database import get_engine, get_sessionmaker
from empla.models.employee import Employee as EmployeeModel
from empla.runner.health import HealthServer

logger = logging.getLogger(__name__)


async def _refresh_status_from_db(
    session_factory: async_sessionmaker[AsyncSession],
    employee_id: UUID,
    tenant_id: UUID,
) -> str | None:
    """Read current employee status from DB."""
    async with session_factory() as session:
        result = await session.execute(
            select(EmployeeModel.status).where(
                EmployeeModel.id == employee_id,
                EmployeeModel.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()


async def _set_db_status(
    session_factory: async_sessionmaker[AsyncSession],
    employee_id: UUID,
    tenant_id: UUID,
    status: str,
) -> None:
    """Update employee status in DB."""
    async with session_factory() as session:
        await session.execute(
            update(EmployeeModel)
            .where(
                EmployeeModel.id == employee_id,
                EmployeeModel.tenant_id == tenant_id,
            )
            .values(status=status)
        )
        await session.commit()


async def run_employee(
    employee_id: UUID,
    tenant_id: UUID,
    health_port: int,
) -> None:
    """
    Main entry point for running a single employee process.

    Args:
        employee_id: UUID of the employee to run
        tenant_id: UUID of the tenant
        health_port: Port for the health check HTTP server
    """
    logger.info(
        f"Starting employee runner: employee={employee_id}, tenant={tenant_id}, "
        f"health_port={health_port}"
    )

    # Initialize database connection
    engine = get_engine()
    session_factory = get_sessionmaker(engine)

    # Load employee from DB (eagerly load goals)
    async with session_factory() as session:
        result = await session.execute(
            select(EmployeeModel)
            .options(selectinload(EmployeeModel.goals))
            .where(
                EmployeeModel.id == employee_id,
                EmployeeModel.tenant_id == tenant_id,
                EmployeeModel.deleted_at.is_(None),
            )
        )
        db_employee = result.scalar_one_or_none()

    if db_employee is None:
        logger.error(f"Employee {employee_id} not found in tenant {tenant_id}")
        await engine.dispose()
        sys.exit(1)

    # Resolve employee class
    employee_class = get_employee_class(db_employee.role)
    if employee_class is None:
        logger.error(f"Unknown employee role: {db_employee.role}")
        await engine.dispose()
        sys.exit(1)

    # Build full config from DB record (personality, goals, llm, loop)
    try:
        db_config = db_employee.config or {}
        if isinstance(db_config, str):
            try:
                db_config = json.loads(db_config)
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning(
                    "Malformed employee config (string, not JSON), using defaults: %s",
                    exc,
                    extra={"employee_id": str(employee_id)},
                )
                db_config = {}
        if not isinstance(db_config, dict):
            logger.warning(
                "Employee config is %s instead of dict, using defaults",
                type(db_config).__name__,
                extra={"employee_id": str(employee_id)},
            )
            db_config = {}

        goal_configs = [
            GoalConfig(
                goal_type=g.goal_type,
                description=g.description,
                priority=g.priority,
                target=g.target,
            )
            for g in (db_employee.goals or [])
            if g.status in ("active", "in_progress")
        ]

        config = EmployeeConfig(
            name=db_employee.name,
            role=db_employee.role,
            email=db_employee.email,
            tenant_id=db_employee.tenant_id,
            capabilities=db_employee.capabilities,
            personality=Personality(**db_employee.personality)
            if db_employee.personality is not None
            else None,
            goals=goal_configs,
            llm=LLMSettings(**(db_config.get("llm") or {})),
            loop=LoopSettings(**(db_config.get("loop") or {})),
            metadata=db_config.get("metadata") or {},
        )
    except (ValidationError, TypeError, KeyError) as e:
        logger.error(
            "Failed to build config for employee %s from DB data: %s. "
            "Check the employee's personality, config.llm, and config.loop fields.",
            employee_id,
            e,
            exc_info=True,
            extra={"employee_id": str(employee_id), "tenant_id": str(tenant_id)},
        )
        try:
            await _set_db_status(session_factory, employee_id, tenant_id, "stopped")
        except Exception:
            logger.error("Failed to set DB status after config error", exc_info=True)
        await engine.dispose()
        sys.exit(1)

    employee = employee_class(config)

    # Start health server
    health = HealthServer(employee_id=employee_id, port=health_port)
    await health.start()

    # Build status checker callback (refreshes employee.status from DB).
    # Passed to employee.start() → ProactiveExecutionLoop so the loop can
    # react to external status changes (pause-via-DB pattern).
    async def status_checker(emp_model: EmployeeModel) -> None:
        try:
            db_status = await _refresh_status_from_db(session_factory, employee_id, tenant_id)
        except Exception:
            logger.warning(
                f"Failed to refresh status from DB for employee {employee_id}, "
                "keeping current status",
                exc_info=True,
                extra={"employee_id": str(employee_id)},
            )
            return
        if db_status is None:
            logger.warning(
                f"Employee {employee_id} not found in DB during status check, "
                "setting status to 'stopped'",
                extra={"employee_id": str(employee_id)},
            )
            emp_model.status = "stopped"
            return
        emp_model.status = db_status

    # Wire up signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Received shutdown signal, stopping employee...")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        # Start employee in a task so we can cancel on signal
        async def _run() -> None:
            await employee.start(run_loop=True, status_checker=status_checker)

        employee_task = asyncio.create_task(_run())
        signal_task = asyncio.create_task(stop_event.wait())

        # Wait for either the employee to finish or a shutdown signal
        done, _pending = await asyncio.wait(
            [employee_task, signal_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        if signal_task in done:
            # Signal received — gracefully stop the employee
            signal_task.result()  # consume result
            await employee.stop()
            try:
                await asyncio.wait_for(employee_task, timeout=30.0)
            except TimeoutError:
                logger.warning("Employee task did not stop within 30s, cancelling")
                employee_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await employee_task
        else:
            # Employee finished on its own — cancel the signal waiter
            signal_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await signal_task

    except Exception:
        logger.error("Employee runner crashed", exc_info=True)
    finally:
        # Stop health server
        await health.stop()

        # Update DB status to "stopped"
        try:
            await _set_db_status(session_factory, employee_id, tenant_id, "stopped")
            logger.info(f"Employee {employee_id} status set to 'stopped' in DB")
        except Exception:
            logger.error(
                f"Failed to update employee {employee_id} status to 'stopped' in DB. "
                "Database may show stale status.",
                exc_info=True,
                extra={
                    "employee_id": str(employee_id),
                    "tenant_id": str(tenant_id),
                },
            )

        # Clean up engine
        await engine.dispose()
        logger.info(f"Employee runner exiting: {employee_id}")
