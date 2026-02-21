"""
empla.runner.__main__ - CLI entry point for employee runner

Usage:
    python -m empla.runner --employee-id UUID --tenant-id UUID --health-port 9100
"""

import argparse
import asyncio
import logging
import sys
from uuid import UUID

from empla.runner.main import run_employee


def main() -> None:
    """Parse arguments and run the employee process."""
    parser = argparse.ArgumentParser(
        prog="empla-runner",
        description="Run a single empla digital employee as a persistent process",
    )
    parser.add_argument(
        "--employee-id",
        type=UUID,
        required=True,
        help="UUID of the employee to run",
    )
    parser.add_argument(
        "--tenant-id",
        type=UUID,
        required=True,
        help="UUID of the tenant",
    )
    parser.add_argument(
        "--health-port",
        type=int,
        default=9100,
        help="Port for the health check HTTP server (default: 9100)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    try:
        asyncio.run(
            run_employee(
                employee_id=args.employee_id,
                tenant_id=args.tenant_id,
                health_port=args.health_port,
            )
        )
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
