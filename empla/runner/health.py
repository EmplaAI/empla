"""
empla.runner.health - Minimal Health Check Server

Raw asyncio HTTP server for employee health checks.
No external dependencies — uses asyncio.start_server with manual HTTP parsing.
"""

import asyncio
import contextlib
import json
import logging
import time
from uuid import UUID

logger = logging.getLogger(__name__)


class HealthServer:
    """Minimal HTTP health check server using raw asyncio."""

    def __init__(self, employee_id: UUID, port: int) -> None:
        self.employee_id = employee_id
        self.port = port
        self._start_time = time.monotonic()
        self._server: asyncio.Server | None = None
        self.cycle_count = 0  # TODO: wire to ProactiveExecutionLoop.cycle_count

    async def start(self) -> None:
        """Start the health server."""
        self._start_time = time.monotonic()
        self._server = await asyncio.start_server(self._handle_request, "127.0.0.1", self.port)
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

    async def _handle_request(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single HTTP request."""
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            request_str = request_line.decode("utf-8", errors="replace").strip()

            # Drain remaining headers (we don't need them)
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if line in {b"\r\n", b"\n"} or not line:
                    break

            if request_str.startswith("GET /health"):
                body = json.dumps(
                    {
                        "status": "ok",
                        "employee_id": str(self.employee_id),
                        "uptime_seconds": round(time.monotonic() - self._start_time, 1),
                        "cycle_count": self.cycle_count,
                    }
                )
                response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                    f"{body}"
                )
            else:
                body = '{"error": "not found"}'
                response = (
                    "HTTP/1.1 404 Not Found\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                    f"{body}"
                )

            writer.write(response.encode("utf-8"))
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
