"""
empla.cli - Command-Line Interface

Provides CLI commands for managing digital employees.

Usage:
    python -m empla.cli employee start <employee-id> --tenant-id UUID
    python -m empla.cli employee stop <employee-id>
    python -m empla.cli employee status <employee-id>
    python -m empla.cli employee list
"""

import argparse
import asyncio
import json
import sys
from uuid import UUID

from empla.services.employee_manager import get_employee_manager


def _get_session_factory() -> tuple:  # type: ignore[type-arg]
    """Create a DB session factory for CLI operations."""
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
    """Get employee runtime status."""
    manager = get_employee_manager()
    status = manager.get_status(args.employee_id)

    # Also try health endpoint if running
    if status.get("is_running"):
        health = await manager.get_health(args.employee_id)
        if health:
            status["health"] = health

    print(json.dumps(status, indent=2, default=str))


async def _list_employees(_args: argparse.Namespace) -> None:
    """List running employees."""
    manager = get_employee_manager()
    running = manager.list_running()

    if not running:
        print("No employees currently running.")
        return

    for eid in running:
        status = manager.get_status(eid)
        print(f"  {eid}  pid={status.get('pid', '?')}  port={status.get('health_port', '?')}")


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
    stop_p.set_defaults(func=_stop_employee)

    # status
    status_p = emp_sub.add_parser("status", help="Get employee status")
    status_p.add_argument("employee_id", type=UUID, help="Employee UUID")
    status_p.set_defaults(func=_status_employee)

    # list
    list_p = emp_sub.add_parser("list", help="List running employees")
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
