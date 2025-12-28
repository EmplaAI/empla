"""
empla.llm - Multi-provider LLM service.

This package provides a unified interface for working with multiple LLM providers
(Anthropic, OpenAI, Google Vertex AI) with automatic fallback and cost tracking.

Example:
    >>> from empla.llm import LLMService
    >>> from empla.llm.config import LLMConfig
    >>>
    >>> config = LLMConfig(
    ...     primary_model="claude-sonnet-4",
    ...     fallback_model="gpt-4o",
    ...     anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    ...     openai_api_key=os.getenv("OPENAI_API_KEY"),
    ... )
    >>> llm = LLMService(config)
    >>>
    >>> # Generate text
    >>> response = await llm.generate("Analyze this situation...")
    >>> print(response.content)
    >>>
    >>> # Generate structured output
    >>> from pydantic import BaseModel
    >>> class Belief(BaseModel):
    ...     subject: str
    ...     confidence: float
    >>>
    >>> response, belief = await llm.generate_structured(
    ...     "Extract belief from: Customer is interested",
    ...     response_format=Belief,
    ... )
"""

import logging
from collections.abc import AsyncIterator
from typing import Optional

from pydantic import BaseModel

from empla.llm.config import MODELS, LLMConfig
from empla.llm.models import LLMRequest, LLMResponse, Message
from empla.llm.provider import LLMProviderFactory

logger = logging.getLogger(__name__)


class LLMService:
    """
    Multi-provider LLM service with fallback and cost tracking.

    This service provides a unified interface for working with multiple LLM providers.
    It automatically falls back to a secondary provider if the primary fails, and
    tracks costs across all requests.

    Attributes:
        config: LLM configuration
        primary: Primary LLM provider
        fallback: Fallback LLM provider (optional)
        total_cost: Total cost of all requests in USD
        requests_count: Total number of requests made
    """

    def __init__(self, config: LLMConfig):
        """
        Initialize LLM service.

        Args:
            config: LLM configuration
        """
        self.config = config

        # Initialize primary provider
        primary_model = MODELS[config.primary_model]
        self.primary = self._create_provider(primary_model.provider.value, primary_model.model_id)

        # Initialize fallback provider (if configured)
        self.fallback = None
        if config.fallback_model:
            fallback_model = MODELS[config.fallback_model]
            self.fallback = self._create_provider(
                fallback_model.provider.value, fallback_model.model_id
            )

        # Cost tracking
        self.total_cost = 0.0
        self.requests_count = 0

    def _create_provider(self, provider: str, model_id: str):
        """
        Create provider instance.

        Args:
            provider: Provider name
            model_id: Model identifier

        Returns:
            Configured provider instance
        """
        if provider == "anthropic":
            return LLMProviderFactory.create(
                provider="anthropic",
                api_key=self.config.anthropic_api_key,
                model_id=model_id,
            )
        if provider == "openai":
            return LLMProviderFactory.create(
                provider="openai",
                api_key=self.config.openai_api_key,
                model_id=model_id,
            )
        if provider == "azure_openai":
            return LLMProviderFactory.create(
                provider="azure_openai",
                api_key=self.config.azure_openai_api_key,
                model_id=model_id,
                azure_endpoint=self.config.azure_openai_endpoint,
                deployment_name=self.config.azure_openai_deployment,
                api_version=self.config.azure_openai_api_version,
            )
        if provider == "vertex":
            return LLMProviderFactory.create(
                provider="vertex",
                api_key="",  # Vertex uses application default credentials
                model_id=model_id,
                project_id=self.config.vertex_project_id,
                location=self.config.vertex_location,
            )
        raise ValueError(
            f"Unsupported LLM provider: {provider}. "
            "Supported providers: anthropic, openai, azure_openai, vertex"
        )

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Generate completion.

        Automatically falls back to secondary provider if primary fails.

        Args:
            prompt: User prompt
            system: System message (optional)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-2.0)

        Returns:
            LLM response

        Example:
            >>> response = await llm.generate(
            ...     "Analyze the customer's sentiment",
            ...     system="You are a sales AI assistant",
            ... )
            >>> print(response.content)
        """
        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))

        request = LLMRequest(messages=messages, max_tokens=max_tokens, temperature=temperature)

        # Try primary provider
        try:
            response = await self.primary.generate(request)
            self._track_cost(response, is_primary=True)
            return response

        except Exception as e:
            logger.error(f"Primary provider failed: {e}")

            # Fallback to secondary provider
            if self.fallback:
                logger.info("Falling back to secondary provider")
                response = await self.fallback.generate(request)
                self._track_cost(response, is_primary=False)
                return response
            raise

    async def generate_structured(
        self,
        prompt: str,
        response_format: type[BaseModel],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> tuple[LLMResponse, BaseModel]:
        """
        Generate structured output (Pydantic model).

        Args:
            prompt: User prompt
            response_format: Pydantic model class for output
            system: System message (optional)
            max_tokens: Maximum tokens
            temperature: Sampling temperature

        Returns:
            Tuple of (LLM response, parsed output)

        Example:
            >>> from pydantic import BaseModel
            >>> class Sentiment(BaseModel):
            ...     label: str
            ...     score: float
            >>>
            >>> response, sentiment = await llm.generate_structured(
            ...     "The customer loves our product!",
            ...     response_format=Sentiment,
            ... )
            >>> print(sentiment.label, sentiment.score)
        """
        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))

        request = LLMRequest(messages=messages, max_tokens=max_tokens, temperature=temperature)

        # Try primary provider
        try:
            response, parsed = await self.primary.generate_structured(request, response_format)
            self._track_cost(response, is_primary=True)
            return response, parsed

        except Exception as e:
            logger.error(f"Primary provider failed: {e}")

            if self.fallback:
                logger.info("Falling back to secondary provider")
                response, parsed = await self.fallback.generate_structured(request, response_format)
                self._track_cost(response, is_primary=False)
                return response, parsed
            raise

    async def stream(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """
        Stream completion.

        Args:
            prompt: User prompt
            system: System message (optional)
            max_tokens: Maximum tokens
            temperature: Sampling temperature

        Yields:
            Content chunks as they arrive

        Example:
            >>> async for chunk in llm.stream("Write a story"):
            ...     print(chunk, end="", flush=True)
        """
        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))

        request = LLMRequest(messages=messages, max_tokens=max_tokens, temperature=temperature)

        async for chunk in self.primary.stream(request):
            yield chunk

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings.

        Uses OpenAI embeddings (text-embedding-3-large) as default.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors

        Example:
            >>> embeddings = await llm.embed([
            ...     "First document",
            ...     "Second document",
            ... ])
            >>> len(embeddings)
            2
        """
        # For embeddings, use OpenAI (Anthropic doesn't provide embeddings)
        # If primary is OpenAI, use it; otherwise use fallback or create OpenAI provider
        if hasattr(self.primary, "embed"):
            try:
                return await self.primary.embed(texts)
            except NotImplementedError:
                pass

        # Use fallback if available
        if self.fallback and hasattr(self.fallback, "embed"):
            try:
                return await self.fallback.embed(texts)
            except NotImplementedError:
                pass

        # Create temporary OpenAI provider for embeddings
        from empla.llm.openai import OpenAIProvider

        openai_provider = OpenAIProvider(
            api_key=self.config.openai_api_key,
            model_id=self.config.embedding_model,
        )
        return await openai_provider.embed(texts)

    def _track_cost(self, response: LLMResponse, is_primary: bool = True):
        """
        Track cost of LLM call.

        Args:
            response: LLM response
            is_primary: Whether this was the primary provider
        """
        if not self.config.enable_cost_tracking:
            return

        # Find model config to calculate cost
        model_key = self.config.primary_model if is_primary else self.config.fallback_model
        model_config = MODELS.get(model_key)

        if model_config:
            cost = response.usage.calculate_cost(model_config)
            self.total_cost += cost
            self.requests_count += 1

            logger.debug(
                f"LLM call cost: ${cost:.4f} "
                f"(total: ${self.total_cost:.2f}, requests: {self.requests_count})"
            )

    def get_cost_summary(self) -> dict:
        """
        Get cost summary.

        Returns:
            Dictionary with cost statistics

        Example:
            >>> summary = llm.get_cost_summary()
            >>> print(f"Total spent: ${summary['total_cost']:.2f}")
        """
        return {
            "total_cost": self.total_cost,
            "requests_count": self.requests_count,
            "average_cost_per_request": (
                self.total_cost / self.requests_count if self.requests_count > 0 else 0.0
            ),
        }


# Export main classes
__all__ = [
    "MODELS",
    "LLMConfig",
    "LLMService",
    "LLMProviderFactory",
]
