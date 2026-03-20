"""Tests for integration health monitoring."""

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest

from empla.core.tools.base import Tool
from empla.core.tools.health import IntegrationHealth, IntegrationHealthMonitor
from empla.core.tools.registry import ToolRegistry
from empla.core.tools.router import ToolRouter

# ============================================================================
# Unit tests for IntegrationHealthMonitor
# ============================================================================


class TestIntegrationHealth:
    def test_initial_state(self) -> None:
        h = IntegrationHealth(name="hubspot")
        assert h.status == "unknown"
        assert h.total_calls == 0
        assert h.error_rate == 0.0
        assert h.avg_latency_ms == 0.0

    def test_healthy_after_successes(self) -> None:
        h = IntegrationHealth(name="hubspot", success_count=10, total_duration_ms=1500.0)
        assert h.status == "healthy"
        assert h.error_rate == 0.0
        assert h.avg_latency_ms == 150.0

    def test_degraded_on_error_rate(self) -> None:
        """20% error rate (failures, no timeouts) → degraded."""
        h = IntegrationHealth(
            name="hubspot", success_count=8, failure_count=2, total_duration_ms=5000.0
        )
        assert h.status == "degraded"
        assert h.error_rate == 0.2

    def test_degraded_on_timeout_rate(self) -> None:
        """Timeout rate > 5% → degraded (even if overall error rate < 20%)."""
        h = IntegrationHealth(
            name="hubspot", success_count=9, timeout_count=1, total_duration_ms=5000.0
        )
        assert h.status == "degraded"
        assert h.timeout_rate == 0.1

    def test_healthy_with_rare_timeout(self) -> None:
        """Single timeout in 100 calls (1% timeout rate) → still healthy."""
        h = IntegrationHealth(
            name="hubspot", success_count=99, timeout_count=1, total_duration_ms=10000.0
        )
        assert h.status == "healthy"

    def test_down_on_high_error_rate(self) -> None:
        h = IntegrationHealth(
            name="hubspot", success_count=2, failure_count=8, total_duration_ms=1000.0
        )
        assert h.status == "down"
        assert h.error_rate == 0.8

    def test_boundary_exactly_50_percent_is_degraded(self) -> None:
        """Exactly 50% error rate → degraded (not down, which requires >50%)."""
        h = IntegrationHealth(name="x", success_count=5, failure_count=5)
        assert h.status == "degraded"

    def test_boundary_just_under_20_percent_is_healthy(self) -> None:
        """19% error rate → healthy."""
        h = IntegrationHealth(name="x", success_count=81, failure_count=19)
        assert h.status == "healthy"

    def test_to_dict(self) -> None:
        h = IntegrationHealth(
            name="hubspot", success_count=5, failure_count=1, total_duration_ms=600.0
        )
        d = h.to_dict()
        assert d["name"] == "hubspot"
        assert d["status"] == "healthy"
        assert d["total_calls"] == 6
        assert d["avg_latency_ms"] == 100.0


class TestHealthMonitor:
    def test_record_success(self) -> None:
        monitor = IntegrationHealthMonitor()
        monitor.record("hubspot", success=True, duration_ms=150.0)
        status = monitor.get_status("hubspot")
        assert status["status"] == "healthy"
        assert status["success_count"] == 1

    def test_record_failure(self) -> None:
        monitor = IntegrationHealthMonitor()
        monitor.record("hubspot", success=False, duration_ms=50.0, error="HTTP 500")
        status = monitor.get_status("hubspot")
        assert status["failure_count"] == 1
        assert status["last_error"] == "HTTP 500"

    def test_record_timeout(self) -> None:
        monitor = IntegrationHealthMonitor()
        monitor.record(
            "hubspot", success=False, duration_ms=30000.0, error="timeout", is_timeout=True
        )
        status = monitor.get_status("hubspot")
        assert status["timeout_count"] == 1

    def test_unknown_integration(self) -> None:
        monitor = IntegrationHealthMonitor()
        status = monitor.get_status("nonexistent")
        assert status["status"] == "unknown"

    def test_get_all_status(self) -> None:
        monitor = IntegrationHealthMonitor()
        monitor.record("hubspot", success=True, duration_ms=100.0)
        monitor.record("google_calendar", success=True, duration_ms=200.0)
        all_status = monitor.get_all_status()
        assert len(all_status) == 2
        names = {s["name"] for s in all_status}
        assert names == {"hubspot", "google_calendar"}

    def test_beliefs_for_degraded(self) -> None:
        monitor = IntegrationHealthMonitor()
        for _ in range(7):
            monitor.record("hubspot", success=True, duration_ms=100.0)
        for _ in range(3):
            monitor.record("hubspot", success=False, duration_ms=100.0, error="HTTP 429")
        # 7 success + 3 fail = 30% error rate → degraded (clearly above 20%)
        beliefs = monitor.get_beliefs()
        assert len(beliefs) == 1
        assert beliefs[0]["subject"] == "hubspot"
        assert beliefs[0]["predicate"] == "availability"
        assert beliefs[0]["belief_object"]["status"] == "degraded"

    def test_beliefs_for_down(self) -> None:
        monitor = IntegrationHealthMonitor()
        for _ in range(8):
            monitor.record("hubspot", success=False, duration_ms=50.0, error="HTTP 500")
        monitor.record("hubspot", success=True, duration_ms=100.0)
        # 8 fail + 1 success = 88% error rate → down
        beliefs = monitor.get_beliefs()
        assert len(beliefs) == 1
        assert beliefs[0]["belief_object"]["status"] == "down"

    def test_no_beliefs_when_healthy(self) -> None:
        monitor = IntegrationHealthMonitor()
        for _ in range(10):
            monitor.record("hubspot", success=True, duration_ms=100.0)
        beliefs = monitor.get_beliefs()
        assert beliefs == []

    def test_reset(self) -> None:
        monitor = IntegrationHealthMonitor()
        monitor.record("hubspot", success=True, duration_ms=100.0)
        monitor.reset()
        assert monitor.get_all_status() == []


# ============================================================================
# Integration test: ToolRouter records health
# ============================================================================


class FastTool:
    async def _execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}


class FailingTool:
    async def _execute(self, params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("API error")


class SlowTool:
    async def _execute(self, params: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(10)
        return {"ok": True}


@pytest.fixture
def employee_id() -> UUID:
    return uuid4()


@pytest.fixture
def router_with_tools() -> ToolRouter:
    registry = ToolRegistry()
    fast = Tool(name="hubspot.get_deals", description="Get deals", parameters_schema={})
    registry.register_tool(fast, FastTool())
    fail = Tool(name="hubspot.broken", description="Broken", parameters_schema={})
    registry.register_tool(fail, FailingTool())
    slow = Tool(name="calendar.slow", description="Slow", parameters_schema={})
    registry.register_tool(slow, SlowTool())
    return ToolRouter(tool_registry=registry, tool_timeout=0.1)


class TestToolRouterHealthIntegration:
    @pytest.mark.asyncio
    async def test_successful_call_records_health(
        self, router_with_tools: ToolRouter, employee_id: UUID
    ) -> None:
        await router_with_tools.execute_tool_call(employee_id, "hubspot.get_deals", {})
        health = router_with_tools.get_integration_health("hubspot")
        assert health["success_count"] == 1
        assert health["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_failed_call_records_health(
        self, router_with_tools: ToolRouter, employee_id: UUID
    ) -> None:
        await router_with_tools.execute_tool_call(employee_id, "hubspot.broken", {})
        health = router_with_tools.get_integration_health("hubspot")
        assert health["failure_count"] == 1

    @pytest.mark.asyncio
    async def test_timeout_records_health(
        self, router_with_tools: ToolRouter, employee_id: UUID
    ) -> None:
        await router_with_tools.execute_tool_call(employee_id, "calendar.slow", {})
        health = router_with_tools.get_integration_health("calendar")
        assert health["timeout_count"] == 1
        assert health["status"] == "down"  # 1 timeout, 0 success = 100% error rate

    @pytest.mark.asyncio
    async def test_health_beliefs_after_failures(
        self, router_with_tools: ToolRouter, employee_id: UUID
    ) -> None:
        # Generate enough failures for "down" status
        for _ in range(6):
            await router_with_tools.execute_tool_call(employee_id, "hubspot.broken", {})
        beliefs = router_with_tools.get_health_beliefs()
        assert len(beliefs) >= 1
        hubspot_belief = next(b for b in beliefs if b["subject"] == "hubspot")
        assert hubspot_belief["belief_object"]["status"] == "down"

    def test_get_all_integration_health(self, router_with_tools: ToolRouter) -> None:
        all_health = router_with_tools.get_all_integration_health()
        assert isinstance(all_health, list)
