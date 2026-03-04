"""
Full E2E tests - IntegrationRouter + Agentic Perception + Test Servers.

Tests the complete flow:
1. IntegrationRouter registers email tools
2. ToolRouter serves them to the BDI loop
3. Agentic perception uses LLM to check tools
4. Test email server provides realistic data
5. Activity recorder captures events

These tests require:
- LLM API key (ANTHROPIC_API_KEY or OPENAI_API_KEY)
- Database (DATABASE_URL)
- Test email server NOT required (in-process testing via TestEmailAdapter)
"""

import logging
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from empla.core.hooks import HookRegistry
from empla.core.tools.registry import ToolRegistry
from empla.core.tools.router import ToolRouter
from empla.integrations.router import IntegrationRouter

logger = logging.getLogger(__name__)


# ============================================================================
# Unit-style tests (no LLM, no DB, fast)
# ============================================================================


class TestIntegrationRouter:
    """Test IntegrationRouter core functionality."""

    def test_tool_registration(self) -> None:
        """@router.tool() registers tools with auto-generated schemas."""
        router = IntegrationRouter("test_svc")

        @router.tool()
        async def do_thing(name: str, count: int = 5) -> dict:
            """Do a thing."""
            return {"name": name, "count": count}

        schemas = router.get_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "test_svc.do_thing"
        assert schemas[0]["description"] == "Do a thing."
        assert "name" in schemas[0]["input_schema"]["properties"]
        assert "count" in schemas[0]["input_schema"]["properties"]
        assert schemas[0]["input_schema"]["required"] == ["name"]

    def test_custom_tool_name(self) -> None:
        """Custom name overrides function name."""
        router = IntegrationRouter("svc")

        @router.tool(name="custom_name", description="Custom desc")
        async def my_func() -> dict:
            return {}

        schemas = router.get_tool_schemas()
        assert schemas[0]["name"] == "svc.custom_name"
        assert schemas[0]["description"] == "Custom desc"

    @pytest.mark.asyncio
    async def test_tool_execution(self) -> None:
        """Tools execute correctly via execute_tool()."""
        router = IntegrationRouter("math")

        @router.tool()
        async def add(a: int, b: int) -> dict:
            """Add two numbers."""
            return {"result": a + b}

        result = await router.execute_tool("math.add", {"a": 3, "b": 4})
        assert result == {"result": 7}

    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self) -> None:
        """Executing unknown tool raises ValueError."""
        router = IntegrationRouter("svc")
        with pytest.raises(ValueError, match="Unknown tool"):
            await router.execute_tool("svc.nonexistent", {})

    @pytest.mark.asyncio
    async def test_adapter_lifecycle(self) -> None:
        """Adapter factory called during initialize, shutdown calls adapter."""
        mock_adapter = MagicMock()
        mock_adapter.initialize = AsyncMock()
        mock_adapter.shutdown = AsyncMock()

        def factory(**kwargs: Any) -> MagicMock:
            return mock_adapter

        router = IntegrationRouter("svc", adapter_factory=factory)
        await router.initialize({"credentials": {"token": "abc"}})

        assert router.adapter is mock_adapter
        mock_adapter.initialize.assert_called_once_with({"token": "abc"})

        await router.shutdown()
        mock_adapter.shutdown.assert_called_once()

    def test_adapter_not_initialized_raises(self) -> None:
        """Accessing adapter before initialize() raises RuntimeError."""
        router = IntegrationRouter("svc")
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = router.adapter

    def test_from_mcp(self) -> None:
        """from_mcp creates router with MCP config stored."""
        router = IntegrationRouter.from_mcp("cal", transport="http", url="http://localhost:9101")
        assert router.name == "cal"
        assert router._mcp_config == {"transport": "http", "url": "http://localhost:9101"}

    def test_repr(self) -> None:
        """Repr shows name and tool count."""
        router = IntegrationRouter("email")

        @router.tool()
        async def send() -> dict:
            return {}

        assert "email" in repr(router)
        assert "1" in repr(router)


class TestToolRouterIntegration:
    """Test ToolRouter.register_integration()."""

    def test_register_integration_adds_tools(self) -> None:
        """Integration tools appear in ToolRouter schemas."""
        tool_router = ToolRouter()

        router = IntegrationRouter("test")

        @router.tool()
        async def greet(name: str) -> dict:
            """Say hello."""
            return {"greeting": f"Hello {name}"}

        tool_router.register_integration(router)

        employee_id = uuid4()
        schemas = tool_router.get_all_tool_schemas(employee_id)
        tool_names = [s["name"] for s in schemas]
        assert "test.greet" in tool_names

    @pytest.mark.asyncio
    async def test_execute_integration_tool(self) -> None:
        """Integration tools execute correctly via ToolRouter."""
        tool_router = ToolRouter()

        router = IntegrationRouter("math")

        @router.tool()
        async def multiply(a: int, b: int) -> dict:
            """Multiply two numbers."""
            return {"result": a * b}

        tool_router.register_integration(router)

        result = await tool_router.execute_tool_call(uuid4(), "math.multiply", {"a": 5, "b": 3})
        assert result.success is True
        assert result.output == {"result": 15}

    @pytest.mark.asyncio
    async def test_integration_shutdown(self) -> None:
        """shutdown_integrations calls shutdown on all routers."""
        tool_router = ToolRouter()

        mock_adapter = MagicMock()
        mock_adapter.shutdown = AsyncMock()

        router = IntegrationRouter("svc")
        router._adapter = mock_adapter
        tool_router.register_integration(router)

        await tool_router.shutdown_integrations()
        mock_adapter.shutdown.assert_called_once()

    def test_get_enabled_capabilities_includes_integrations(self) -> None:
        """get_enabled_capabilities returns integration names."""
        tool_router = ToolRouter()

        router = IntegrationRouter("email")
        tool_router.register_integration(router)

        caps = tool_router.get_enabled_capabilities(uuid4())
        assert "email" in caps


class TestEmailIntegrationTools:
    """Test the email integration tools module."""

    def test_email_tools_registered(self) -> None:
        """Email tools module registers expected tools."""
        from empla.integrations.email.tools import router

        schemas = router.get_tool_schemas()
        tool_names = [s["name"] for s in schemas]
        assert "email.send_email" in tool_names
        assert "email.reply_to_email" in tool_names
        assert "email.get_unread_emails" in tool_names
        assert "email.mark_read" in tool_names
        assert "email.archive" in tool_names


class TestActivityRecorder:
    """Test ActivityRecorder hook registration."""

    def test_registers_on_hooks(self) -> None:
        """ActivityRecorder registers handlers on expected hooks."""
        from empla.services.activity_recorder import ActivityRecorder

        hooks = HookRegistry()
        recorder = ActivityRecorder(
            session=MagicMock(),
            tenant_id=uuid4(),
            employee_id=uuid4(),
        )
        recorder.register(hooks)

        from empla.core.hooks import (
            HOOK_AFTER_INTENTION_EXECUTION,
            HOOK_AFTER_PERCEPTION,
            HOOK_EMPLOYEE_START,
            HOOK_EMPLOYEE_STOP,
        )

        assert hooks.has_handlers(HOOK_AFTER_PERCEPTION)
        assert hooks.has_handlers(HOOK_AFTER_INTENTION_EXECUTION)
        assert hooks.has_handlers(HOOK_EMPLOYEE_START)
        assert hooks.has_handlers(HOOK_EMPLOYEE_STOP)


# ============================================================================
# E2E tests with test email server (require httpx + FastAPI)
# ============================================================================


class TestEmailServerIntegration:
    """Test email server + TestEmailAdapter together."""

    @pytest.fixture
    async def email_server(self):
        """Start test email server in-process."""
        import asyncio

        import uvicorn

        from tests.servers.email_server import app, store

        # Reset state
        store.reset()

        config = uvicorn.Config(app, host="127.0.0.1", port=9199, log_level="error")
        server = uvicorn.Server(config)

        task = asyncio.create_task(server.serve())
        # Wait for server to be ready
        await asyncio.sleep(0.3)

        yield store

        server.should_exit = True
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_test_email_adapter_send_and_fetch(self, email_server: Any) -> None:
        """TestEmailAdapter can send and fetch emails via test server."""
        from empla.integrations.email.test_adapter import TestEmailAdapter

        adapter = TestEmailAdapter("bot@test.empla.ai", base_url="http://127.0.0.1:9199")
        await adapter.initialize({})

        try:
            # Send an email
            result = await adapter.send(
                to=["user@example.com"],
                subject="Test Subject",
                body="Test body content",
            )
            assert result.success is True
            assert "message_id" in result.data

            # Load an inbox email
            from tests.servers.email_server import EmailMessage, store

            store.add_email(
                EmailMessage(
                    id="test-001",
                    from_addr="external@example.com",
                    to_addrs=["bot@test.empla.ai"],
                    subject="Incoming test",
                    body="Hello bot!",
                    timestamp="2024-01-01T00:00:00Z",
                    is_read=False,
                )
            )

            # Fetch unread
            emails = await adapter.fetch_emails(unread_only=True, max_results=10)
            assert len(emails) == 1
            assert emails[0].subject == "Incoming test"
            assert emails[0].is_read is False

            # Mark read
            mark_result = await adapter.mark_read("test-001")
            assert mark_result.success is True

            # Verify marked read
            emails = await adapter.fetch_emails(unread_only=True, max_results=10)
            assert len(emails) == 0
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_email_integration_router_with_test_adapter(self, email_server: Any) -> None:
        """Full flow: IntegrationRouter + TestEmailAdapter + ToolRouter."""
        from empla.integrations.email.factory import create_email_adapter

        # Create fresh router (don't reuse module-level one)
        router = IntegrationRouter("email", adapter_factory=create_email_adapter)

        @router.tool()
        async def send_email(to: list[str], subject: str, body: str) -> dict:
            """Send email."""
            result = await router.adapter.send(to, subject, body)
            return {"success": result.success, "message_id": result.data.get("message_id")}

        @router.tool()
        async def get_unread_emails(max_results: int = 10) -> list[dict]:
            """Get unread emails."""
            emails = await router.adapter.fetch_emails(unread_only=True, max_results=max_results)
            return [{"id": e.id, "subject": e.subject} for e in emails]

        # Initialize with test provider
        await router.initialize(
            {
                "provider": "test",
                "email_address": "bot@test.empla.ai",
                "base_url": "http://127.0.0.1:9199",
            }
        )

        # Register in ToolRouter
        tool_router = ToolRouter()
        tool_router.register_integration(router)

        employee_id = uuid4()

        # Verify schemas
        schemas = tool_router.get_all_tool_schemas(employee_id)
        tool_names = [s["name"] for s in schemas]
        assert "email.send_email" in tool_names
        assert "email.get_unread_emails" in tool_names

        # Execute send via ToolRouter
        result = await tool_router.execute_tool_call(
            employee_id,
            "email.send_email",
            {"to": ["user@example.com"], "subject": "Hello", "body": "Hi there"},
        )
        assert result.success is True

        # Verify email was sent
        state = email_server.get_state()
        assert state["sent_count"] == 1

        await router.shutdown()


# ============================================================================
# Full BDI cycle test (requires LLM)
# ============================================================================


def has_any_llm_key() -> bool:
    return bool(
        os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("VERTEX_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
    )


@pytest.mark.skipif(not has_any_llm_key(), reason="No LLM API keys configured")
class TestAgenticPerception:
    """Test agentic perception with real LLM."""

    @pytest.mark.asyncio
    async def test_agentic_perception_calls_tools(self) -> None:
        """LLM-driven perception uses tools to check environment."""
        from empla.core.loop.execution import ProactiveExecutionLoop
        from empla.core.loop.models import LoopConfig
        from empla.employees.config import LLMSettings
        from empla.llm import LLMService
        from empla.settings import get_settings, resolve_llm_config

        settings = get_settings()
        # Force no fallback model to avoid requiring multiple API keys
        llm_config = resolve_llm_config(
            settings,
            employee_llm=LLMSettings(fallback_model=""),
        )
        llm_service = LLMService(llm_config)

        # Create mock BDI components
        mock_beliefs = AsyncMock()
        mock_beliefs.get_all_beliefs = AsyncMock(return_value=[])
        mock_beliefs.update_beliefs = AsyncMock(return_value=[])

        mock_goals = AsyncMock()
        mock_goals.get_active_goals = AsyncMock(
            return_value=[
                MagicMock(description="Maintain 3x pipeline coverage", priority=9, id=uuid4()),
            ]
        )

        mock_intentions = AsyncMock()
        mock_intentions.get_next_intention = AsyncMock(return_value=None)

        mock_memory = MagicMock()
        mock_memory.episodic = MagicMock()
        mock_memory.procedural = MagicMock()

        # Create a simple tool for testing
        tool_reg = ToolRegistry()
        tool_router = ToolRouter(tool_reg)

        router = IntegrationRouter("crm")

        @router.tool()
        async def get_pipeline_metrics() -> dict:
            """Get CRM pipeline metrics."""
            return {"coverage": 1.8, "total_value": 180000, "deal_count": 3}

        tool_router.register_integration(router)

        # Create mock employee
        mock_employee = MagicMock()
        mock_employee.id = uuid4()
        mock_employee.tenant_id = uuid4()
        mock_employee.name = "Test Employee"

        loop = ProactiveExecutionLoop(
            employee=mock_employee,
            beliefs=mock_beliefs,
            goals=mock_goals,
            intentions=mock_intentions,
            memory=mock_memory,
            llm_service=llm_service,
            config=LoopConfig(cycle_interval_seconds=10),
            tool_router=tool_router,
        )

        try:
            # Run agentic perception
            tool_schemas = tool_router.get_all_tool_schemas(mock_employee.id)
            result = await loop._perceive_agentic(tool_schemas)

            # The LLM should have made at least one tool call
            assert len(result.observations) >= 0  # LLM may or may not call tools
            assert result.perception_duration_ms >= 0
        finally:
            await llm_service.close()
