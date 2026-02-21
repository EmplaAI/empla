"""
empla.cli - Command-Line Interface

Provides CLI commands for managing digital employees.

Usage:
    python -m empla.cli employee start <employee-id> --tenant-id UUID
    python -m empla.cli employee stop <employee-id> --tenant-id UUID
    python -m empla.cli employee status <employee-id> --tenant-id UUID
    python -m empla.cli employee list
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import TYPE_CHECKING, Any
from uuid import UUID

from empla.services.employee_manager import get_employee_manager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


def _get_session_factory() -> tuple[async_sessionmaker[AsyncSession], AsyncEngine]:
    """Create a DB session factory for CLI operations.

    Returns:
        Tuple of (async_sessionmaker, AsyncEngine).
    """
    from empla.models.database import get_engine, get_sessionmaker

    engine = get_engine()
    return get_sessionmaker(engine), engine


async def _start_employee(args: argparse.Namespace) -> None:
    """Start an employee subprocess."""
    session_factory, engine = _get_session_factory()
    manager = get_employee_manager()

    try:
        async with session_factory() as session:
            status = await manager.start_employee(
                employee_id=args.employee_id,
                tenant_id=args.tenant_id,
                session=session,
            )
        print(json.dumps(status, indent=2, default=str))
    finally:
        await engine.dispose()


async def _stop_employee(args: argparse.Namespace) -> None:
    """Stop a running employee."""
    session_factory, engine = _get_session_factory()
    manager = get_employee_manager()

    try:
        async with session_factory() as session:
            status = await manager.stop_employee(
                employee_id=args.employee_id,
                session=session,
            )
        print(json.dumps(status, indent=2, default=str))
    finally:
        await engine.dispose()


async def _status_employee(args: argparse.Namespace) -> None:
    """Get employee runtime status.

    Queries the DB for persisted status and probes the health endpoint
    to determine if the employee subprocess is actually reachable.
    """
    session_factory, engine = _get_session_factory()

    try:
        from sqlalchemy import select

        from empla.models.employee import Employee as EmployeeModel

        async with session_factory() as session:
            result = await session.execute(
                select(EmployeeModel).where(
                    EmployeeModel.id == args.employee_id,
                    EmployeeModel.tenant_id == args.tenant_id,
                )
            )
            db_employee = result.scalar_one_or_none()

        if db_employee is None:
            print(json.dumps({"error": f"Employee {args.employee_id} not found"}, indent=2))
            return

        status: dict[str, Any] = {
            "id": str(db_employee.id),
            "name": db_employee.name,
            "role": db_employee.role,
            "db_status": db_employee.status,
            "is_running": db_employee.status == "active",
            "is_paused": db_employee.status == "paused",
        }

        # Probe health endpoint if manager knows the port
        import httpx

        manager = get_employee_manager()
        port = manager.get_health_port(args.employee_id)
        if port is not None:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"http://127.0.0.1:{port}/health", timeout=3.0)
                    if resp.status_code == 200:
                        status["health"] = resp.json()
            except Exception as exc:
                logger.debug("Health probe failed for port %s: %s", port, exc, exc_info=True)

        print(json.dumps(status, indent=2, default=str))
    finally:
        await engine.dispose()


async def _list_employees(_args: argparse.Namespace) -> None:
    """List running employees (active and paused) from the database."""
    session_factory, engine = _get_session_factory()

    try:
        from sqlalchemy import select

        from empla.models.employee import Employee as EmployeeModel

        async with session_factory() as session:
            result = await session.execute(
                select(EmployeeModel).where(EmployeeModel.status.in_(["active", "paused"]))
            )
            employees = result.scalars().all()

        if not employees:
            print("No running employees.")
            return

        for emp in employees:
            print(f"  {emp.id}  name={emp.name}  role={emp.role}  status={emp.status}")
    finally:
        await engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="empla",
        description="empla - Production-Ready Digital Employees",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── employee command group ──
    emp_parser = subparsers.add_parser("employee", help="Manage digital employees")
    emp_sub = emp_parser.add_subparsers(dest="action", help="Employee actions")

    # start
    start_p = emp_sub.add_parser("start", help="Start an employee")
    start_p.add_argument("employee_id", type=UUID, help="Employee UUID")
    start_p.add_argument("--tenant-id", type=UUID, required=True, help="Tenant UUID")
    start_p.set_defaults(func=_start_employee)

    # stop
    stop_p = emp_sub.add_parser("stop", help="Stop a running employee")
    stop_p.add_argument("employee_id", type=UUID, help="Employee UUID")
    stop_p.add_argument("--tenant-id", type=UUID, required=True, help="Tenant UUID")
    stop_p.set_defaults(func=_stop_employee)

    # status
    status_p = emp_sub.add_parser("status", help="Get employee status")
    status_p.add_argument("employee_id", type=UUID, help="Employee UUID")
    status_p.add_argument("--tenant-id", type=UUID, required=True, help="Tenant UUID")
    status_p.set_defaults(func=_status_employee)

    # list
    list_p = emp_sub.add_parser("list", help="List active employees")
    list_p.set_defaults(func=_list_employees)

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
