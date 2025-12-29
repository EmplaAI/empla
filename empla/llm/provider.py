"""
Abstract LLM provider interface.

This module defines the base interface that all LLM providers must implement.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from empla.llm.models import LLMRequest, LLMResponse


class LLMProviderBase(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, api_key: str, model_id: str, **kwargs: Any) -> None:
        self.api_key = api_key
        self.model_id = model_id
        self.kwargs = kwargs

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generate completion.

        Args:
            request: LLM request with messages and parameters

        Returns:
            LLM response with content and metadata
        """

    @abstractmethod
    async def generate_structured(
        self, request: LLMRequest, response_format: type[BaseModel]
    ) -> tuple[LLMResponse, BaseModel]:
        """
        Generate structured output (Pydantic model).

        Uses provider's native structured output if available,
        otherwise falls back to JSON mode + parsing.

        Args:
            request: LLM request
            response_format: Pydantic model class for output

        Returns:
            Tuple of (LLM response, parsed structured output)
        """

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Stream completion.

        Args:
            request: LLM request

        Yields:
            Content chunks as they arrive
        """

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """


class LLMProviderFactory:
    """Factory for creating LLM providers."""

    @staticmethod
    def create(provider: str, api_key: str, model_id: str, **kwargs: Any) -> LLMProviderBase:
        """
        Create LLM provider.

        Args:
            provider: Provider name ("anthropic", "openai", "azure_openai", "vertex")
            api_key: API key for provider
            model_id: Model identifier
            **kwargs: Additional provider-specific config
                For azure_openai: azure_endpoint, deployment_name, api_version

        Returns:
            Configured LLM provider instance

        Raises:
            ValueError: If provider is unknown
        """
        from empla.llm.anthropic import AnthropicProvider
        from empla.llm.azure_openai import AzureOpenAIProvider
        from empla.llm.openai import OpenAIProvider
        from empla.llm.vertex import VertexAIProvider

        providers = {
            "anthropic": AnthropicProvider,
            "openai": OpenAIProvider,
            "azure_openai": AzureOpenAIProvider,
            "vertex": VertexAIProvider,
        }

        if provider not in providers:
            raise ValueError(
                f"Unknown provider: {provider}. Supported providers: {', '.join(providers.keys())}"
            )

        return providers[provider](api_key=api_key, model_id=model_id, **kwargs)
