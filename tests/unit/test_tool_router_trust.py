"""Tests for ToolRouter trust boundary and timeout integration."""

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest

from empla.core.tools.base import Tool
from empla.core.tools.registry import ToolRegistry
from empla.core.tools.router import ToolRouter
from empla.core.tools.trust import TrustBoundary


class SlowTool:
    """Tool that takes longer than timeout."""

    async def _execute(self, params: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(10)
        return {"result": "should not reach"}


class FastTool:
    """Tool that returns immediately."""

    async def _execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"result": "ok", "echo": params.get("input", "")}


class FailingTool:
    """Tool that raises an exception."""

    async def _execute(self, params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("tool exploded")


@pytest.fixture
def employee_id() -> UUID:
    return uuid4()


@pytest.fixture
def registry_with_tools() -> ToolRegistry:
    """Registry with fast, slow, and failing tools."""
    registry = ToolRegistry()

    fast = Tool(name="crm.get_deals", description="Get deals", parameters_schema={})
    registry.register_tool(fast, FastTool())

    slow = Tool(name="crm.slow_query", description="Slow query", parameters_schema={})
    registry.register_tool(slow, SlowTool())

    fail = Tool(name="crm.broken", description="Broken tool", parameters_schema={})
    registry.register_tool(fail, FailingTool())

    denied = Tool(name="hubspot.delete_all_deals", description="Delete all", parameters_schema={})
    registry.register_tool(denied, FastTool())

    return registry


class TestTrustBoundaryIntegration:
    @pytest.mark.asyncio
    async def test_allowed_tool_executes(
        self, registry_with_tools: ToolRegistry, employee_id: UUID
    ) -> None:
        router = ToolRouter(tool_registry=registry_with_tools)
        result = await router.execute_tool_call(employee_id, "crm.get_deals", {"input": "test"})
        assert result.success
        assert result.output["echo"] == "test"

    @pytest.mark.asyncio
    async def test_denied_tool_returns_error(
        self, registry_with_tools: ToolRegistry, employee_id: UUID
    ) -> None:
        router = ToolRouter(tool_registry=registry_with_tools)
        result = await router.execute_tool_call(employee_id, "hubspot.delete_all_deals", {})
        assert not result.success
        assert "Trust boundary denied" in result.error
        assert result.metadata.get("trust_denied") is True

    @pytest.mark.asyncio
    async def test_role_denied_after_taint(
        self, registry_with_tools: ToolRegistry, employee_id: UUID
    ) -> None:
        """Role restrictions only activate after reading untrusted content."""
        router = ToolRouter(tool_registry=registry_with_tools)
        admin_tool = Tool(name="admin.config", description="Config", parameters_schema={})
        registry_with_tools.register_tool(admin_tool, FastTool())
        # email. prefix is high-risk → taints context
        email_tool = Tool(
            name="email.get_unread_emails", description="Read email", parameters_schema={}
        )
        registry_with_tools.register_tool(email_tool, FastTool())

        # Before taint: admin allowed (role checks inactive)
        result = await router.execute_tool_call(
            employee_id, "admin.config", {}, employee_role="sales_ae"
        )
        assert result.success

        # Read email → taints context
        await router.execute_tool_call(employee_id, "email.get_unread_emails", {})

        # After taint: admin blocked for sales_ae
        result = await router.execute_tool_call(
            employee_id, "admin.config", {}, employee_role="sales_ae"
        )
        assert not result.success
        assert "Trust boundary denied" in result.error

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(
        self, registry_with_tools: ToolRegistry, employee_id: UUID
    ) -> None:
        router = ToolRouter(tool_registry=registry_with_tools)
        result = await router.execute_tool_call(employee_id, "nonexistent.tool", {})
        assert not result.success
        assert "Unknown tool" in result.error


class TestTimeoutIntegration:
    @pytest.mark.asyncio
    async def test_slow_tool_times_out(
        self, registry_with_tools: ToolRegistry, employee_id: UUID
    ) -> None:
        router = ToolRouter(tool_registry=registry_with_tools, tool_timeout=0.1)
        result = await router.execute_tool_call(employee_id, "crm.slow_query", {})
        assert not result.success
        assert "timed out" in result.error
        assert result.metadata.get("timeout") is True

    @pytest.mark.asyncio
    async def test_fast_tool_within_timeout(
        self, registry_with_tools: ToolRegistry, employee_id: UUID
    ) -> None:
        router = ToolRouter(tool_registry=registry_with_tools, tool_timeout=5.0)
        result = await router.execute_tool_call(employee_id, "crm.get_deals", {})
        assert result.success
        assert "duration_ms" in result.metadata

    @pytest.mark.asyncio
    async def test_failing_tool_returns_error_not_timeout(
        self, registry_with_tools: ToolRegistry, employee_id: UUID
    ) -> None:
        router = ToolRouter(tool_registry=registry_with_tools, tool_timeout=5.0)
        result = await router.execute_tool_call(employee_id, "crm.broken", {})
        assert not result.success
        assert "RuntimeError" in result.error
        assert result.metadata.get("timeout") is not True


class TestTrustCycleReset:
    @pytest.mark.asyncio
    async def test_reset_allows_new_calls(
        self, registry_with_tools: ToolRegistry, employee_id: UUID
    ) -> None:
        boundary = TrustBoundary(max_calls_per_cycle=2)
        router = ToolRouter(tool_registry=registry_with_tools, trust_boundary=boundary)

        await router.execute_tool_call(employee_id, "crm.get_deals", {})
        await router.execute_tool_call(employee_id, "crm.get_deals", {})

        result = await router.execute_tool_call(employee_id, "crm.get_deals", {})
        assert not result.success

        router.reset_trust_cycle()
        result = await router.execute_tool_call(employee_id, "crm.get_deals", {})
        assert result.success

    def test_trust_stats(self, registry_with_tools: ToolRegistry, employee_id: UUID) -> None:
        router = ToolRouter(tool_registry=registry_with_tools)
        stats = router.get_trust_stats()
        assert "total_decisions" in stats
        assert "allowed" in stats
        assert "denied" in stats
