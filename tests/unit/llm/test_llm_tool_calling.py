"""
Unit tests for LLM function calling / tool use support.

Tests tool call models, provider-level tool calling, and LLMService.generate_with_tools().
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from empla.llm import LLMService
from empla.llm.config import LLMConfig
from empla.llm.models import (
    LLMRequest,
    LLMResponse,
    Message,
    TokenUsage,
    ToolCall,
)

# ============================================================================
# Model Tests
# ============================================================================


def test_tool_call_model():
    """Test ToolCall model creation."""
    tc = ToolCall(id="tc_123", name="email.send", arguments={"to": ["a@b.com"], "subject": "Hi"})
    assert tc.id == "tc_123"
    assert tc.name == "email.send"
    assert tc.arguments["to"] == ["a@b.com"]


def test_message_tool_role():
    """Test Message accepts 'tool' role."""
    msg = Message(role="tool", content='{"success": true}', tool_call_id="tc_123")
    assert msg.role == "tool"
    assert msg.tool_call_id == "tc_123"


def test_message_assistant_with_tool_calls():
    """Test Message can carry tool_calls for assistant role."""
    tc = ToolCall(id="tc_1", name="email.send", arguments={"to": ["a@b.com"]})
    msg = Message(role="assistant", content="I'll send that email.", tool_calls=[tc])
    assert msg.tool_calls is not None
    assert len(msg.tool_calls) == 1
    assert msg.tool_calls[0].name == "email.send"


def test_message_backwards_compatible():
    """Test Message still works without new fields (backwards compatibility)."""
    msg = Message(role="user", content="Hello")
    assert msg.tool_calls is None
    assert msg.tool_call_id is None


def test_llm_request_with_tools():
    """Test LLMRequest accepts tools and tool_choice."""
    tools = [
        {
            "name": "email.send",
            "description": "Send email",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]
    request = LLMRequest(
        messages=[Message(role="user", content="Send email")],
        tools=tools,
        tool_choice="auto",
    )
    assert request.tools is not None
    assert len(request.tools) == 1
    assert request.tool_choice == "auto"


def test_llm_request_without_tools():
    """Test LLMRequest works without tools (backwards compatibility)."""
    request = LLMRequest(messages=[Message(role="user", content="Hello")])
    assert request.tools is None
    assert request.tool_choice is None


def test_llm_response_with_tool_calls():
    """Test LLMResponse can carry tool_calls."""
    tc = ToolCall(id="tc_1", name="email.send", arguments={"to": ["a@b.com"]})
    response = LLMResponse(
        content="",
        model="test",
        usage=TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30),
        finish_reason="tool_use",
        tool_calls=[tc],
    )
    assert response.tool_calls is not None
    assert response.finish_reason == "tool_use"


def test_llm_response_without_tool_calls():
    """Test LLMResponse works without tool_calls (backwards compatibility)."""
    response = LLMResponse(
        content="Hello",
        model="test",
        usage=TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30),
        finish_reason="stop",
    )
    assert response.tool_calls is None


# ============================================================================
# Message Validation Tests
# ============================================================================


def test_message_tool_requires_tool_call_id():
    """Tool messages must have tool_call_id."""
    with pytest.raises(ValueError, match="tool messages must have tool_call_id"):
        Message(role="tool", content="result")


def test_message_tool_cannot_have_tool_calls():
    """Tool messages cannot carry tool_calls."""
    tc = ToolCall(id="tc_1", name="email.send", arguments={})
    with pytest.raises(ValueError, match="tool messages cannot have tool_calls"):
        Message(role="tool", content="result", tool_call_id="tc_1", tool_calls=[tc])


def test_message_system_cannot_have_tool_calls():
    """System messages cannot carry tool_calls."""
    tc = ToolCall(id="tc_1", name="email.send", arguments={})
    with pytest.raises(ValueError, match="system messages cannot have tool_calls"):
        Message(role="system", content="You are helpful", tool_calls=[tc])


def test_message_user_cannot_have_tool_call_id():
    """User messages cannot have tool_call_id."""
    with pytest.raises(ValueError, match="user messages cannot have tool_call_id"):
        Message(role="user", content="Hello", tool_call_id="tc_1")


def test_message_assistant_cannot_have_tool_call_id():
    """Assistant messages cannot have tool_call_id."""
    with pytest.raises(ValueError, match="assistant messages cannot have tool_call_id"):
        Message(role="assistant", content="Hi", tool_call_id="tc_1")


# ============================================================================
# Anthropic Provider Tests
# ============================================================================


SAMPLE_TOOLS = [
    {
        "name": "email.send",
        "description": "Send an email",
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


@pytest.mark.asyncio
async def test_anthropic_generate_with_tools_text_response():
    """Test Anthropic provider returns text when no tool calls."""
    from empla.llm.anthropic import AnthropicProvider

    provider = AnthropicProvider(api_key="sk-test", model_id="claude-sonnet-4")

    # Mock response with text only
    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "I'll help you with that."

    mock_response = MagicMock()
    mock_response.content = [mock_text_block]
    mock_response.model = "claude-sonnet-4"
    mock_response.stop_reason = "end_turn"
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50

    provider.client.messages.create = AsyncMock(return_value=mock_response)

    request = LLMRequest(
        messages=[Message(role="user", content="Help me")],
        tools=SAMPLE_TOOLS,
        tool_choice="auto",
    )
    response = await provider.generate_with_tools(request)

    assert response.content == "I'll help you with that."
    assert response.tool_calls is None
    assert response.finish_reason == "end_turn"


@pytest.mark.asyncio
async def test_anthropic_generate_with_tools_tool_use():
    """Test Anthropic provider parses tool_use content blocks."""
    from empla.llm.anthropic import AnthropicProvider

    provider = AnthropicProvider(api_key="sk-test", model_id="claude-sonnet-4")

    # Mock response with tool_use
    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.id = "toolu_123"
    mock_tool_block.name = "email.send"
    mock_tool_block.input = {"to": ["a@b.com"], "subject": "Hi", "body": "Hello"}

    mock_response = MagicMock()
    mock_response.content = [mock_tool_block]
    mock_response.model = "claude-sonnet-4"
    mock_response.stop_reason = "tool_use"
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50

    provider.client.messages.create = AsyncMock(return_value=mock_response)

    request = LLMRequest(
        messages=[Message(role="user", content="Send email to a@b.com")],
        tools=SAMPLE_TOOLS,
        tool_choice="auto",
    )
    response = await provider.generate_with_tools(request)

    assert response.tool_calls is not None
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "toolu_123"
    assert response.tool_calls[0].name == "email.send"
    assert response.tool_calls[0].arguments["to"] == ["a@b.com"]
    assert response.finish_reason == "tool_use"


@pytest.mark.asyncio
async def test_anthropic_tool_result_message_conversion():
    """Test Anthropic provider converts tool result messages correctly."""
    from empla.llm.anthropic import AnthropicProvider

    provider = AnthropicProvider(api_key="sk-test", model_id="claude-sonnet-4")

    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Done!"

    mock_response = MagicMock()
    mock_response.content = [mock_text_block]
    mock_response.model = "claude-sonnet-4"
    mock_response.stop_reason = "end_turn"
    mock_response.usage.input_tokens = 200
    mock_response.usage.output_tokens = 20

    provider.client.messages.create = AsyncMock(return_value=mock_response)

    # Build multi-turn conversation with tool result
    tc = ToolCall(id="toolu_123", name="email.send", arguments={"to": ["a@b.com"]})
    messages = [
        Message(role="user", content="Send email"),
        Message(role="assistant", content="", tool_calls=[tc]),
        Message(role="tool", content='{"success": true}', tool_call_id="toolu_123"),
    ]

    request = LLMRequest(messages=messages, tools=SAMPLE_TOOLS)
    await provider.generate_with_tools(request)

    # Verify the API was called with correct message format
    call_kwargs = provider.client.messages.create.call_args[1]
    api_messages = call_kwargs["messages"]

    # First message: user
    assert api_messages[0]["role"] == "user"
    # Second message: assistant with tool_use
    assert api_messages[1]["role"] == "assistant"
    assert api_messages[1]["content"][0]["type"] == "tool_use"
    # Third message: tool result as user message
    assert api_messages[2]["role"] == "user"
    assert api_messages[2]["content"][0]["type"] == "tool_result"
    assert api_messages[2]["content"][0]["tool_use_id"] == "toolu_123"


# ============================================================================
# OpenAI Provider Tests
# ============================================================================


@pytest.mark.asyncio
async def test_openai_generate_with_tools_text_response():
    """Test OpenAI provider returns text when no tool calls."""
    from empla.llm.openai import OpenAIProvider

    provider = OpenAIProvider(api_key="sk-test", model_id="gpt-4o")

    mock_message = MagicMock()
    mock_message.content = "I'll help you."
    mock_message.tool_calls = None

    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "stop"

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50
    mock_usage.total_tokens = 150

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o"
    mock_response.usage = mock_usage

    provider.client.chat.completions.create = AsyncMock(return_value=mock_response)

    request = LLMRequest(
        messages=[Message(role="user", content="Help me")],
        tools=SAMPLE_TOOLS,
        tool_choice="auto",
    )
    response = await provider.generate_with_tools(request)

    assert response.content == "I'll help you."
    assert response.tool_calls is None


@pytest.mark.asyncio
async def test_openai_generate_with_tools_tool_calls():
    """Test OpenAI provider parses function tool calls."""
    from empla.llm.openai import OpenAIProvider

    provider = OpenAIProvider(api_key="sk-test", model_id="gpt-4o")

    mock_function = MagicMock()
    mock_function.name = "email.send"
    mock_function.arguments = json.dumps({"to": ["a@b.com"], "subject": "Hi", "body": "Hello"})

    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function = mock_function

    mock_message = MagicMock()
    mock_message.content = None
    mock_message.tool_calls = [mock_tool_call]

    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "tool_calls"

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50
    mock_usage.total_tokens = 150

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o"
    mock_response.usage = mock_usage

    provider.client.chat.completions.create = AsyncMock(return_value=mock_response)

    request = LLMRequest(
        messages=[Message(role="user", content="Send email")],
        tools=SAMPLE_TOOLS,
        tool_choice="auto",
    )
    response = await provider.generate_with_tools(request)

    assert response.tool_calls is not None
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "call_123"
    assert response.tool_calls[0].name == "email.send"
    assert response.tool_calls[0].arguments["to"] == ["a@b.com"]


# ============================================================================
# LLMService Tests
# ============================================================================


@pytest.fixture
def mock_config():
    return LLMConfig(
        primary_model="claude-sonnet-4",
        fallback_model="gpt-4o",
        anthropic_api_key="sk-ant-test",
        openai_api_key="sk-test",
    )


@pytest.fixture
def mock_tool_response():
    tc = ToolCall(id="tc_1", name="email.send", arguments={"to": ["a@b.com"]})
    return LLMResponse(
        content="",
        model="claude-sonnet-4",
        usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        finish_reason="tool_use",
        tool_calls=[tc],
    )


@pytest.mark.asyncio
async def test_service_generate_with_tools_primary(mock_config, mock_tool_response):
    """Test LLMService.generate_with_tools uses primary provider."""
    with patch("empla.llm.LLMProviderFactory.create") as mock_factory:
        mock_provider = MagicMock()
        mock_provider.generate_with_tools = AsyncMock(return_value=mock_tool_response)
        mock_factory.return_value = mock_provider

        service = LLMService(mock_config)
        response = await service.generate_with_tools(
            messages=[Message(role="user", content="Send email")],
            tools=SAMPLE_TOOLS,
        )

        assert response.tool_calls is not None
        assert response.tool_calls[0].name == "email.send"
        mock_provider.generate_with_tools.assert_called_once()


@pytest.mark.asyncio
async def test_service_generate_with_tools_fallback(mock_config, mock_tool_response):
    """Test LLMService.generate_with_tools falls back on primary failure."""
    with patch("empla.llm.LLMProviderFactory.create") as mock_factory:
        primary = MagicMock()
        primary.generate_with_tools = AsyncMock(side_effect=Exception("Primary down"))

        fallback = MagicMock()
        fallback.generate_with_tools = AsyncMock(return_value=mock_tool_response)

        call_count = 0

        def create_provider(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return primary if call_count == 1 else fallback

        mock_factory.side_effect = create_provider

        service = LLMService(mock_config)
        response = await service.generate_with_tools(
            messages=[Message(role="user", content="Send email")],
            tools=SAMPLE_TOOLS,
        )

        assert response.tool_calls is not None
        fallback.generate_with_tools.assert_called_once()


@pytest.mark.asyncio
async def test_service_generate_with_tools_no_fallback_raises():
    """Test LLMService.generate_with_tools raises when no fallback."""
    no_fallback_config = LLMConfig(
        primary_model="claude-sonnet-4",
        anthropic_api_key="sk-ant-test",
    )
    with patch("empla.llm.LLMProviderFactory.create") as mock_factory:
        mock_provider = MagicMock()
        mock_provider.generate_with_tools = AsyncMock(side_effect=Exception("Fail"))
        mock_factory.return_value = mock_provider

        service = LLMService(no_fallback_config)
        with pytest.raises(Exception, match="Fail"):
            await service.generate_with_tools(
                messages=[Message(role="user", content="Send email")],
                tools=SAMPLE_TOOLS,
            )
