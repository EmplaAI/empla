"""
Tests for tool execution system.

Tests cover:
- ToolExecutionEngine retry logic
- Parameter validation
- Error handling
- ToolRegistry functionality
- Tool discovery and filtering
"""

import asyncio
from typing import Any

import pytest

from empla.core.tools import (
    Tool,
    ToolCapability,
    ToolExecutionEngine,
    ToolRegistry,
)


# Mock tool implementations for testing
class SuccessfulTool:
    """Tool that always succeeds."""

    async def _execute(self, params: dict[str, Any]) -> Any:
        return {"result": "success", "params": params}


class FailingTool:
    """Tool that always fails."""

    def __init__(self, error_msg: str = "Tool failed"):
        self.error_msg = error_msg

    async def _execute(self, params: dict[str, Any]) -> Any:
        raise RuntimeError(self.error_msg)


class FlakeyTool:
    """Tool that fails N times then succeeds."""

    def __init__(self, failures_before_success: int = 2):
        self.failures_before_success = failures_before_success
        self.attempt = 0

    async def _execute(self, params: dict[str, Any]) -> Any:
        self.attempt += 1
        if self.attempt <= self.failures_before_success:
            raise RuntimeError(f"Transient timeout error (attempt {self.attempt})")
        return {"result": "success", "attempts": self.attempt}


class SlowTool:
    """Tool that takes time to execute."""

    def __init__(self, delay_ms: int = 100):
        self.delay_ms = delay_ms

    async def _execute(self, params: dict[str, Any]) -> Any:
        await asyncio.sleep(self.delay_ms / 1000)
        return {"result": "success", "delay_ms": self.delay_ms}


# Test ToolExecutionEngine


@pytest.mark.asyncio
async def test_execute_successful_tool():
    """Test successful tool execution."""
    engine = ToolExecutionEngine()
    tool = Tool(
        name="test_tool",
        description="Test tool",
        parameters_schema={"param1": {"type": "string"}},
    )
    implementation = SuccessfulTool()

    result = await engine.execute(tool, implementation, {"param1": "value1"})

    assert result.success
    assert result.output == {"result": "success", "params": {"param1": "value1"}}
    assert result.error is None
    assert result.duration_ms > 0
    assert result.retries == 0


@pytest.mark.asyncio
async def test_execute_failing_tool():
    """Test tool execution with permanent failure."""
    engine = ToolExecutionEngine(max_retries=2)
    tool = Tool(
        name="test_tool",
        description="Test tool",
        parameters_schema={},
    )
    implementation = FailingTool("Permanent validation error")

    result = await engine.execute(tool, implementation, {})

    assert not result.success
    assert "validation error" in result.error.lower()
    assert result.output is None
    assert result.duration_ms > 0
    # Permanent error should not retry
    assert result.retries == 0


@pytest.mark.asyncio
async def test_execute_with_retry_transient_failure():
    """Test retry logic for transient failures."""
    engine = ToolExecutionEngine(
        max_retries=3,
        initial_backoff_ms=10,
        backoff_multiplier=2.0,
    )
    tool = Tool(
        name="test_tool",
        description="Test tool",
        parameters_schema={},
    )
    implementation = FlakeyTool(failures_before_success=2)

    result = await engine.execute(tool, implementation, {})

    assert result.success
    assert result.output["attempts"] == 3  # Failed twice, succeeded on 3rd
    assert result.retries == 2  # 2 retry attempts
    assert result.duration_ms > 0


@pytest.mark.asyncio
async def test_execute_retry_exhaustion():
    """Test when all retries are exhausted."""
    engine = ToolExecutionEngine(
        max_retries=2,
        initial_backoff_ms=10,
    )
    tool = Tool(
        name="test_tool",
        description="Test tool",
        parameters_schema={},
    )
    # Fails 5 times, but we only retry 2 times (3 total attempts)
    implementation = FlakeyTool(failures_before_success=5)

    result = await engine.execute(tool, implementation, {})

    assert not result.success
    assert "timeout" in result.error.lower()
    assert result.retries == 2  # Max retries reached


@pytest.mark.asyncio
async def test_parameter_validation_missing_required():
    """Test parameter validation for missing required parameter."""
    engine = ToolExecutionEngine()
    tool = Tool(
        name="test_tool",
        description="Test tool",
        parameters_schema={
            "required_param": {"type": "string", "required": True},
            "optional_param": {"type": "string"},
        },
    )
    implementation = SuccessfulTool()

    # Missing required parameter
    result = await engine.execute(tool, implementation, {"optional_param": "value"})

    assert not result.success
    assert "missing required parameter" in result.error.lower()
    assert result.retries == 0


@pytest.mark.asyncio
async def test_parameter_validation_wrong_type():
    """Test parameter validation for wrong type."""
    engine = ToolExecutionEngine()
    tool = Tool(
        name="test_tool",
        description="Test tool",
        parameters_schema={
            "string_param": {"type": "string"},
            "number_param": {"type": "number"},
        },
    )
    implementation = SuccessfulTool()

    # Wrong type for number_param (string instead of number)
    result = await engine.execute(
        tool, implementation, {"string_param": "hello", "number_param": "not a number"}
    )

    assert not result.success
    assert "wrong type" in result.error.lower()


@pytest.mark.asyncio
async def test_parameter_validation_unexpected_parameter():
    """Test parameter validation for unexpected parameter."""
    engine = ToolExecutionEngine()
    tool = Tool(
        name="test_tool",
        description="Test tool",
        parameters_schema={
            "allowed_param": {"type": "string"},
        },
    )
    implementation = SuccessfulTool()

    # Pass an unexpected parameter
    result = await engine.execute(
        tool, implementation, {"allowed_param": "valid", "unexpected_param": "should_fail"}
    )

    assert not result.success
    assert "unexpected parameter" in result.error.lower()
    assert "unexpected_param" in result.error
    assert result.retries == 0


@pytest.mark.asyncio
async def test_execution_timing():
    """Test that execution duration is tracked correctly."""
    engine = ToolExecutionEngine()
    tool = Tool(
        name="slow_tool",
        description="Slow tool",
        parameters_schema={},
    )
    implementation = SlowTool(delay_ms=100)

    result = await engine.execute(tool, implementation, {})

    assert result.success
    assert result.duration_ms >= 100  # At least 100ms (delay was applied)


@pytest.mark.asyncio
async def test_should_retry_transient_errors():
    """Test that transient errors trigger retry."""
    engine = ToolExecutionEngine()

    # Transient errors should retry
    assert engine._should_retry(RuntimeError("Connection timeout"))
    assert engine._should_retry(RuntimeError("Rate limit exceeded"))
    assert engine._should_retry(RuntimeError("503 Service Unavailable"))
    assert engine._should_retry(RuntimeError("429 Too Many Requests"))


@pytest.mark.asyncio
async def test_should_not_retry_permanent_errors():
    """Test that permanent errors do NOT trigger retry."""
    engine = ToolExecutionEngine()

    # Permanent errors should NOT retry
    assert not engine._should_retry(RuntimeError("401 Unauthorized"))
    assert not engine._should_retry(RuntimeError("403 Forbidden"))
    assert not engine._should_retry(RuntimeError("404 Not Found"))
    assert not engine._should_retry(ValueError("Invalid parameter"))
    assert not engine._should_retry(RuntimeError("Authentication failed"))


# Test ToolRegistry


def test_register_and_get_tool():
    """Test tool registration and retrieval."""
    registry = ToolRegistry()
    tool = Tool(
        name="test_tool",
        description="Test tool",
        parameters_schema={},
    )
    implementation = SuccessfulTool()

    registry.register_tool(tool, implementation)

    # Get by ID
    retrieved = registry.get_tool(tool.tool_id)
    assert retrieved == tool

    # Get by name
    retrieved_by_name = registry.get_tool_by_name("test_tool")
    assert retrieved_by_name == tool

    # Get implementation
    impl = registry.get_implementation(tool.tool_id)
    assert impl == implementation


def test_register_duplicate_tool_name():
    """Test that registering duplicate tool names raises error."""
    registry = ToolRegistry()
    tool1 = Tool(name="test_tool", description="Tool 1", parameters_schema={})
    tool2 = Tool(name="test_tool", description="Tool 2", parameters_schema={})

    registry.register_tool(tool1, SuccessfulTool())

    with pytest.raises(ValueError, match="already registered"):
        registry.register_tool(tool2, SuccessfulTool())


def test_list_tools_no_filter():
    """Test listing all tools without filter."""
    registry = ToolRegistry()

    tool1 = Tool(
        name="tool1",
        description="Tool 1",
        parameters_schema={},
        required_capabilities=["email"],
        category="communication",
    )
    tool2 = Tool(
        name="tool2",
        description="Tool 2",
        parameters_schema={},
        required_capabilities=["calendar"],
        category="scheduling",
    )

    registry.register_tool(tool1, SuccessfulTool())
    registry.register_tool(tool2, SuccessfulTool())

    tools = registry.list_tools()
    assert len(tools) == 2


def test_list_tools_by_capability():
    """Test filtering tools by capability."""
    registry = ToolRegistry()

    email_tool = Tool(
        name="send_email",
        description="Send email",
        parameters_schema={},
        required_capabilities=["email"],
    )
    calendar_tool = Tool(
        name="schedule_meeting",
        description="Schedule meeting",
        parameters_schema={},
        required_capabilities=["calendar"],
    )

    registry.register_tool(email_tool, SuccessfulTool())
    registry.register_tool(calendar_tool, SuccessfulTool())

    email_tools = registry.list_tools(capability="email")
    assert len(email_tools) == 1
    assert email_tools[0].name == "send_email"


def test_list_tools_by_category():
    """Test filtering tools by category."""
    registry = ToolRegistry()

    tool1 = Tool(
        name="tool1",
        description="Communication tool",
        parameters_schema={},
        category="communication",
    )
    tool2 = Tool(
        name="tool2",
        description="Research tool",
        parameters_schema={},
        category="research",
    )

    registry.register_tool(tool1, SuccessfulTool())
    registry.register_tool(tool2, SuccessfulTool())

    comm_tools = registry.list_tools(category="communication")
    assert len(comm_tools) == 1
    assert comm_tools[0].name == "tool1"


def test_list_tools_by_tag():
    """Test filtering tools by tag."""
    registry = ToolRegistry()

    tool1 = Tool(
        name="tool1",
        description="Priority tool",
        parameters_schema={},
        tags=["priority", "email"],
    )
    tool2 = Tool(
        name="tool2",
        description="Normal tool",
        parameters_schema={},
        tags=["email"],
    )

    registry.register_tool(tool1, SuccessfulTool())
    registry.register_tool(tool2, SuccessfulTool())

    priority_tools = registry.list_tools(tag="priority")
    assert len(priority_tools) == 1
    assert priority_tools[0].name == "tool1"


def test_register_and_get_capability():
    """Test capability registration and retrieval."""
    registry = ToolRegistry()
    capability = ToolCapability(
        name="email",
        description="Email operations",
        required_credentials=["microsoft_graph_token"],
        tools=["send_email", "read_email"],
    )

    registry.register_capability(capability)

    retrieved = registry.get_capability("email")
    assert retrieved == capability


def test_has_capability_with_credentials():
    """Test checking if credentials satisfy capability requirements."""
    registry = ToolRegistry()
    capability = ToolCapability(
        name="email",
        description="Email operations",
        required_credentials=["microsoft_graph_token"],
        tools=["send_email"],
    )
    registry.register_capability(capability)

    # Has required credentials
    credentials = {"microsoft_graph_token": "eyJ0..."}
    assert registry.has_capability("email", credentials)

    # Missing required credentials
    missing_creds = {"other_token": "abc"}
    assert not registry.has_capability("email", missing_creds)


def test_get_tools_for_employee():
    """Test getting available tools for employee based on capabilities and credentials."""
    registry = ToolRegistry()

    # Register email capability
    email_capability = ToolCapability(
        name="email",
        description="Email operations",
        required_credentials=["microsoft_graph_token"],
        tools=["send_email"],
    )
    registry.register_capability(email_capability)

    # Register calendar capability
    calendar_capability = ToolCapability(
        name="calendar",
        description="Calendar operations",
        required_credentials=["google_oauth_token"],
        tools=["schedule_meeting"],
    )
    registry.register_capability(calendar_capability)

    # Register tools
    email_tool = Tool(
        name="send_email",
        description="Send email",
        parameters_schema={},
        required_capabilities=["email"],
    )
    calendar_tool = Tool(
        name="schedule_meeting",
        description="Schedule meeting",
        parameters_schema={},
        required_capabilities=["calendar"],
    )
    registry.register_tool(email_tool, SuccessfulTool())
    registry.register_tool(calendar_tool, SuccessfulTool())

    # Employee with email capability and credentials
    employee_capabilities = ["email"]
    employee_credentials = {"microsoft_graph_token": "eyJ0..."}

    available_tools = registry.get_tools_for_employee(employee_capabilities, employee_credentials)

    # Should only get email tool (has capability and credentials)
    assert len(available_tools) == 1
    assert available_tools[0].name == "send_email"


def test_registry_clear():
    """Test clearing registry."""
    registry = ToolRegistry()

    tool = Tool(name="test_tool", description="Test", parameters_schema={})
    registry.register_tool(tool, SuccessfulTool())

    assert len(registry) == 1

    registry.clear()

    assert len(registry) == 0
    assert registry.get_tool_by_name("test_tool") is None


def test_registry_contains():
    """Test __contains__ method."""
    registry = ToolRegistry()

    tool = Tool(name="test_tool", description="Test", parameters_schema={})
    registry.register_tool(tool, SuccessfulTool())

    assert "test_tool" in registry
    assert "nonexistent_tool" not in registry
