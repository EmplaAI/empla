"""
Unit tests for empla.runner - Employee Process Runner

Tests the health server and runner components in isolation.
"""

import asyncio
import json
from uuid import uuid4

import pytest

from empla.runner.health import HealthServer

# ============================================================================
# Health Server Tests
# ============================================================================


@pytest.fixture
async def health_server():
    """Create and start a health server, clean up after test."""
    employee_id = uuid4()
    server = HealthServer(employee_id=employee_id, port=0)  # port 0 = OS picks
    # We'll use a specific port to avoid conflicts
    server.port = 19876
    await server.start()
    yield server
    await server.stop()


@pytest.mark.asyncio
async def test_health_server_starts_and_stops():
    """Test health server can start and stop cleanly."""
    server = HealthServer(employee_id=uuid4(), port=19877)
    await server.start()
    assert server._server is not None
    await server.stop()
    assert server._server is None


@pytest.mark.asyncio
async def test_health_endpoint_returns_json(health_server):
    """Test GET /health returns correct JSON response."""
    health_server.cycle_count = 42

    reader, writer = await asyncio.open_connection("127.0.0.1", health_server.port)
    writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
    await writer.drain()

    # Read response
    response = await asyncio.wait_for(reader.read(4096), timeout=5.0)
    writer.close()
    await writer.wait_closed()

    response_str = response.decode("utf-8")
    # Split headers from body
    parts = response_str.split("\r\n\r\n", 1)
    assert len(parts) == 2

    headers, body = parts
    assert "200 OK" in headers
    assert "application/json" in headers

    data = json.loads(body)
    assert data["status"] == "ok"
    assert data["employee_id"] == str(health_server.employee_id)
    assert data["cycle_count"] == 42
    assert "uptime_seconds" in data


@pytest.mark.asyncio
async def test_health_endpoint_404_for_unknown_path(health_server):
    """Test non-health paths return 404."""
    reader, writer = await asyncio.open_connection("127.0.0.1", health_server.port)
    writer.write(b"GET /unknown HTTP/1.1\r\nHost: localhost\r\n\r\n")
    await writer.drain()

    response = await asyncio.wait_for(reader.read(4096), timeout=5.0)
    writer.close()
    await writer.wait_closed()

    assert b"404 Not Found" in response


@pytest.mark.asyncio
async def test_health_server_tracks_uptime(health_server):
    """Test uptime_seconds increases over time."""
    await asyncio.sleep(0.1)

    reader, writer = await asyncio.open_connection("127.0.0.1", health_server.port)
    writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
    await writer.drain()

    response = await asyncio.wait_for(reader.read(4096), timeout=5.0)
    writer.close()
    await writer.wait_closed()

    body = response.decode("utf-8").split("\r\n\r\n", 1)[1]
    data = json.loads(body)
    assert data["uptime_seconds"] >= 0.1


# ============================================================================
# Runner __main__ Tests
# ============================================================================


def test_runner_module_is_importable():
    """Test that the runner module can be imported."""
    import empla.runner
    import empla.runner.__main__
    import empla.runner.health
    import empla.runner.main

    assert empla.runner is not None
    assert empla.runner.__main__ is not None
    assert empla.runner.health is not None
    assert empla.runner.main is not None


# ============================================================================
# Registry Tests (moved here since registry is needed by runner)
# ============================================================================


def test_get_employee_class_sales_ae():
    """Test registry resolves sales_ae role."""
    from empla.employees.registry import get_employee_class

    cls = get_employee_class("sales_ae")
    assert cls is not None
    assert cls.__name__ == "SalesAE"


def test_get_employee_class_csm():
    """Test registry resolves csm role."""
    from empla.employees.registry import get_employee_class

    cls = get_employee_class("csm")
    assert cls is not None
    assert cls.__name__ == "CustomerSuccessManager"


def test_get_employee_class_unknown_returns_none():
    """Test registry returns None for unknown roles."""
    from empla.employees.registry import get_employee_class

    assert get_employee_class("nonexistent_role") is None


def test_get_supported_roles():
    """Test get_supported_roles returns expected roles."""
    from empla.employees.registry import get_supported_roles

    roles = get_supported_roles()
    assert "sales_ae" in roles
    assert "csm" in roles
