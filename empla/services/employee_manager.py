"""
empla.services.employee_manager - Employee Runtime Manager

Manages digital employee processes. Each employee runs as an independent
subprocess via ``python -m empla.runner``. The API server is the *control
plane* (lifecycle, routing, monitoring), NOT the execution plane.

Pause/resume is DB-only: the manager writes status to the DB and the
employee subprocess reads it each cycle (pause-via-DB pattern).
"""

import asyncio
import logging
import os
import secrets
import signal
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from empla.employees.registry import get_employee_class, get_supported_roles
from empla.models.employee import Employee as EmployeeModel

logger = logging.getLogger(__name__)

# Base port for employee health servers. Ports are allocated sequentially
# starting from this value (9100, 9101, 9102, ...). Ports are never
# reclaimed — monotonically increasing. Acceptable for the current
# process-per-container model where restarts are infrequent.
_HEALTH_PORT_BASE = 9100

# Timeout in seconds for subprocess graceful shutdown before SIGKILL.
_STOP_TIMEOUT_SECONDS = 30


class UnsupportedRoleError(ValueError):
    """Raised when attempting to start an employee with an unsupported role."""


class EmployeeManager:
    """
    Singleton manager for employee subprocesses.

    Lifecycle:
        start_employee  → spawns ``python -m empla.runner`` subprocess
        stop_employee   → sends SIGTERM, waits, SIGKILL if needed
        pause_employee  → writes status='paused' to DB (subprocess reads it)
        resume_employee → writes status='active' to DB
        get_status      → checks if subprocess is alive (local only)
    """

    _instance: "EmployeeManager | None" = None
    _lock: asyncio.Lock | None = None

    def __new__(cls) -> "EmployeeManager":
        """Ensure singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return

        # Subprocess tracking
        self._processes: dict[UUID, subprocess.Popen[bytes]] = {}
        self._health_ports: dict[UUID, int] = {}
        # Per-employee shared secret used as the X-Runner-Token header on
        # all non-/health requests to the runner subprocess. Generated at
        # spawn time and passed via env var to the runner. /health stays
        # unauthenticated so liveness probes work without a token.
        self._health_tokens: dict[UUID, str] = {}
        self._tenant_ids: dict[UUID, UUID] = {}
        self._next_health_port: int = _HEALTH_PORT_BASE

        # Error tracking (populated when we detect a process crashed)
        self._error_states: dict[UUID, str] = {}

        self._initialized = True
        logger.info("EmployeeManager initialized (subprocess backend)")

    async def _get_lock(self) -> asyncio.Lock:
        """Get or create the asyncio lock (deferred to avoid event-loop warnings).

        Safe without additional synchronization: no await between the None check
        and assignment, so the GIL guarantees atomicity. Do not add awaits here.
        """
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start_employee(
        self,
        employee_id: UUID,
        tenant_id: UUID,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """
        Start a digital employee as a subprocess.

        Validates the employee exists and has a supported role, spawns
        ``python -m empla.runner``, and updates DB status to ``active``.
        """
        async with await self._get_lock():
            # Check if already running
            if employee_id in self._processes:
                proc = self._processes[employee_id]
                if proc.poll() is None:
                    raise RuntimeError(f"Employee {employee_id} is already running")
                # Process exited — clean up stale entry
                self._processes.pop(employee_id, None)
                self._health_ports.pop(employee_id, None)
                self._health_tokens.pop(employee_id, None)
                self._tenant_ids.pop(employee_id, None)

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

            # Validate role
            employee_class = get_employee_class(db_employee.role)
            if employee_class is None:
                raise UnsupportedRoleError(
                    f"Unsupported role '{db_employee.role}'. "
                    f"Supported roles: {get_supported_roles()}"
                )

            # Allocate health port
            health_port = self._next_health_port
            self._next_health_port += 1

            # Generate per-runner shared secret for the X-Runner-Token header.
            # 256 bits of entropy via secrets.token_urlsafe(32).
            health_token = secrets.token_urlsafe(32)

            # Spawn subprocess. Pass the token via env (not argv) so it
            # doesn't show up in `ps`. Pass health port via argv so it's
            # easy to grep.
            cmd = [
                sys.executable,
                "-m",
                "empla.runner",
                "--employee-id",
                str(employee_id),
                "--tenant-id",
                str(tenant_id),
                "--health-port",
                str(health_port),
            ]

            logger.info(
                f"Spawning employee subprocess: {employee_id} on port {health_port}",
                extra={"employee_id": str(employee_id), "health_port": health_port},
            )

            spawn_env = {**os.environ, "EMPLA_RUNNER_TOKEN": health_token}
            proc = subprocess.Popen(  # noqa: ASYNC220 — intentionally blocking; Popen returns immediately
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=spawn_env,
            )

            self._processes[employee_id] = proc
            self._health_ports[employee_id] = health_port
            self._health_tokens[employee_id] = health_token
            self._tenant_ids[employee_id] = tenant_id
            self._error_states.pop(employee_id, None)

            # Update database status
            if db_employee.status != "active":
                db_employee.activated_at = datetime.now(UTC)
            db_employee.status = "active"
            try:
                await session.commit()
            except Exception:
                # Commit failed — kill orphaned subprocess and clean up tracking
                logger.error(
                    f"DB commit failed after spawning employee {employee_id} "
                    f"(pid={proc.pid}), terminating subprocess",
                    exc_info=True,
                    extra={"employee_id": str(employee_id), "pid": proc.pid},
                )
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                except (ProcessLookupError, OSError):
                    pass  # Already exited
                self._processes.pop(employee_id, None)
                self._health_ports.pop(employee_id, None)
                self._health_tokens.pop(employee_id, None)
                self._tenant_ids.pop(employee_id, None)
                raise

            logger.info(
                f"Employee {employee_id} subprocess started (pid={proc.pid})",
                extra={"employee_id": str(employee_id), "pid": proc.pid},
            )

            return self.get_status(employee_id)

    async def stop_employee(
        self,
        employee_id: UUID,
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """
        Stop a running employee subprocess.

        Sends SIGTERM for graceful shutdown, waits up to ``_STOP_TIMEOUT_SECONDS``,
        then sends SIGKILL if the process hasn't exited.
        """
        async with await self._get_lock():
            if employee_id not in self._processes:
                raise ValueError(f"Employee {employee_id} is not running")

            proc = self._processes[employee_id]
            # Capture tenant_id BEFORE get_status — _prune_dead_process
            # (called by get_status) removes _tenant_ids if process died.
            tid = self._tenant_ids.get(employee_id)
            status = self.get_status(employee_id)

            logger.info(
                f"Stopping employee {employee_id} (pid={proc.pid})",
                extra={"employee_id": str(employee_id)},
            )

            # Send SIGTERM for graceful shutdown
            if proc.poll() is None:
                try:
                    proc.send_signal(signal.SIGTERM)
                except (ProcessLookupError, OSError) as e:
                    logger.info(
                        f"Employee {employee_id} already exited when sending SIGTERM: {e}",
                        extra={"employee_id": str(employee_id)},
                    )

                # Wait for process to exit
                try:
                    await asyncio.get_running_loop().run_in_executor(
                        None,
                        proc.wait,
                        _STOP_TIMEOUT_SECONDS,
                    )
                except subprocess.TimeoutExpired:
                    logger.warning(
                        f"Employee {employee_id} did not stop within "
                        f"{_STOP_TIMEOUT_SECONDS}s, sending SIGKILL",
                        extra={"employee_id": str(employee_id)},
                    )
                    proc.kill()
                    try:
                        await asyncio.get_running_loop().run_in_executor(None, proc.wait, 5)
                    except subprocess.TimeoutExpired:
                        logger.critical(
                            f"Employee {employee_id} (pid={proc.pid}) did not exit "
                            "after SIGKILL — process may be a zombie",
                            extra={"employee_id": str(employee_id), "pid": proc.pid},
                        )

            # Clean up
            self._processes.pop(employee_id, None)
            self._health_ports.pop(employee_id, None)
            self._health_tokens.pop(employee_id, None)
            self._tenant_ids.pop(employee_id, None)
            self._error_states.pop(employee_id, None)

            # Update database if session provided
            if session is not None:
                if tid is None:
                    raise ValueError(
                        f"Employee {employee_id} has no tenant_id — cannot update DB safely"
                    )
                await session.execute(
                    update(EmployeeModel)
                    .where(
                        EmployeeModel.id == employee_id,
                        EmployeeModel.tenant_id == tid,
                    )
                    .values(status="stopped")
                )
                await session.commit()

            logger.info(f"Employee {employee_id} stopped")

            status["is_running"] = False
            return status

    async def pause_employee(
        self,
        employee_id: UUID,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """
        Pause a running employee by setting DB status to 'paused'.

        The subprocess reads its status from DB each cycle and will
        sleep-and-recheck when it sees 'paused'.
        """
        async with await self._get_lock():
            if employee_id not in self._processes:
                raise ValueError(f"Employee {employee_id} is not running")
            if self._processes[employee_id].poll() is not None:
                raise ValueError(f"Employee {employee_id} process has exited")

            tid = self._tenant_ids.get(employee_id)
            if tid is None:
                raise ValueError(
                    f"Employee {employee_id} has no tenant_id — cannot update DB safely"
                )

            await session.execute(
                update(EmployeeModel)
                .where(
                    EmployeeModel.id == employee_id,
                    EmployeeModel.tenant_id == tid,
                )
                .values(status="paused")
            )
            await session.commit()

            logger.info(f"Employee {employee_id} paused (DB status updated)")

            return self.get_status(employee_id)

    async def resume_employee(
        self,
        employee_id: UUID,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """
        Resume a paused employee by setting DB status to 'active'.
        """
        async with await self._get_lock():
            if employee_id not in self._processes:
                raise ValueError(f"Employee {employee_id} is not running")
            if self._processes[employee_id].poll() is not None:
                raise ValueError(f"Employee {employee_id} process has exited")

            tid = self._tenant_ids.get(employee_id)
            if tid is None:
                raise ValueError(
                    f"Employee {employee_id} has no tenant_id — cannot update DB safely"
                )

            await session.execute(
                update(EmployeeModel)
                .where(
                    EmployeeModel.id == employee_id,
                    EmployeeModel.tenant_id == tid,
                )
                .values(status="active")
            )
            await session.commit()

            logger.info(f"Employee {employee_id} resumed (DB status updated)")

            return self.get_status(employee_id)

    # =========================================================================
    # Status
    # =========================================================================

    def _prune_dead_process(self, employee_id: UUID) -> None:
        """Check if a tracked process has exited and clean up if so.

        Records non-zero exit codes in ``_error_states`` and removes
        the process from ``_processes``, ``_health_ports``, and
        ``_tenant_ids``.
        """
        if employee_id not in self._processes:
            return
        proc = self._processes[employee_id]
        if proc.poll() is None:
            return  # still alive
        returncode = proc.returncode
        if returncode != 0:
            self._error_states[employee_id] = f"Process exited with code {returncode}"
        self._processes.pop(employee_id, None)
        self._health_ports.pop(employee_id, None)
        self._health_tokens.pop(employee_id, None)
        self._tenant_ids.pop(employee_id, None)

    def get_status(self, employee_id: UUID) -> dict[str, Any]:
        """
        Get runtime status for an employee.

        Checks whether the subprocess is alive. Returns process metadata
        (pid, health_port) for live processes. Dead processes are pruned
        from internal tracking and their exit codes recorded in
        ``_error_states``. Use ``get_health()`` to poll the subprocess
        health endpoint.
        """
        # Prune dead process if tracked (records error state, cleans maps)
        self._prune_dead_process(employee_id)

        error_state = self._error_states.get(employee_id)

        if employee_id not in self._processes:
            return {
                "id": str(employee_id),
                "is_running": False,
                "is_paused": False,
                "has_error": error_state is not None,
                "last_error": error_state,
            }

        proc = self._processes[employee_id]
        return {
            "id": str(employee_id),
            "is_running": True,
            "is_paused": False,  # Pause state is in DB, not tracked here
            "has_error": False,
            "last_error": None,
            "pid": proc.pid,
            "health_port": self._health_ports.get(employee_id),
        }

    async def get_health(self, employee_id: UUID) -> dict[str, Any] | None:
        """
        Poll the health endpoint of an employee subprocess.

        Returns:
            Health data dict, or None if unreachable.
        """
        port = self._health_ports.get(employee_id)
        if port is None:
            return None

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"http://127.0.0.1:{port}/health",
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    return resp.json()  # type: ignore[no-any-return]
                logger.warning(
                    f"Health check returned {resp.status_code} for employee {employee_id}",
                    extra={"employee_id": str(employee_id), "status_code": resp.status_code},
                )
        except httpx.ConnectError:
            logger.warning(
                f"Health check connection refused for employee {employee_id} on port {port}",
                extra={"employee_id": str(employee_id), "health_port": port},
            )
        except httpx.TimeoutException:
            logger.warning(
                f"Health check timed out for employee {employee_id} on port {port}",
                extra={"employee_id": str(employee_id), "health_port": port},
            )
        except httpx.HTTPError:
            logger.warning(
                f"Health check failed for employee {employee_id} on port {port}",
                exc_info=True,
                extra={"employee_id": str(employee_id), "health_port": port},
            )
        return None

    async def wake_employee(self, employee_id: UUID, event: dict[str, Any]) -> bool:
        """Send a wake event to an employee subprocess.

        Posts the event payload to the subprocess health server's
        ``/wake`` endpoint, which stores the event and interrupts the
        inter-cycle sleep so the loop processes it immediately.

        Args:
            employee_id: Target employee UUID.
            event: Event dict with at least ``provider`` and ``event_type``.

        Returns:
            True if the wake was accepted, False if unreachable.
        """
        port = self._health_ports.get(employee_id)
        if port is None:
            logger.warning(
                f"Cannot wake employee {employee_id}: no health port registered",
                extra={"employee_id": str(employee_id)},
            )
            return False

        token = self._health_tokens.get(employee_id)
        headers = {"X-Runner-Token": token} if token else {}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"http://127.0.0.1:{port}/wake",
                    json=event,
                    headers=headers,
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    logger.info(
                        f"Wake event sent to employee {employee_id}",
                        extra={
                            "employee_id": str(employee_id),
                            "provider": event.get("provider"),
                            "event_type": event.get("event_type"),
                        },
                    )
                    return True
                logger.warning(
                    f"Wake request returned {resp.status_code} for employee {employee_id}",
                    extra={"employee_id": str(employee_id), "status_code": resp.status_code},
                )
        except httpx.ConnectError:
            logger.warning(
                f"Wake connection refused for employee {employee_id} on port {port}",
                extra={"employee_id": str(employee_id), "health_port": port},
            )
        except httpx.TimeoutException:
            logger.warning(
                f"Wake request timed out for employee {employee_id} on port {port}",
                extra={"employee_id": str(employee_id), "health_port": port},
            )
        except httpx.HTTPError:
            logger.warning(
                f"Wake request failed for employee {employee_id} on port {port}",
                exc_info=True,
                extra={"employee_id": str(employee_id), "health_port": port},
            )
        return False

    def list_running(self) -> list[UUID]:
        """Get list of running employee IDs."""
        # Prune dead processes (records error state, cleans internal maps)
        dead = [eid for eid, proc in self._processes.items() if proc.poll() is not None]
        for eid in dead:
            self._prune_dead_process(eid)
        return list(self._processes.keys())

    def is_running(self, employee_id: UUID) -> bool:
        """Check if an employee subprocess is currently alive."""
        if employee_id not in self._processes:
            return False
        return self._processes[employee_id].poll() is None

    def get_health_port(self, employee_id: UUID) -> int | None:
        """Get the health check port for a running employee."""
        return self._health_ports.get(employee_id)

    def get_health_token(self, employee_id: UUID) -> str | None:
        """Get the X-Runner-Token shared secret for a running employee.

        Returned to API proxies that need to call non-/health endpoints on
        the runner subprocess. Returns None if the employee is not tracked
        (process never spawned, already cleaned up).
        """
        return self._health_tokens.get(employee_id)

    async def restart_all_for_tenant(
        self,
        tenant_id: UUID,
        session: AsyncSession,
    ) -> int:
        """
        Stop + respawn every running employee owned by ``tenant_id`` so the
        new subprocess reads fresh ``Tenant.settings`` at startup.

        Used by the settings PUT endpoint (PR #83). The subprocess startup
        path is the only place tenant settings are read today (OAuth tokens,
        MCP servers, identity, and the module-level HubSpot ``_hubspot_init``
        all follow the same pattern), so a fresh spawn is the simplest and
        most reliable reload mechanism.

        Contract:
        - Employees currently tracked as running for this tenant are marked
          ``status='restarting'`` in the DB while the stop + spawn cycle
          runs, then flip back to ``'active'`` after the new subprocess
          registers. The intermediate state is visible to operators and
          gives the loop's status poll a clean signal.
        - Employees not tracked as running (already stopped, paused, or
          owned by a different tenant) are untouched.
        - Best-effort: individual failures are logged but don't abort the
          whole fan-out. The next manual start will pick up the new settings.

        Returns the number of employees that were marked for restart.
        """
        affected = [eid for eid, tid in list(self._tenant_ids.items()) if tid == tenant_id]
        if not affected:
            return 0

        # Mark restarting FIRST so the DB row reflects the transient state
        # even if the stop/start fan-out is slow or partially fails.
        await session.execute(
            update(EmployeeModel)
            .where(
                EmployeeModel.tenant_id == tenant_id,
                EmployeeModel.id.in_(affected),
                EmployeeModel.deleted_at.is_(None),
            )
            .values(status="restarting")
        )
        await session.commit()

        restarted = 0
        for eid in affected:
            stopped_ok = False
            try:
                # stop_employee with session=None skips the DB write, because
                # we already set status='restarting' above and start_employee
                # below will flip it back to 'active'.
                await self.stop_employee(eid, session=None)
                stopped_ok = True
                await self.start_employee(eid, tenant_id, session)
                restarted += 1
            except Exception:
                logger.warning(
                    "Failed to restart employee %s during tenant-wide settings reload",
                    eid,
                    exc_info=True,
                    extra={"employee_id": str(eid), "tenant_id": str(tenant_id)},
                )
                # Critical: don't leave the DB row stuck at 'restarting' with
                # no subprocess and no reaper. Revert to 'stopped' if we did
                # kill the process but couldn't respawn, or 'active' on pure
                # stop failure (since the old process is still around).
                recovery_status = "stopped" if stopped_ok else "active"
                try:
                    await session.execute(
                        update(EmployeeModel)
                        .where(
                            EmployeeModel.id == eid,
                            EmployeeModel.tenant_id == tenant_id,
                        )
                        .values(status=recovery_status)
                    )
                    await session.commit()
                except Exception:
                    logger.error(
                        "Employee %s stuck in status='restarting' — could not "
                        "write recovery status %s after respawn failure",
                        eid,
                        recovery_status,
                        exc_info=True,
                        extra={"employee_id": str(eid)},
                    )

        logger.info(
            "Tenant %s settings-triggered restart: %d of %d employees respawned",
            tenant_id,
            restarted,
            len(affected),
            extra={"tenant_id": str(tenant_id)},
        )
        return restarted

    async def stop_all(self, session: AsyncSession | None = None) -> dict[str, list[UUID]]:
        """
        Stop all running employees.

        Returns:
            Dictionary with 'stopped' and 'failed' lists of employee IDs.
        """
        employee_ids = list(self._processes.keys())
        stopped: list[UUID] = []
        failed: list[UUID] = []

        for employee_id in employee_ids:
            try:
                await self.stop_employee(employee_id, session)
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

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset the singleton (for testing only)."""
        cls._instance = None


def get_employee_manager() -> EmployeeManager:
    """Get the singleton EmployeeManager instance."""
    return EmployeeManager()
