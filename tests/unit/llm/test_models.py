"""
Unit tests for LLM models.

Tests the shared data models used across providers.
"""

import pytest
from pydantic import ValidationError

from empla.llm.config import MODELS
from empla.llm.models import LLMModel, LLMProvider, LLMRequest, Message, TokenUsage


def test_message_validation():
    """Test Message model validation."""
    msg = Message(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"


def test_message_invalid_role():
    """Test Message rejects invalid roles."""
    with pytest.raises(ValidationError):
        Message(role="invalid", content="Hello")


def test_token_usage_calculate_cost():
    """Test TokenUsage cost calculation."""
    usage = TokenUsage(input_tokens=1000, output_tokens=2000, total_tokens=3000)

    model = LLMModel(
        provider=LLMProvider.ANTHROPIC,
        model_id="claude-sonnet-4",
        input_cost_per_1m=3.00,
        output_cost_per_1m=15.00,
    )

    cost = usage.calculate_cost(model)

    # (1000/1M * $3) + (2000/1M * $15) = $0.003 + $0.03 = $0.033
    assert abs(cost - 0.033) < 0.0001


def test_llm_request_creation():
    """Test LLMRequest can be created."""
    request = LLMRequest(
        messages=[Message(role="user", content="Test")],
        max_tokens=2048,
        temperature=0.5,
    )

    assert len(request.messages) == 1
    assert request.max_tokens == 2048
    assert request.temperature == 0.5


def test_llm_request_defaults():
    """Test LLMRequest uses default values."""
    request = LLMRequest(messages=[Message(role="user", content="Test")])

    assert request.max_tokens == 4096  # Default
    assert request.temperature == 0.7  # Default
    assert request.stop_sequences is None  # Default


def test_pre_configured_models_exist():
    """Test pre-configured models are available."""
    assert "claude-sonnet-4" in MODELS
    assert "gpt-4o" in MODELS
    assert "gemini-1.5-pro" in MODELS


def test_pre_configured_model_has_pricing():
    """Test pre-configured models have pricing info."""
    model = MODELS["claude-sonnet-4"]

    assert model.provider == LLMProvider.ANTHROPIC
    assert model.input_cost_per_1m > 0
    assert model.output_cost_per_1m > 0
