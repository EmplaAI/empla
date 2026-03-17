"""
Unit tests for agentic execution loop (LLM-driven tool calling).

Tests _execute_intention_with_tools() and the integration between
LLM function calling, tool dispatch, and the execution loop.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

from empla.core.loop.execution import ProactiveExecutionLoop
from empla.core.tools.base import ActionResult
from empla.core.tools.router import ToolRouter
from empla.llm.models import LLMResponse, TokenUsage, ToolCall
from empla.models.employee import Employee

# ============================================================================
# Fixtures
# ============================================================================


def _make_employee() -> Mock:
    """Create a mock Employee for testing."""
    employee = Mock(spec=Employee)
    employee.id = uuid4()
    employee.name = "Test Employee"
    employee.status = "active"
    employee.role = "sales_ae"
    return employee


def _make_mock_bdi():
    """Create mock BDI components."""
    beliefs = MagicMock()
    beliefs.update_beliefs = AsyncMock(return_value=[])
    beliefs.get_all_beliefs = AsyncMock(return_value=[])
    beliefs.update_belief = AsyncMock()

    goals = MagicMock()
    goals.get_active_goals = AsyncMock(return_value=[])
    goals.update_goal_progress = AsyncMock()
    goals.add_goal = AsyncMock()

    intentions = MagicMock()
    intentions.get_next_intention = AsyncMock(return_value=None)
    intentions.dependencies_satisfied = AsyncMock(return_value=True)
    intentions.start_intention = AsyncMock()
    intentions.complete_intention = AsyncMock()
    intentions.fail_intention = AsyncMock()
    intentions.get_intentions_for_goal = AsyncMock(return_value=[])
    intentions.generate_plan_for_goal = AsyncMock(return_value=[])

    memory = MagicMock()
    memory.episodic = MagicMock()
    memory.episodic.record_episode = AsyncMock()
    memory.procedural = MagicMock()
    memory.procedural.record_procedure = AsyncMock()

    return beliefs, goals, intentions, memory


def _make_intention(description: str = "Send welcome email to new lead") -> SimpleNamespace:
    """Create a mock intention."""
    return SimpleNamespace(
        id=uuid4(),
        description=description,
        intention_type="action",
        priority=7,
        plan={"steps": []},
        context={"reasoning": "New lead detected", "success_criteria": "Email sent"},
    )


def _make_llm_response(content: str = "", tool_calls: list[ToolCall] | None = None) -> LLMResponse:
    """Create a mock LLM response."""
    return LLMResponse(
        content=content,
        model="test-model",
        usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        finish_reason="tool_use" if tool_calls else "end_turn",
        tool_calls=tool_calls,
    )


SAMPLE_TOOL_SCHEMAS = [
    {
        "name": "email.send_email",
        "description": "Send email",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "array", "items": {"type": "string"}},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    }
]


def _make_tool_router(
    schemas: list[dict] | None = None,
    execute_result: ActionResult | None = None,
    execute_side_effect: list | Exception | None = None,
) -> MagicMock:
    """Create a mock ToolRouter."""
    if schemas is None:
        schemas = SAMPLE_TOOL_SCHEMAS
    tool_router = MagicMock(spec=ToolRouter)
    tool_router.get_all_tool_schemas = MagicMock(return_value=schemas)
    if execute_side_effect is not None:
        tool_router.execute_tool_call = AsyncMock(side_effect=execute_side_effect)
    elif execute_result is not None:
        tool_router.execute_tool_call = AsyncMock(return_value=execute_result)
    else:
        tool_router.execute_tool_call = AsyncMock(
            return_value=ActionResult(success=True, output={"sent": True})
        )
    return tool_router


# ============================================================================
# Tests for _execute_intention_with_tools
# ============================================================================


@pytest.mark.asyncio
async def test_agentic_execution_single_tool_call():
    """Test LLM makes one tool call then completes."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    # Mock LLM: first call returns tool call, second returns text (done)
    llm_service = MagicMock()
    tc = ToolCall(
        id="tc_1",
        name="email.send_email",
        arguments={"to": ["lead@example.com"], "subject": "Welcome!", "body": "Hello!"},
    )

    responses = [
        _make_llm_response(tool_calls=[tc]),
        _make_llm_response(content="Email sent successfully."),
    ]
    llm_service.generate_with_tools = AsyncMock(side_effect=responses)

    tool_router = _make_tool_router(
        execute_result=ActionResult(success=True, output={"message_id": "msg_123"})
    )

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
        llm_service=llm_service,
        tool_router=tool_router,
    )

    intention = _make_intention()
    result = await loop._execute_intention_with_tools(intention, SAMPLE_TOOL_SCHEMAS)

    assert result["success"] is True
    assert result["tool_calls_made"] == 1
    assert result["agentic"] is True
    assert result["message"] == "Email sent successfully."

    # Verify tool was called with correct arguments
    tool_router.execute_tool_call.assert_called_once_with(
        employee.id,
        "email.send_email",
        {"to": ["lead@example.com"], "subject": "Welcome!", "body": "Hello!"},
    )


@pytest.mark.asyncio
async def test_agentic_execution_no_tool_calls():
    """Test LLM completes without making any tool calls."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    llm_service = MagicMock()
    llm_service.generate_with_tools = AsyncMock(
        return_value=_make_llm_response(content="No action needed.")
    )

    tool_router = _make_tool_router()

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
        llm_service=llm_service,
        tool_router=tool_router,
    )

    intention = _make_intention()
    result = await loop._execute_intention_with_tools(intention, SAMPLE_TOOL_SCHEMAS)

    assert result["success"] is True
    assert result["tool_calls_made"] == 0
    assert result["message"] == "No action needed."
    tool_router.execute_tool_call.assert_not_called()


@pytest.mark.asyncio
async def test_agentic_execution_multiple_tool_calls():
    """Test LLM chains multiple tool calls across iterations."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    tc1 = ToolCall(
        id="tc_1",
        name="email.send_email",
        arguments={"to": ["a@b.com"], "subject": "Hi", "body": "Hello"},
    )
    tc2 = ToolCall(
        id="tc_2",
        name="email.send_email",
        arguments={"to": ["c@d.com"], "subject": "Follow up", "body": "Checking in"},
    )

    llm_service = MagicMock()
    responses = [
        _make_llm_response(tool_calls=[tc1]),
        _make_llm_response(tool_calls=[tc2]),
        _make_llm_response(content="Both emails sent."),
    ]
    llm_service.generate_with_tools = AsyncMock(side_effect=responses)

    tool_router = _make_tool_router(
        execute_result=ActionResult(success=True, output={"sent": True})
    )

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
        llm_service=llm_service,
        tool_router=tool_router,
    )

    intention = _make_intention()
    result = await loop._execute_intention_with_tools(intention, SAMPLE_TOOL_SCHEMAS)

    assert result["success"] is True
    assert result["tool_calls_made"] == 2
    assert tool_router.execute_tool_call.call_count == 2


@pytest.mark.asyncio
async def test_agentic_execution_tool_call_failure_adapts():
    """Test LLM adapts when a tool call fails."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    tc1 = ToolCall(
        id="tc_1",
        name="email.send_email",
        arguments={"to": ["a@b.com"], "subject": "Hi", "body": "Hello"},
    )

    llm_service = MagicMock()
    responses = [
        _make_llm_response(tool_calls=[tc1]),
        _make_llm_response(content="Email failed, but I've noted the issue."),
    ]
    llm_service.generate_with_tools = AsyncMock(side_effect=responses)

    tool_router = _make_tool_router(
        execute_result=ActionResult(success=False, error="SMTP connection refused")
    )

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
        llm_service=llm_service,
        tool_router=tool_router,
    )

    intention = _make_intention()
    result = await loop._execute_intention_with_tools(intention, SAMPLE_TOOL_SCHEMAS)

    # LLM adapts and completes despite tool failure
    assert result["success"] is True
    assert result["tool_calls_made"] == 1


@pytest.mark.asyncio
async def test_agentic_execution_max_iterations():
    """Test max iteration safety limit."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    # LLM keeps making tool calls forever
    tc = ToolCall(
        id="tc_loop",
        name="email.send_email",
        arguments={"to": ["a@b.com"], "subject": "Loop", "body": "Loop"},
    )

    llm_service = MagicMock()
    llm_service.generate_with_tools = AsyncMock(return_value=_make_llm_response(tool_calls=[tc]))

    tool_router = _make_tool_router(
        execute_result=ActionResult(success=True, output={"sent": True})
    )

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
        llm_service=llm_service,
        tool_router=tool_router,
    )

    intention = _make_intention()
    result = await loop._execute_intention_with_tools(intention, SAMPLE_TOOL_SCHEMAS)

    assert result["success"] is False
    assert "iteration budget" in result["error"]
    assert result["tool_calls_made"] == 10  # max_iterations = 10


@pytest.mark.asyncio
async def test_agentic_execution_llm_failure():
    """Test agentic execution handles LLM failure gracefully."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    llm_service = MagicMock()
    llm_service.generate_with_tools = AsyncMock(side_effect=Exception("LLM API timeout"))

    tool_router = _make_tool_router()

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
        llm_service=llm_service,
        tool_router=tool_router,
    )

    intention = _make_intention()
    result = await loop._execute_intention_with_tools(intention, SAMPLE_TOOL_SCHEMAS)

    assert result["success"] is False
    assert "LLM call failed" in result["error"]
    assert result["agentic"] is True


@pytest.mark.asyncio
async def test_agentic_execution_tool_exception():
    """Test agentic execution handles tool call exception without crashing."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    tc = ToolCall(
        id="tc_1",
        name="email.send_email",
        arguments={"to": ["a@b.com"], "subject": "Hi", "body": "Hello"},
    )

    llm_service = MagicMock()
    responses = [
        _make_llm_response(tool_calls=[tc]),
        _make_llm_response(content="Handled the error."),
    ]
    llm_service.generate_with_tools = AsyncMock(side_effect=responses)

    tool_router = _make_tool_router(execute_side_effect=RuntimeError("Connection lost"))

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
        llm_service=llm_service,
        tool_router=tool_router,
    )

    intention = _make_intention()
    result = await loop._execute_intention_with_tools(intention, SAMPLE_TOOL_SCHEMAS)

    # Should succeed because LLM handles the error
    assert result["success"] is True
    assert result["tool_calls_made"] == 1


# ============================================================================
# Tests for _execute_intention_plan fallback behavior
# ============================================================================


@pytest.mark.asyncio
async def test_intention_plan_uses_agentic_when_available():
    """Test _execute_intention_plan prefers agentic execution when tools available."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    llm_service = MagicMock()
    llm_service.generate_with_tools = AsyncMock(
        return_value=_make_llm_response(content="Done via agentic.")
    )

    tool_router = _make_tool_router()

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
        llm_service=llm_service,
        tool_router=tool_router,
    )

    intention = _make_intention()
    result = await loop._execute_intention_plan(intention)

    assert result["agentic"] is True
    assert result["success"] is True


@pytest.mark.asyncio
async def test_intention_plan_errors_without_llm():
    """Test _execute_intention_plan returns error without LLM service."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
        llm_service=None,  # No LLM
    )

    intention = _make_intention()
    result = await loop._execute_intention_plan(intention)

    assert result["success"] is False
    assert result["agentic"] is True
    assert "LLM service" in result["error"]


@pytest.mark.asyncio
async def test_intention_plan_errors_without_tools():
    """Test _execute_intention_plan returns error when no tools available."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    llm_service = MagicMock()

    tool_router = _make_tool_router(schemas=[])  # No tools

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
        llm_service=llm_service,
        tool_router=tool_router,
    )

    intention = _make_intention()
    result = await loop._execute_intention_plan(intention)

    assert result["success"] is False
    assert result["agentic"] is True
    assert "No tools" in result["error"]


# ============================================================================
# Tests for prompt building
# ============================================================================


def test_build_execution_system_prompt():
    """Test system prompt is non-empty and reasonable."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
    )

    prompt = loop._build_execution_system_prompt()
    assert "tool" in prompt.lower()
    assert len(prompt) > 20


def test_build_intention_prompt():
    """Test intention prompt includes description and context."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
    )

    intention = _make_intention("Send email to lead@example.com")
    prompt = loop._build_intention_prompt(intention)

    assert "Send email to lead@example.com" in prompt
    assert "New lead detected" in prompt
    assert "Email sent" in prompt


def test_build_intention_prompt_no_context():
    """Test intention prompt works without context."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
    )

    intention = SimpleNamespace(
        id=uuid4(),
        description="Do something",
        context=None,
    )
    prompt = loop._build_intention_prompt(intention)

    assert "Do something" in prompt


# ============================================================================
# Tests for critical edge cases (parallel tool calls, mid-loop failures)
# ============================================================================


@pytest.mark.asyncio
async def test_agentic_execution_parallel_tool_calls_in_single_response():
    """Test LLM returns multiple tool calls in a single response."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    tc1 = ToolCall(
        id="tc_1",
        name="email.send_email",
        arguments={"to": ["alice@example.com"], "subject": "Hi Alice", "body": "Hello"},
    )
    tc2 = ToolCall(
        id="tc_2",
        name="email.send_email",
        arguments={"to": ["bob@example.com"], "subject": "Hi Bob", "body": "Hello"},
    )

    llm_service = MagicMock()
    responses = [
        _make_llm_response(tool_calls=[tc1, tc2]),  # Both in one response
        _make_llm_response(content="Both emails sent."),
    ]
    llm_service.generate_with_tools = AsyncMock(side_effect=responses)

    # First call succeeds, second fails
    tool_router = _make_tool_router(
        execute_side_effect=[
            ActionResult(success=True, output={"message_id": "msg_1"}),
            ActionResult(success=False, error="SMTP error for Bob"),
        ]
    )

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
        llm_service=llm_service,
        tool_router=tool_router,
    )

    intention = _make_intention()
    result = await loop._execute_intention_with_tools(intention, SAMPLE_TOOL_SCHEMAS)

    assert result["success"] is True
    assert result["tool_calls_made"] == 2
    assert tool_router.execute_tool_call.call_count == 2

    # Verify both tool result messages were appended
    second_call_args = llm_service.generate_with_tools.call_args_list[1]
    messages = second_call_args.kwargs["messages"]
    tool_messages = [m for m in messages if m.role == "tool"]
    assert len(tool_messages) == 2
    assert tool_messages[0].tool_call_id == "tc_1"
    assert tool_messages[1].tool_call_id == "tc_2"


@pytest.mark.asyncio
async def test_agentic_execution_llm_fails_on_later_iteration():
    """Test LLM fails on a later iteration after completing tool calls."""
    employee = _make_employee()
    beliefs, goals, intentions, memory = _make_mock_bdi()

    tc = ToolCall(
        id="tc_1",
        name="email.send_email",
        arguments={"to": ["a@b.com"], "subject": "Hi", "body": "Hello"},
    )

    llm_service = MagicMock()
    responses = [
        _make_llm_response(tool_calls=[tc]),  # iteration 0: tool call
        _make_llm_response(tool_calls=[tc]),  # iteration 1: tool call
        Exception("API rate limit exceeded"),  # iteration 2: failure
    ]
    llm_service.generate_with_tools = AsyncMock(side_effect=responses)

    tool_router = _make_tool_router(
        execute_result=ActionResult(success=True, output={"sent": True})
    )

    loop = ProactiveExecutionLoop(
        employee=employee,
        beliefs=beliefs,
        goals=goals,
        intentions=intentions,
        memory=memory,
        llm_service=llm_service,
        tool_router=tool_router,
    )

    intention = _make_intention()
    result = await loop._execute_intention_with_tools(intention, SAMPLE_TOOL_SCHEMAS)

    assert result["success"] is False
    assert "LLM call failed" in result["error"]
    # Should track the 2 tool calls that completed before the failure
    assert result["tool_calls_made"] == 2
