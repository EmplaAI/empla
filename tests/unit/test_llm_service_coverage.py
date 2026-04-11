"""
Coverage tests for empla.llm.LLMService — uncovered lines.

Focuses on:
- generate (primary success, fallback, no fallback raises)
- generate_structured (primary success, fallback, no fallback raises)
- generate_with_tools (primary success, fallback, NotImplementedError propagated, no fallback raises)
- _track_cost
- get_cost_summary
- close
- _validate_api_key
- _create_provider
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import BaseModel

from empla.llm.config import LLMConfig
from empla.llm.models import LLMResponse, Message, TokenUsage

# ============================================================================
# Helpers
# ============================================================================


def _make_response(content: str = "hello", cost_tokens: int = 100) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="test-model",
        usage=TokenUsage(
            input_tokens=cost_tokens,
            output_tokens=cost_tokens,
            total_tokens=cost_tokens * 2,
        ),
        finish_reason="end_turn",
    )


def _make_service(
    *,
    primary_fails: bool = False,
    primary_error: Exception | None = None,
    fallback: bool = True,
    fallback_fails: bool = False,
):
    """Create LLMService with mocked providers (bypass __init__)."""
    from empla.llm import LLMService

    config = LLMConfig(
        primary_model="gemini-3-flash-preview",
        fallback_model="gpt-4o" if fallback else None,
        anthropic_api_key="test-key",
        openai_api_key="test-key" if fallback else None,
    )

    # Bypass __init__ to avoid real provider creation
    service = object.__new__(LLMService)
    service.config = config
    service.total_cost = 0.0
    service.requests_count = 0
    # Attributes that would otherwise be set by __init__. We set them to
    # empty/None so internal methods that reference them don't AttributeError.
    service._router = None
    service._provider_pool = {}
    service._owner_id = "default"

    # Mock primary
    service.primary = Mock()
    if primary_fails:
        err = primary_error or RuntimeError("Primary failed")
        service.primary.generate = AsyncMock(side_effect=err)
        service.primary.generate_structured = AsyncMock(side_effect=err)
        service.primary.generate_with_tools = AsyncMock(side_effect=err)
    else:
        service.primary.generate = AsyncMock(return_value=_make_response())
        service.primary.generate_structured = AsyncMock(return_value=(_make_response(), Mock()))
        service.primary.generate_with_tools = AsyncMock(return_value=_make_response())
    service.primary.close = AsyncMock()

    # Mock fallback
    if fallback:
        service.fallback = Mock()
        if fallback_fails:
            service.fallback.generate = AsyncMock(side_effect=RuntimeError("Fallback failed"))
            service.fallback.generate_structured = AsyncMock(
                side_effect=RuntimeError("Fallback failed")
            )
            service.fallback.generate_with_tools = AsyncMock(
                side_effect=RuntimeError("Fallback failed")
            )
        else:
            service.fallback.generate = AsyncMock(return_value=_make_response("fallback"))
            service.fallback.generate_structured = AsyncMock(
                return_value=(_make_response("fallback"), Mock())
            )
            service.fallback.generate_with_tools = AsyncMock(
                return_value=_make_response("fallback")
            )
        service.fallback.close = AsyncMock()
    else:
        service.fallback = None

    return service


class SampleModel(BaseModel):
    value: str


# ============================================================================
# generate
# ============================================================================


class TestGenerate:
    @pytest.mark.asyncio
    async def test_primary_success(self):
        service = _make_service()
        result = await service.generate("test prompt")
        assert result.content == "hello"
        service.primary.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_system_message(self):
        service = _make_service()
        result = await service.generate("test", system="You are helpful")
        assert result.content == "hello"
        request = service.primary.generate.call_args[0][0]
        assert len(request.messages) == 2
        assert request.messages[0].role == "system"

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self):
        service = _make_service(primary_fails=True)
        result = await service.generate("test")
        assert result.content == "fallback"
        service.fallback.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_without_fallback(self):
        service = _make_service(primary_fails=True, fallback=False)
        with pytest.raises(RuntimeError, match="Primary failed"):
            await service.generate("test")


# ============================================================================
# generate_structured
# ============================================================================


class TestGenerateStructured:
    @pytest.mark.asyncio
    async def test_primary_success(self):
        service = _make_service()
        result, _parsed = await service.generate_structured("test", response_format=SampleModel)
        assert result.content == "hello"
        service.primary.generate_structured.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_system(self):
        service = _make_service()
        await service.generate_structured("test", response_format=SampleModel, system="sys")
        request = service.primary.generate_structured.call_args[0][0]
        assert request.messages[0].role == "system"

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self):
        service = _make_service(primary_fails=True)
        result, _ = await service.generate_structured("test", response_format=SampleModel)
        assert result.content == "fallback"

    @pytest.mark.asyncio
    async def test_raises_without_fallback(self):
        service = _make_service(primary_fails=True, fallback=False)
        with pytest.raises(RuntimeError):
            await service.generate_structured("test", response_format=SampleModel)


# ============================================================================
# generate_with_tools
# ============================================================================


class TestGenerateWithTools:
    @pytest.mark.asyncio
    async def test_primary_success(self):
        service = _make_service()
        messages = [Message(role="user", content="test")]
        tools = [{"name": "search", "description": "Search", "parameters": {}}]
        result = await service.generate_with_tools(messages, tools)
        assert result.content == "hello"

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self):
        service = _make_service(primary_fails=True)
        messages = [Message(role="user", content="test")]
        tools = [{"name": "search", "description": "Search", "parameters": {}}]
        result = await service.generate_with_tools(messages, tools)
        assert result.content == "fallback"

    @pytest.mark.asyncio
    async def test_raises_without_fallback(self):
        service = _make_service(primary_fails=True, fallback=False)
        messages = [Message(role="user", content="test")]
        tools = [{"name": "search", "description": "Search", "parameters": {}}]
        with pytest.raises(RuntimeError):
            await service.generate_with_tools(messages, tools)

    @pytest.mark.asyncio
    async def test_not_implemented_error_propagated(self):
        """NotImplementedError from primary should NOT trigger fallback."""
        service = _make_service(
            primary_fails=True,
            primary_error=NotImplementedError("No tool support"),
        )
        messages = [Message(role="user", content="test")]
        tools = [{"name": "x", "description": "x", "parameters": {}}]
        with pytest.raises(NotImplementedError):
            await service.generate_with_tools(messages, tools)
        # Fallback should NOT be called
        service.fallback.generate_with_tools.assert_not_called()


# ============================================================================
# _track_cost
# ============================================================================


class TestTrackCost:
    """Tests for _track_cost_for_model (renamed from _track_cost in LLM routing refactor)."""

    def test_tracks_primary_cost(self):
        service = _make_service()
        response = _make_response(cost_tokens=1000)
        service._track_cost_for_model(response, model_key="gemini-3-flash-preview")
        assert service.total_cost > 0
        assert service.requests_count == 1

    def test_tracks_fallback_cost(self):
        service = _make_service()
        response = _make_response(cost_tokens=1000)
        service._track_cost_for_model(response, model_key="gpt-4o")
        assert service.total_cost > 0

    def test_cost_tracking_disabled(self):
        service = _make_service()
        service.config.enable_cost_tracking = False
        response = _make_response(cost_tokens=1000)
        service._track_cost_for_model(response, model_key="gemini-3-flash-preview")
        assert service.total_cost == 0.0
        assert service.requests_count == 0

    def test_unknown_model_key_no_crash(self):
        """Unknown model key should skip cost tracking without raising."""
        service = _make_service()
        response = _make_response(cost_tokens=1000)
        service._track_cost_for_model(response, model_key="nonexistent-model")
        # Unknown model: cost skipped, no crash
        assert service.requests_count == 0


# ============================================================================
# get_cost_summary
# ============================================================================


class TestGetCostSummary:
    def test_empty_summary(self):
        service = _make_service()
        summary = service.get_cost_summary()
        assert summary["total_cost"] == 0.0
        assert summary["requests_count"] == 0
        assert summary["average_cost_per_request"] == 0.0

    def test_with_requests(self):
        service = _make_service()
        service.total_cost = 0.10
        service.requests_count = 5
        summary = service.get_cost_summary()
        assert summary["total_cost"] == 0.10
        assert summary["average_cost_per_request"] == pytest.approx(0.02)


# ============================================================================
# close
# ============================================================================


class TestClose:
    @pytest.mark.asyncio
    async def test_closes_both_providers(self):
        service = _make_service()
        await service.close()
        service.primary.close.assert_called_once()
        service.fallback.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_closes_without_fallback(self):
        service = _make_service(fallback=False)
        await service.close()
        service.primary.close.assert_called_once()


# ============================================================================
# _validate_api_key
# ============================================================================


class TestValidateApiKey:
    def test_anthropic_missing(self):
        service = _make_service()
        service.config.anthropic_api_key = None
        with pytest.raises(ValueError, match="anthropic_api_key"):
            service._validate_api_key("anthropic")

    def test_openai_missing(self):
        service = _make_service()
        service.config.openai_api_key = None
        with pytest.raises(ValueError, match="openai_api_key"):
            service._validate_api_key("openai")

    def test_azure_missing(self):
        service = _make_service()
        service.config.azure_openai_api_key = None
        with pytest.raises(ValueError, match="azure_openai_api_key"):
            service._validate_api_key("azure_openai")

    def test_valid_key_passes(self):
        service = _make_service()
        service.config.anthropic_api_key = "sk-test"
        # Should not raise
        service._validate_api_key("anthropic")


# ============================================================================
# _create_provider
# ============================================================================


class TestCreateProvider:
    def test_unsupported_provider_raises(self):
        service = _make_service()
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            service._create_provider("unknown_provider", "model-id")

    @patch("empla.llm.LLMProviderFactory.create")
    def test_creates_anthropic(self, mock_create):
        service = _make_service()
        service.config.anthropic_api_key = "sk-test"
        service._create_provider("anthropic", "claude-sonnet-4-20250514")
        mock_create.assert_called_once()

    @patch("empla.llm.LLMProviderFactory.create")
    def test_creates_openai(self, mock_create):
        service = _make_service()
        service.config.openai_api_key = "sk-test"
        service._create_provider("openai", "gpt-4o")
        mock_create.assert_called_once()

    @patch("empla.llm.LLMProviderFactory.create")
    def test_creates_vertex(self, mock_create):
        service = _make_service()
        service._create_provider("vertex", "gemini-1.5-pro")
        mock_create.assert_called_once()

    @patch("empla.llm.LLMProviderFactory.create")
    def test_creates_azure_openai(self, mock_create):
        service = _make_service()
        service.config.azure_openai_api_key = "key"
        service.config.azure_openai_endpoint = "https://test.openai.azure.com"
        service.config.azure_openai_deployment = "deploy"
        service._create_provider("azure_openai", "gpt-4o")
        mock_create.assert_called_once()
