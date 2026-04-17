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
import os
import signal
import sys
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from empla.core.tools.mcp_bridge import MCPServerConfig
from empla.employees.config import EmployeeConfig, GoalConfig, LLMSettings, LoopSettings
from empla.employees.personality import Personality
from empla.employees.registry import get_employee_class
from empla.integrations.email.tools import router as email_router_template
from empla.models.database import get_engine, get_sessionmaker
from empla.models.employee import Employee as EmployeeModel
from empla.models.tenant import Tenant
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


async def _setup_dev_integrations(employee: Any) -> None:
    """Set up test integrations for --dev mode.

    Registers the email integration backed by the test email server.
    Uses the module-level email_router_template directly (tool functions
    are closures over it), so we initialize that router with the test adapter.

    Note: Safe to use module-level singleton because each employee runs in
    its own process via run_employee().
    """
    # Initialize the template router with test adapter — the tool functions
    # are closures over email_router_template.adapter, so this makes them work.
    base_url = os.getenv("EMPLA_TEST_EMAIL_URL", "http://localhost:9110")
    await email_router_template.initialize(
        {
            "provider": "test",
            "email_address": employee.email,
            "base_url": base_url,
        }
    )

    # Register on the employee's tool router
    if employee._tool_router is not None:
        employee._tool_router.register_integration(email_router_template)
        logger.info("Dev integrations registered: email (test)")


async def run_employee(
    employee_id: UUID,
    tenant_id: UUID,
    health_port: int,
    dev: bool = False,
) -> None:
    """
    Main entry point for running a single employee process.

    Args:
        employee_id: UUID of the employee to run
        tenant_id: UUID of the tenant
        health_port: Port for the health check HTTP server
        dev: If True, register test integrations (email via test adapter)
    """
    logger.info(
        f"Starting employee runner: employee={employee_id}, tenant={tenant_id}, "
        f"health_port={health_port}"
    )

    # Initialize database connection
    engine = get_engine()
    session_factory = get_sessionmaker(engine)

    # Load employee + tenant in one session. Tenant.settings are
    # captured at process start per PR #83's runner-restart pattern;
    # mid-process they're guaranteed stable because any settings change
    # triggers a full respawn.
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

        tenant_row = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
        )
        db_tenant = tenant_row.scalar_one_or_none()

    if db_employee is None:
        logger.error(f"Employee {employee_id} not found in tenant {tenant_id}")
        await engine.dispose()
        sys.exit(1)

    # Pull the cost hard-stop from Tenant.settings.cost.hard_stop_budget_usd.
    # Absent / malformed settings → None → feature disabled (matches
    # the schema default). Never raise: settings are operator-facing
    # and a bad row shouldn't kill the runner.
    cost_hard_stop_usd: float | None = None
    if db_tenant is not None and isinstance(db_tenant.settings, dict):
        try:
            cost_section = db_tenant.settings.get("cost") or {}
            if isinstance(cost_section, dict):
                raw = cost_section.get("hard_stop_budget_usd")
                # Python bool is a subclass of int — `isinstance(True, int)`
                # returns True. Without the explicit `not isinstance(raw, bool)`
                # guard, a settings value of `true` would silently enable a
                # $1/day cap. Filter bools out first.
                if isinstance(raw, int | float) and not isinstance(raw, bool) and raw > 0:
                    cost_hard_stop_usd = float(raw)
        except Exception:
            logger.warning(
                "Failed to parse Tenant.settings.cost; cost hard-stop disabled",
                extra={"tenant_id": str(tenant_id)},
                exc_info=True,
            )

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
            personality=Personality.from_dict(db_employee.personality)
            if db_employee.personality is not None
            else None,
            goals=goal_configs,
            role_description=db_config.get("role_description"),
            llm=LLMSettings(**(db_config.get("llm") or {})),
            loop=LoopSettings(**(db_config.get("loop") or {})),
            metadata=db_config.get("metadata") or {},
            cost_hard_stop_usd=cost_hard_stop_usd,
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

    # Load MCP server configs from DB
    mcp_configs: list[MCPServerConfig] = []
    creds: dict[str, dict[str, Any]] = {}
    try:
        from empla.services.integrations.mcp_service import MCPIntegrationService
        from empla.services.integrations.token_manager import get_token_manager

        async with session_factory() as mcp_session:
            tm = get_token_manager()
            mcp_service = MCPIntegrationService(mcp_session, tm)
            raw_configs = await mcp_service.get_active_mcp_servers(tenant_id)

            for cfg in raw_configs:
                try:
                    mcp_configs.append(MCPServerConfig(**cfg))
                except Exception:
                    logger.warning(
                        "Skipping invalid MCP server config: name=%s, keys=%s",
                        cfg.get("name", "<unnamed>"),
                        list(cfg.keys()),
                        exc_info=True,
                        extra={"employee_id": str(employee_id)},
                    )
            if mcp_configs:
                logger.info(
                    "Loaded %d MCP server(s) from DB: %s",
                    len(mcp_configs),
                    [c.name for c in mcp_configs],
                    extra={"employee_id": str(employee_id)},
                )
    except Exception:
        logger.error(
            "Failed to load MCP server configs — employee will have no integrations",
            exc_info=True,
            extra={"employee_id": str(employee_id)},
        )

    # Resolve OAuth credentials and inject into MCP server configs.
    # stdio servers get OAUTH_ACCESS_TOKEN in env; HTTP servers get Authorization header.
    try:
        from empla.services.integrations.credential_injector import CredentialInjector

        async with session_factory() as cred_session:
            tm = get_token_manager()
            injector = CredentialInjector(cred_session, tm)
            creds = await injector.get_credentials(employee_id, tenant_id)

            for mcp_cfg in mcp_configs:
                provider = mcp_cfg.env.get("OAUTH_PROVIDER")
                if provider and provider in creds:
                    token = creds[provider].get("access_token")
                    if token:
                        if mcp_cfg.transport == "http":
                            mcp_cfg.headers["Authorization"] = f"Bearer {token}"
                        else:
                            mcp_cfg.env["OAUTH_ACCESS_TOKEN"] = token
                        logger.debug(
                            "Injected OAuth token for MCP server '%s' (provider: %s, transport: %s)",
                            mcp_cfg.name,
                            provider,
                            mcp_cfg.transport,
                            extra={"employee_id": str(employee_id)},
                        )

            await cred_session.commit()
    except Exception:
        logger.error(
            "Failed to resolve OAuth credentials — MCP servers will start without tokens",
            exc_info=True,
            extra={"employee_id": str(employee_id)},
        )

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
            await employee.start(
                run_loop=False,
                status_checker=status_checker,
                mcp_configs=mcp_configs or None,
            )
            if dev:
                await _setup_dev_integrations(employee)

            # Wire health server → loop for event-driven wake triggers.
            # After start() the loop exists; set the health server reference
            # so the loop can drain events, and give the health server the
            # wake callback so POST /wake triggers an immediate cycle.
            if employee._loop is not None:
                employee._loop._health_server = health
                health._wake_callback = employee._loop.wake
            # Wire tool router for read-only /tools introspection (PR #80).
            # Without this the /tools endpoints return 503.
            if employee._tool_router is not None:
                health._tool_router = employee._tool_router

            await employee._run_loop()

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

        # Update DB status to "stopped" — but ONLY if we're currently
        # running. The cost hard-stop (and future restart/terminate
        # flows) set status='paused'/'restarting'/'terminated' inside
        # the loop as a durable signal to the supervisor and dashboard
        # ("employee is paused, admin must resume"). If we unconditionally
        # stamp 'stopped' here, a deploy or crash erases that signal and
        # the employee silently resumes at full spend on next start.
        try:
            async with session_factory() as session:
                result = await session.execute(
                    update(EmployeeModel)
                    .where(
                        EmployeeModel.id == employee_id,
                        EmployeeModel.tenant_id == tenant_id,
                        EmployeeModel.status.in_(("active", "running")),
                    )
                    .values(status="stopped")
                )
                await session.commit()
                if result.rowcount:
                    logger.info(f"Employee {employee_id} status set to 'stopped' in DB")
                else:
                    logger.info(
                        f"Employee {employee_id} shutdown: preserved non-running "
                        "status (paused/restarting/terminated) set during loop"
                    )
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
