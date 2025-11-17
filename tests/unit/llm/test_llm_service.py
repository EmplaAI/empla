"""
Unit tests for LLMService.

Tests the main LLM service with fallback logic and cost tracking.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from empla.llm import LLMService
from empla.llm.config import LLMConfig
from empla.llm.models import LLMResponse, TokenUsage


class BeliefModel(BaseModel):
    """Pydantic model for structured output tests."""

    subject: str
    confidence: float


@pytest.fixture
def mock_config():
    """Create mock LLM configuration."""
    return LLMConfig(
        primary_model="claude-sonnet-4",
        fallback_model="gpt-4o",
        anthropic_api_key="sk-ant-test",
        openai_api_key="sk-test",
    )


@pytest.fixture
def mock_response():
    """Create mock LLM response."""
    return LLMResponse(
        content="Test response content",
        model="claude-sonnet-4",
        usage=TokenUsage(input_tokens=100, output_tokens=200, total_tokens=300),
        finish_reason="stop",
    )


@pytest.mark.asyncio
async def test_llm_service_initialization(mock_config):
    """Test LLM service initializes correctly."""
    with patch("empla.llm.LLMProviderFactory.create") as mock_factory:
        mock_factory.return_value = MagicMock()

        service = LLMService(mock_config)

        assert service.config == mock_config
        assert service.primary is not None
        assert service.fallback is not None
        assert service.total_cost == 0.0
        assert service.requests_count == 0


@pytest.mark.asyncio
async def test_generate_uses_primary_provider(mock_config, mock_response):
    """Test generate uses primary provider when it succeeds."""
    with patch("empla.llm.LLMProviderFactory.create") as mock_factory:
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)
        mock_factory.return_value = mock_provider

        service = LLMService(mock_config)
        response = await service.generate("Test prompt")

        assert response == mock_response
        mock_provider.generate.assert_called_once()


@pytest.mark.asyncio
async def test_generate_falls_back_on_primary_failure(mock_config, mock_response):
    """Test generate falls back to secondary provider when primary fails."""
    with patch("empla.llm.LLMProviderFactory.create") as mock_factory:
        # Primary provider fails
        mock_primary = MagicMock()
        mock_primary.generate = AsyncMock(side_effect=Exception("API error"))

        # Fallback provider succeeds
        mock_fallback = MagicMock()
        mock_fallback.generate = AsyncMock(return_value=mock_response)

        # Return primary first, then fallback
        mock_factory.side_effect = [mock_primary, mock_fallback]

        service = LLMService(mock_config)
        response = await service.generate("Test prompt")

        assert response == mock_response
        mock_primary.generate.assert_called_once()
        mock_fallback.generate.assert_called_once()


@pytest.mark.asyncio
async def test_generate_raises_when_both_providers_fail(mock_config):
    """Test generate raises exception when both providers fail."""
    with patch("empla.llm.LLMProviderFactory.create") as mock_factory:
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(side_effect=Exception("API error"))
        mock_factory.return_value = mock_provider

        service = LLMService(mock_config)

        with pytest.raises(Exception, match="API error"):
            await service.generate("Test prompt")


@pytest.mark.asyncio
async def test_generate_structured_returns_parsed_output(mock_config):
    """Test generate_structured returns parsed Pydantic model."""
    mock_belief = BeliefModel(subject="test", confidence=0.8)
    mock_resp = LLMResponse(
        content='{"subject": "test", "confidence": 0.8}',
        model="claude-sonnet-4",
        usage=TokenUsage(input_tokens=50, output_tokens=20, total_tokens=70),
        finish_reason="stop",
        structured_output=mock_belief,
    )

    with patch("empla.llm.LLMProviderFactory.create") as mock_factory:
        mock_provider = MagicMock()
        mock_provider.generate_structured = AsyncMock(return_value=(mock_resp, mock_belief))
        mock_factory.return_value = mock_provider

        service = LLMService(mock_config)
        response, belief = await service.generate_structured(
            "Test prompt", response_format=BeliefModel
        )

        assert response == mock_resp
        assert belief == mock_belief
        assert belief.subject == "test"
        assert belief.confidence == 0.8


@pytest.mark.asyncio
async def test_cost_tracking_enabled(mock_config, mock_response):
    """Test cost tracking works when enabled."""
    with patch("empla.llm.LLMProviderFactory.create") as mock_factory:
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)
        mock_factory.return_value = mock_provider

        service = LLMService(mock_config)
        await service.generate("Test prompt")

        assert service.total_cost > 0.0
        assert service.requests_count == 1

        summary = service.get_cost_summary()
        assert summary["total_cost"] > 0.0
        assert summary["requests_count"] == 1
        assert summary["average_cost_per_request"] > 0.0


@pytest.mark.asyncio
async def test_cost_tracking_disabled(mock_config, mock_response):
    """Test cost tracking can be disabled."""
    mock_config.enable_cost_tracking = False

    with patch("empla.llm.LLMProviderFactory.create") as mock_factory:
        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)
        mock_factory.return_value = mock_provider

        service = LLMService(mock_config)
        await service.generate("Test prompt")

        assert service.total_cost == 0.0  # Not tracked
        assert service.requests_count == 0


@pytest.mark.asyncio
async def test_stream_yields_chunks(mock_config):
    """Test stream yields content chunks."""

    async def mock_stream_gen(*args, **kwargs):
        """Mock stream generator."""
        for chunk in ["Hello", " ", "world", "!"]:
            yield chunk

    with patch("empla.llm.LLMProviderFactory.create") as mock_factory:
        mock_provider = MagicMock()
        # stream() should return the async generator itself, not a call to it
        mock_provider.stream = mock_stream_gen
        mock_factory.return_value = mock_provider

        service = LLMService(mock_config)
        chunks = []
        async for chunk in service.stream("Test prompt"):
            chunks.append(chunk)

        assert "".join(chunks) == "Hello world!"


@pytest.mark.asyncio
async def test_embed_uses_openai_provider(mock_config):
    """Test embed uses OpenAI provider for embeddings."""
    mock_embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    with patch("empla.llm.LLMProviderFactory.create") as mock_factory:
        # Primary provider (Anthropic) doesn't support embeddings
        mock_primary = MagicMock()
        mock_primary.embed = AsyncMock(
            side_effect=NotImplementedError("Anthropic doesn't provide embeddings")
        )

        # Fallback provider (OpenAI) supports embeddings
        mock_fallback = MagicMock()
        mock_fallback.embed = AsyncMock(return_value=mock_embeddings)

        mock_factory.side_effect = [mock_primary, mock_fallback]

        service = LLMService(mock_config)
        embeddings = await service.embed(["text1", "text2"])

        assert embeddings == mock_embeddings
