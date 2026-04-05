"""
empla.runner.health - Minimal Health + Wake Server

Raw asyncio HTTP server for employee health checks and external wake triggers.
No external dependencies — uses asyncio.start_server with manual HTTP parsing.

Endpoints:
  GET  /health  — health check (used by EmployeeManager.get_health)
  POST /wake    — wake the employee loop with an event payload
"""

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Callable
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

_MAX_PENDING_EVENTS = 100
_MAX_WAKE_BODY_BYTES = 65_536


class HealthServer:
    """Minimal HTTP server for health checks and wake triggers.

    The wake endpoint accepts event payloads from the API server
    (proxied via EmployeeManager) and stores them until the execution
    loop drains them at the start of the next cycle.
    """

    def __init__(
        self,
        employee_id: UUID,
        port: int,
        wake_callback: Callable[[], None] | None = None,
    ) -> None:
        self.employee_id = employee_id
        self.port = port
        self._start_time = time.monotonic()
        self._server: asyncio.Server | None = None
        self.cycle_count = 0  # TODO: wire to ProactiveExecutionLoop.cycle_count
        self._wake_callback = wake_callback
        self._pending_events: list[dict[str, Any]] = []

    async def start(self) -> None:
        """Start the health server."""
        self._start_time = time.monotonic()
        self._server = await asyncio.start_server(self._handle_request, "127.0.0.1", self.port)
        # Update port to actual bound port (useful when port=0 for ephemeral)
        sockets = self._server.sockets
        if sockets:
            self.port = sockets[0].getsockname()[1]
        logger.info(
            f"Health server listening on 127.0.0.1:{self.port}",
            extra={"employee_id": str(self.employee_id)},
        )

    async def stop(self) -> None:
        """Stop the health server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info(
                "Health server stopped",
                extra={"employee_id": str(self.employee_id)},
            )

    def drain_events(self) -> list[dict[str, Any]]:
        """Return and clear all pending events.

        Called by the execution loop early in each cycle to collect
        events that arrived since the last drain. Safe in single-threaded
        asyncio (no preemption between the swap and reassignment).
        """
        events = self._pending_events
        self._pending_events = []
        return events

    async def _handle_request(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single HTTP request."""
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            request_str = request_line.decode("utf-8", errors="replace").strip()

            # Parse headers — we need Content-Length for POST bodies
            content_length = 0
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if line in {b"\r\n", b"\n"} or not line:
                    break
                header_str = line.decode("utf-8", errors="replace").strip().lower()
                if header_str.startswith("content-length:"):
                    with contextlib.suppress(ValueError):
                        content_length = int(header_str.split(":", 1)[1].strip())

            if request_str.startswith("GET /health"):
                response_body, status_code = self._handle_health(), 200
            elif request_str.startswith("POST /wake"):
                response_body, status_code = await self._handle_wake(reader, content_length)
            else:
                response_body, status_code = '{"error": "not found"}', 404

            status_text = {
                200: "OK",
                400: "Bad Request",
                404: "Not Found",
                503: "Service Unavailable",
            }
            body_bytes = response_body.encode("utf-8")
            header = (
                f"HTTP/1.1 {status_code} {status_text.get(status_code, 'Error')}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body_bytes)}\r\n"
                "Connection: close\r\n"
                "\r\n"
            )

            writer.write(header.encode("utf-8") + body_bytes)
            await writer.drain()
        except TimeoutError:
            logger.debug(
                "Health server request timed out",
                extra={"employee_id": str(self.employee_id)},
            )
        except (ConnectionResetError, BrokenPipeError):
            logger.debug(
                "Health server client disconnected",
                extra={"employee_id": str(self.employee_id)},
            )
        except Exception:
            logger.warning(
                "Unexpected health server request error",
                exc_info=True,
                extra={"employee_id": str(self.employee_id)},
            )
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    def _handle_health(self) -> str:
        """Build health check response body."""
        return json.dumps(
            {
                "status": "ok",
                "employee_id": str(self.employee_id),
                "uptime_seconds": round(time.monotonic() - self._start_time, 1),
                "cycle_count": self.cycle_count,
                "pending_events": len(self._pending_events),
            }
        )

    async def _handle_wake(
        self, reader: asyncio.StreamReader, content_length: int
    ) -> tuple[str, int]:
        """Handle POST /wake — store event and trigger loop wake."""
        if content_length < 0 or content_length > _MAX_WAKE_BODY_BYTES:
            return '{"error": "invalid or oversized payload"}', 400

        raw = b""
        if content_length > 0:
            raw = await asyncio.wait_for(reader.read(content_length), timeout=5.0)

        try:
            event = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            return '{"error": "invalid JSON"}', 400

        if not isinstance(event, dict):
            return '{"error": "payload must be a JSON object"}', 400

        if len(self._pending_events) >= _MAX_PENDING_EVENTS:
            dropped = self._pending_events.pop(0)
            logger.warning(
                "Pending events queue full, dropping oldest event",
                extra={
                    "employee_id": str(self.employee_id),
                    "dropped_provider": dropped.get("provider", "unknown"),
                    "dropped_event_type": dropped.get("event_type", "unknown"),
                    "queue_size": _MAX_PENDING_EVENTS,
                },
            )

        self._pending_events.append(event)

        if self._wake_callback:
            try:
                self._wake_callback()
            except Exception:
                logger.warning(
                    "Wake callback failed, event stored but loop may not wake immediately",
                    exc_info=True,
                    extra={"employee_id": str(self.employee_id)},
                )

        logger.info(
            "Wake event received",
            extra={
                "employee_id": str(self.employee_id),
                "provider": event.get("provider", "unknown"),
                "event_type": event.get("event_type", "unknown"),
                "pending_count": len(self._pending_events),
            },
        )

        return json.dumps({"status": "accepted", "pending_events": len(self._pending_events)}), 200
