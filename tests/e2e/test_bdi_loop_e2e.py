"""
Full BDI Loop E2E tests — production code paths with real MCP servers.

Tests the complete production stack:
- MCPBridge connects to calendar/CRM test servers via stdio (proper MCP protocol)
- IntegrationRouter + TestEmailAdapter connects to email test server via HTTP
- ToolRouter merges all tools into a single interface
- ProactiveExecutionLoop uses ToolRouter for perception + execution

No database required. LLM tests are opt-in (skip when no API key).
"""

import asyncio
import contextlib
import json
import logging
import os
import sys
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
import uvicorn

from empla.core.loop.execution import ProactiveExecutionLoop
from empla.core.loop.models import LoopConfig
from empla.core.tools.mcp_bridge import MCPBridge, MCPServerConfig
from empla.core.tools.registry import ToolRegistry
from empla.core.tools.router import ToolRouter
from empla.integrations.email.tools import router as email_router_template
from empla.llm.models import LLMResponse, TokenUsage, ToolCall
from empla.models.employee import Employee

# Reusable mock token usage
_USAGE = TokenUsage(input_tokens=10, output_tokens=10, total_tokens=20)

logger = logging.getLogger(__name__)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def email_server_url():
    """Start test email server in-process, yield its URL."""
    from tests.servers.email_server import app, store

    store.reset()
    port = 9198  # Unique port to avoid conflict with other tests

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    # Poll until ready
    base_url = f"http://127.0.0.1:{port}"
    async with httpx.AsyncClient() as client:
        for _ in range(50):
            try:
                resp = await client.get(f"{base_url}/state", timeout=0.5)
                if resp.status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            await asyncio.sleep(0.1)
        else:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            pytest.fail("Test email server failed to start")

    yield base_url

    server.should_exit = True
    await asyncio.sleep(0.1)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.fixture
async def tool_router(email_server_url: str):
    """Create ToolRouter with real MCP + email connections, seed data."""
    registry = ToolRegistry()
    router = ToolRouter(tool_registry=registry)
    bridge = MCPBridge(registry)

    # Connect calendar via stdio MCP
    calendar_tools = await bridge.connect(
        MCPServerConfig(
            name="calendar",
            transport="stdio",
            command=[sys.executable, "-m", "tests.servers.calendar_mcp", "--mcp"],
        )
    )

    # Connect CRM via stdio MCP
    crm_tools = await bridge.connect(
        MCPServerConfig(
            name="crm",
            transport="stdio",
            command=[sys.executable, "-m", "tests.servers.crm_mcp", "--mcp"],
        )
    )

    # Connect email via IntegrationRouter + TestEmailAdapter
    await email_router_template.initialize(
        {
            "provider": "test",
            "email_address": "bot@test.empla.ai",
            "base_url": email_server_url,
        }
    )
    router.register_integration(email_router_template)

    # Seed data via MCP tools (CRM deals)
    employee_id = uuid4()
    await router.execute_tool_call(
        employee_id,
        "crm.mcp_create_deal",
        {"name": "AcmeCorp Enterprise", "value": 120000.0, "stage": "qualification"},
    )
    await router.execute_tool_call(
        employee_id,
        "crm.mcp_create_deal",
        {"name": "TechStart Growth", "value": 45000.0, "stage": "proposal"},
    )
    await router.execute_tool_call(
        employee_id,
        "crm.mcp_create_deal",
        {"name": "DataFlow Platform", "value": 15000.0, "stage": "prospecting"},
    )

    # Seed calendar event
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    await router.execute_tool_call(
        employee_id,
        "calendar.mcp_create_event",
        {
            "title": "Discovery Call with DataFlow",
            "start": (now + timedelta(hours=2)).isoformat(),
            "end": (now + timedelta(hours=2, minutes=30)).isoformat(),
        },
    )

    # Seed email via HTTP
    async with httpx.AsyncClient(base_url=email_server_url) as client:
        await client.post(
            "/scenario/load",
            json={
                "emails": [
                    {
                        "id": "email-e2e-001",
                        "from_addr": "sarah@acmecorp.com",
                        "to_addrs": ["bot@test.empla.ai"],
                        "subject": "Need demo ASAP",
                        "body": "We need a demo by Thursday. Budget approved for $200k.",
                        "timestamp": now.isoformat(),
                        "is_read": False,
                    },
                ]
            },
        )

    yield router, bridge, employee_id

    # Cleanup
    await bridge.disconnect_all()
    await email_router_template.shutdown()


def _make_mock_employee() -> Mock:
    """Create a mock Employee with required fields."""
    employee = Mock(spec=Employee)
    employee.id = uuid4()
    employee.tenant_id = uuid4()
    employee.name = "Test SalesAE"
    employee.role = "sales_ae"
    employee.status = "active"
    employee.email = "bot@test.empla.ai"
    return employee


def _make_mock_bdi() -> dict[str, Any]:
    """Create mock BDI components."""
    beliefs = Mock()
    beliefs.update_beliefs = AsyncMock(return_value=[])
    beliefs.get_all_beliefs = AsyncMock(return_value=[])
    beliefs.update_belief = AsyncMock()

    goals = Mock()
    goals.get_active_goals = AsyncMock(return_value=[])
    goals.get_pursuing_goals = AsyncMock(return_value=[])
    goals.update_goal_progress = AsyncMock()
    goals.complete_goal = AsyncMock()
    goals.get_goal = AsyncMock(return_value=None)
    goals.add_goal = AsyncMock()
    goals.abandon_goal = AsyncMock()
    goals.update_goal_priority = AsyncMock()
    goals.rollback = AsyncMock()

    intentions = Mock()
    intentions.get_next_intention = AsyncMock(return_value=None)
    intentions.get_intentions_for_goal = AsyncMock(return_value=[])
    intentions.generate_plan_for_goal = AsyncMock(return_value=[])

    memory = Mock()
    proc = Mock()
    proc.record_procedure = AsyncMock()
    proc.find_procedures_for_situation = AsyncMock(return_value=[])
    proc.reinforce_successful_procedures = AsyncMock()
    proc.archive_poor_procedures = AsyncMock()
    memory.procedural = proc

    ep = Mock()
    ep.record_episode = AsyncMock()
    ep.reinforce_frequently_recalled = AsyncMock(return_value=0)
    ep.decay_rarely_recalled = AsyncMock(return_value=0)
    memory.episodic = ep

    return {
        "beliefs": beliefs,
        "goals": goals,
        "intentions": intentions,
        "memory": memory,
    }


# ============================================================================
# Tests: Tool Discovery (no LLM needed)
# ============================================================================


class TestToolDiscovery:
    """Verify MCP bridge discovers and registers all tools."""

    @pytest.mark.asyncio
    async def test_calendar_tools_discovered(
        self, tool_router: tuple[ToolRouter, MCPBridge, Any]
    ) -> None:
        """Calendar MCP server tools are discovered via MCPBridge."""
        router, _, employee_id = tool_router
        schemas = router.get_all_tool_schemas(employee_id)
        tool_names = [s["name"] for s in schemas]

        assert "calendar.mcp_get_upcoming_events" in tool_names
        assert "calendar.mcp_create_event" in tool_names
        assert "calendar.mcp_list_events" in tool_names

    @pytest.mark.asyncio
    async def test_crm_tools_discovered(
        self, tool_router: tuple[ToolRouter, MCPBridge, Any]
    ) -> None:
        """CRM MCP server tools are discovered via MCPBridge."""
        router, _, employee_id = tool_router
        schemas = router.get_all_tool_schemas(employee_id)
        tool_names = [s["name"] for s in schemas]

        assert "crm.mcp_get_pipeline_metrics" in tool_names
        assert "crm.mcp_get_deals" in tool_names
        assert "crm.mcp_create_deal" in tool_names
        assert "crm.mcp_update_deal" in tool_names
        assert "crm.mcp_get_contacts" in tool_names
        assert "crm.mcp_add_contact" in tool_names
        assert "crm.mcp_get_at_risk_customers" in tool_names

    @pytest.mark.asyncio
    async def test_email_tools_discovered(
        self, tool_router: tuple[ToolRouter, MCPBridge, Any]
    ) -> None:
        """Email integration tools are registered via IntegrationRouter."""
        router, _, employee_id = tool_router
        schemas = router.get_all_tool_schemas(employee_id)
        tool_names = [s["name"] for s in schemas]

        assert "email.send_email" in tool_names
        assert "email.get_unread_emails" in tool_names

    @pytest.mark.asyncio
    async def test_all_integrations_present(
        self, tool_router: tuple[ToolRouter, MCPBridge, Any]
    ) -> None:
        """All 3 integrations registered: calendar + CRM (MCP) + email (IntegrationRouter)."""
        router, _bridge, employee_id = tool_router
        schemas = router.get_all_tool_schemas(employee_id)
        tool_names = [s["name"] for s in schemas]

        calendar_count = sum(1 for n in tool_names if n.startswith("calendar."))
        crm_count = sum(1 for n in tool_names if n.startswith("crm."))
        email_count = sum(1 for n in tool_names if n.startswith("email."))

        assert calendar_count == 3
        assert crm_count == 7
        assert email_count >= 5  # send, reply, forward, get_unread, mark_read, archive


# ============================================================================
# Tests: Tool Execution (no LLM needed)
# ============================================================================


class TestToolExecution:
    """Verify tools return real data through the full production stack."""

    @pytest.mark.asyncio
    async def test_crm_pipeline_metrics_return_seeded_data(
        self, tool_router: tuple[ToolRouter, MCPBridge, Any]
    ) -> None:
        """CRM pipeline metrics reflect seeded deals ($180k = 1.8x coverage)."""
        router, _, employee_id = tool_router
        result = await router.execute_tool_call(employee_id, "crm.mcp_get_pipeline_metrics", {})
        assert result.success is True
        # Output is a JSON string from the MCP server
        data = json.loads(result.output)
        assert data["coverage"] == 1.8
        assert data["total_value"] == 180000.0
        assert data["deal_count"] == 3

    @pytest.mark.asyncio
    async def test_calendar_upcoming_events(
        self, tool_router: tuple[ToolRouter, MCPBridge, Any]
    ) -> None:
        """Calendar returns the seeded upcoming event."""
        router, _, employee_id = tool_router
        result = await router.execute_tool_call(
            employee_id, "calendar.mcp_get_upcoming_events", {"hours": 24}
        )
        assert result.success is True
        data = json.loads(result.output)
        assert len(data) >= 1
        assert any("DataFlow" in e["title"] for e in data)

    @pytest.mark.asyncio
    async def test_email_get_unread(self, tool_router: tuple[ToolRouter, MCPBridge, Any]) -> None:
        """Email returns seeded unread email."""
        router, _, employee_id = tool_router
        result = await router.execute_tool_call(
            employee_id, "email.get_unread_emails", {"max_results": 10}
        )
        assert result.success is True
        assert isinstance(result.output, list)
        assert len(result.output) >= 1
        assert any("demo" in e["subject"].lower() for e in result.output)

    @pytest.mark.asyncio
    async def test_crm_create_and_get_deal(
        self, tool_router: tuple[ToolRouter, MCPBridge, Any]
    ) -> None:
        """Create a deal via CRM MCP then verify it appears in get_deals."""
        router, _, employee_id = tool_router

        # Create
        create_result = await router.execute_tool_call(
            employee_id,
            "crm.mcp_create_deal",
            {"name": "NewCo", "value": 50000.0, "stage": "prospecting"},
        )
        assert create_result.success is True
        deal = json.loads(create_result.output)
        assert deal["name"] == "NewCo"

        # Verify it shows up
        deals_result = await router.execute_tool_call(employee_id, "crm.mcp_get_deals", {})
        assert deals_result.success is True
        deals = json.loads(deals_result.output)
        assert any(d["name"] == "NewCo" for d in deals)

    @pytest.mark.asyncio
    async def test_email_send(self, tool_router: tuple[ToolRouter, MCPBridge, Any]) -> None:
        """Send email via IntegrationRouter → TestEmailAdapter → test server."""
        router, _, employee_id = tool_router
        result = await router.execute_tool_call(
            employee_id,
            "email.send_email",
            {"to": ["user@example.com"], "subject": "Test E2E", "body": "Hello from E2E"},
        )
        assert result.success is True
        assert result.output["success"] is True


# ============================================================================
# Tests: Perception with real tools (mock LLM)
# ============================================================================


class TestPerceptionWithRealTools:
    """Test agentic perception with mock LLM + real tool execution."""

    @pytest.mark.asyncio
    async def test_perception_calls_tools_and_creates_observations(
        self, tool_router: tuple[ToolRouter, MCPBridge, Any]
    ) -> None:
        """Mock LLM returns tool calls → real tools execute → observations created."""
        router, _, _ = tool_router
        employee = _make_mock_employee()
        bdi = _make_mock_bdi()

        # Mock LLM: first call returns CRM tool call, second call returns no tools (done)
        mock_llm = Mock()
        call_count = 0

        async def mock_generate_with_tools(**kwargs: Any) -> LLMResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    content="Let me check the pipeline.",
                    model="mock",
                    usage=_USAGE,
                    finish_reason="tool_calls",
                    tool_calls=[
                        ToolCall(
                            id="tc-1",
                            name="crm.mcp_get_pipeline_metrics",
                            arguments={},
                        )
                    ],
                )
            return LLMResponse(
                content="Pipeline is at 1.8x, below target.",
                model="mock",
                usage=_USAGE,
                finish_reason="stop",
                tool_calls=[],
            )

        mock_llm.generate_with_tools = mock_generate_with_tools

        loop = ProactiveExecutionLoop(
            employee=employee,
            beliefs=bdi["beliefs"],
            goals=bdi["goals"],
            intentions=bdi["intentions"],
            memory=bdi["memory"],
            llm_service=mock_llm,
            config=LoopConfig(cycle_interval_seconds=1),
            tool_router=router,
        )

        tool_schemas = router.get_all_tool_schemas(employee.id)
        result = await loop._perceive_agentic(tool_schemas)

        assert len(result.observations) >= 1
        crm_obs = [o for o in result.observations if o.source == "crm"]
        assert len(crm_obs) >= 1
        assert "crm" in result.sources_checked

        # Verify the observation contains real tool data
        tool_result = crm_obs[0].content.get("tool_result")
        assert tool_result is not None
        # The output is a JSON string from MCP
        data = json.loads(tool_result)
        assert data["coverage"] == 1.8

    @pytest.mark.asyncio
    async def test_perception_multiple_tool_calls(
        self, tool_router: tuple[ToolRouter, MCPBridge, Any]
    ) -> None:
        """LLM calls multiple tools across iterations."""
        router, _, _ = tool_router
        employee = _make_mock_employee()
        bdi = _make_mock_bdi()

        call_count = 0

        async def mock_generate(**kwargs: Any) -> LLMResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    content="Checking CRM",
                    model="mock",
                    usage=_USAGE,
                    finish_reason="tool_calls",
                    tool_calls=[
                        ToolCall(id="tc-1", name="crm.mcp_get_pipeline_metrics", arguments={}),
                    ],
                )
            if call_count == 2:
                return LLMResponse(
                    content="Now checking email",
                    model="mock",
                    usage=_USAGE,
                    finish_reason="tool_calls",
                    tool_calls=[
                        ToolCall(
                            id="tc-2",
                            name="email.get_unread_emails",
                            arguments={"max_results": 5},
                        ),
                    ],
                )
            return LLMResponse(
                content="Done checking.",
                model="mock",
                usage=_USAGE,
                finish_reason="stop",
                tool_calls=[],
            )

        mock_llm = Mock()
        mock_llm.generate_with_tools = mock_generate

        loop = ProactiveExecutionLoop(
            employee=employee,
            beliefs=bdi["beliefs"],
            goals=bdi["goals"],
            intentions=bdi["intentions"],
            memory=bdi["memory"],
            llm_service=mock_llm,
            config=LoopConfig(cycle_interval_seconds=1),
            tool_router=router,
        )

        tool_schemas = router.get_all_tool_schemas(employee.id)
        result = await loop._perceive_agentic(tool_schemas)

        assert len(result.observations) >= 2
        assert "crm" in result.sources_checked
        assert "email" in result.sources_checked


# ============================================================================
# Tests: Intention execution with real tools (mock LLM)
# ============================================================================


class TestIntentionExecutionWithRealTools:
    """Test intention execution with mock LLM + real tool execution."""

    @pytest.mark.asyncio
    async def test_sends_email_via_tool(
        self, tool_router: tuple[ToolRouter, MCPBridge, Any]
    ) -> None:
        """LLM decides to send email → real email sent via test server."""
        router, _, _ = tool_router
        employee = _make_mock_employee()
        bdi = _make_mock_bdi()

        call_count = 0

        async def mock_generate(**kwargs: Any) -> LLMResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    content="Sending follow-up email.",
                    model="mock",
                    usage=_USAGE,
                    finish_reason="tool_calls",
                    tool_calls=[
                        ToolCall(
                            id="tc-send",
                            name="email.send_email",
                            arguments={
                                "to": ["sarah@acmecorp.com"],
                                "subject": "Demo Scheduling",
                                "body": "Hi Sarah, happy to schedule a demo this week.",
                            },
                        )
                    ],
                )
            return LLMResponse(
                content="Email sent successfully.",
                model="mock",
                usage=_USAGE,
                finish_reason="stop",
                tool_calls=[],
            )

        mock_llm = Mock()
        mock_llm.generate_with_tools = mock_generate

        loop = ProactiveExecutionLoop(
            employee=employee,
            beliefs=bdi["beliefs"],
            goals=bdi["goals"],
            intentions=bdi["intentions"],
            memory=bdi["memory"],
            llm_service=mock_llm,
            config=LoopConfig(cycle_interval_seconds=1),
            tool_router=router,
        )

        # Create mock intention
        intention = Mock()
        intention.id = uuid4()
        intention.description = "Send follow-up email to AcmeCorp about demo"
        intention.goal_id = uuid4()
        intention.priority = 8

        tool_schemas = router.get_all_tool_schemas(employee.id)
        result = await loop._execute_intention_with_tools(intention, tool_schemas)

        assert result["success"] is True
        assert "email.send_email" in result["tools_used"]

    @pytest.mark.asyncio
    async def test_creates_deal_via_crm(
        self, tool_router: tuple[ToolRouter, MCPBridge, Any]
    ) -> None:
        """LLM creates a new CRM deal → verified via get_deals."""
        from empla.llm.models import LLMResponse, ToolCall

        router, _, employee_id = tool_router
        employee = _make_mock_employee()
        bdi = _make_mock_bdi()

        call_count = 0

        async def mock_generate(**kwargs: Any) -> LLMResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    content="Creating deal for BigCo.",
                    model="mock",
                    usage=_USAGE,
                    finish_reason="tool_calls",
                    tool_calls=[
                        ToolCall(
                            id="tc-deal",
                            name="crm.mcp_create_deal",
                            arguments={
                                "name": "BigCo Enterprise",
                                "value": 250000.0,
                                "stage": "qualification",
                            },
                        )
                    ],
                )
            return LLMResponse(
                content="Deal created.",
                model="mock",
                usage=_USAGE,
                finish_reason="stop",
                tool_calls=[],
            )

        mock_llm = Mock()
        mock_llm.generate_with_tools = mock_generate

        loop = ProactiveExecutionLoop(
            employee=employee,
            beliefs=bdi["beliefs"],
            goals=bdi["goals"],
            intentions=bdi["intentions"],
            memory=bdi["memory"],
            llm_service=mock_llm,
            config=LoopConfig(cycle_interval_seconds=1),
            tool_router=router,
        )

        intention = Mock()
        intention.id = uuid4()
        intention.description = "Create deal for BigCo"
        intention.goal_id = uuid4()
        intention.priority = 7

        tool_schemas = router.get_all_tool_schemas(employee.id)
        result = await loop._execute_intention_with_tools(intention, tool_schemas)

        assert result["success"] is True
        assert "crm.mcp_create_deal" in result["tools_used"]

        # Verify deal exists in CRM via direct tool call
        deals_result = await router.execute_tool_call(employee_id, "crm.mcp_get_deals", {})
        deals = json.loads(deals_result.output)
        assert any(d["name"] == "BigCo Enterprise" for d in deals)


# ============================================================================
# Tests: Full BDI cycle with mock LLM
# ============================================================================


class TestFullBDICycleWithMockLLM:
    """Test a complete BDI cycle with all phases."""

    @pytest.mark.asyncio
    async def test_full_cycle_no_errors(
        self, tool_router: tuple[ToolRouter, MCPBridge, Any]
    ) -> None:
        """Full _execute_bdi_phases() completes without errors."""
        router, _, _ = tool_router
        employee = _make_mock_employee()
        bdi = _make_mock_bdi()

        # LLM returns no tool calls (simple perception)
        async def mock_generate(**kwargs: Any) -> LLMResponse:
            return LLMResponse(
                content="Nothing urgent to check.",
                model="mock",
                usage=_USAGE,
                finish_reason="stop",
                tool_calls=[],
            )

        # For structured output (strategic planning, goal evaluation)
        async def mock_generate_structured(**kwargs: Any) -> Any:
            response_model = kwargs.get("response_model")
            if response_model is not None:
                return response_model()
            return {}

        mock_llm = Mock()
        mock_llm.generate_with_tools = mock_generate
        mock_llm.generate_structured = mock_generate_structured

        loop = ProactiveExecutionLoop(
            employee=employee,
            beliefs=bdi["beliefs"],
            goals=bdi["goals"],
            intentions=bdi["intentions"],
            memory=bdi["memory"],
            llm_service=mock_llm,
            config=LoopConfig(cycle_interval_seconds=1),
            tool_router=router,
        )

        # Run one full cycle — should not raise
        result = await loop._execute_bdi_phases()
        # Result is None when no intention was executed (normal for empty goals)
        assert result is None or hasattr(result, "success")


# ============================================================================
# Tests: Full cycle with real LLM (opt-in)
# ============================================================================


def _has_llm_key() -> bool:
    return bool(
        os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("VERTEX_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
    )


@pytest.mark.skipif(not _has_llm_key(), reason="No LLM API keys configured")
class TestFullCycleWithRealLLM:
    """E2E tests with real LLM — opt-in, requires API key."""

    @pytest.mark.asyncio
    async def test_perception_with_real_llm(
        self, tool_router: tuple[ToolRouter, MCPBridge, Any]
    ) -> None:
        """Real LLM decides which tools to call for perception."""
        from empla.employees.config import LLMSettings
        from empla.llm import LLMService
        from empla.settings import get_settings, resolve_llm_config

        router, _, _ = tool_router
        employee = _make_mock_employee()
        bdi = _make_mock_bdi()

        # Set up a real goal so LLM has something to check
        mock_goal = Mock()
        mock_goal.id = uuid4()
        mock_goal.description = "Maintain 3x pipeline coverage"
        mock_goal.priority = 9
        mock_goal.goal_type = "maintenance"
        mock_goal.status = "active"
        bdi["goals"].get_active_goals = AsyncMock(return_value=[mock_goal])

        settings = get_settings()
        llm_config = resolve_llm_config(
            settings,
            employee_llm=LLMSettings(fallback_model=""),
        )
        llm_service = LLMService(llm_config)

        loop = ProactiveExecutionLoop(
            employee=employee,
            beliefs=bdi["beliefs"],
            goals=bdi["goals"],
            intentions=bdi["intentions"],
            memory=bdi["memory"],
            llm_service=llm_service,
            config=LoopConfig(cycle_interval_seconds=1),
            tool_router=router,
        )

        try:
            tool_schemas = router.get_all_tool_schemas(employee.id)
            result = await loop._perceive_agentic(tool_schemas)

            # Verify perception completed without error
            assert result.observations is not None
            assert result.perception_duration_ms >= 0
            # LLM may or may not call tools depending on its reasoning —
            # the key assertion is that the full stack works without errors
            logger.info(
                "Real LLM perception: %d observations, sources=%s",
                len(result.observations),
                result.sources_checked,
            )
        finally:
            await llm_service.close()
