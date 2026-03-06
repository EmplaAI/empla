"""
empla.llm - Multi-provider LLM service.

This package provides a unified interface for working with multiple LLM providers
(Anthropic, OpenAI, Google Vertex AI) with automatic fallback, cost tracking,
and optional rule-based routing.

Example:
    >>> from empla.llm import LLMService
    >>> from empla.llm.config import LLMConfig, RoutingPolicy
    >>>
    >>> config = LLMConfig(
    ...     primary_model="claude-sonnet-4",
    ...     fallback_model="gpt-4o",
    ...     routing_policy=RoutingPolicy(enabled=True),
    ...     anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    ...     openai_api_key=os.getenv("OPENAI_API_KEY"),
    ... )
    >>> llm = LLMService(config)
    >>>
    >>> # Generate text (backwards compatible — routing not used)
    >>> response = await llm.generate("Analyze this situation...")
    >>>
    >>> # Generate with routing context
    >>> from empla.llm import TaskContext, TaskType
    >>> response = await llm.generate(
    ...     "Extract beliefs from this observation...",
    ...     task_context=TaskContext(
    ...         task_type=TaskType.BELIEF_EXTRACTION,
    ...         priority=5,
    ...         quality_threshold=0.5,
    ...     ),
    ... )
"""

import logging
from collections.abc import AsyncIterator
from typing import Any, Literal, cast

from pydantic import BaseModel

from empla.llm.config import MODELS, LLMConfig
from empla.llm.models import (
    LLMRequest,
    LLMResponse,
    Message,
    RouterDecision,
    TaskContext,
    TaskType,
    ToolCall,
)
from empla.llm.provider import LLMProviderBase, LLMProviderFactory
from empla.llm.router import LLMRouter

logger = logging.getLogger(__name__)


class LLMService:
    """
    Multi-provider LLM service with fallback, cost tracking, and optional routing.

    When ``config.routing_policy`` is set and enabled, the service maintains a
    provider pool for all configured models and uses ``LLMRouter`` to select the
    most cost-effective model for each call based on ``TaskContext``.

    When ``task_context=None`` (default), behaviour is identical to the original
    implementation — primary provider is used with fallback on failure.

    Attributes:
        config: LLM configuration
        primary: Primary LLM provider (legacy path)
        fallback: Fallback LLM provider (legacy path, optional)
        total_cost: Total cost of all requests in USD
        requests_count: Total number of requests made
    """

    def __init__(self, config: LLMConfig) -> None:
        """
        Initialize LLM service.

        Args:
            config: LLM configuration

        Raises:
            ValueError: If required API key is missing for configured provider
        """
        self.config = config

        # Initialize primary provider (legacy path)
        primary_model = MODELS[config.primary_model]
        self._validate_api_key(primary_model.provider.value)
        self.primary = self._create_provider(primary_model.provider.value, primary_model.model_id)

        # Initialize fallback provider (legacy path, if configured)
        self.fallback = None
        if config.fallback_model:
            fallback_model = MODELS[config.fallback_model]
            self._validate_api_key(fallback_model.provider.value)
            self.fallback = self._create_provider(
                fallback_model.provider.value, fallback_model.model_id
            )

        # Build provider pool (routing path) — lazily skips models without API keys.
        # primary and fallback providers are reused in the pool to avoid duplicate connections.
        self._provider_pool: dict[str, LLMProviderBase] = {}
        self._router: LLMRouter | None = None
        if config.routing_policy and config.routing_policy.enabled:
            self._build_provider_pool()
            self._router = LLMRouter(
                policy=config.routing_policy,
                provider_pool=self._provider_pool,
            )

        # Cost tracking
        self.total_cost = 0.0
        self.requests_count = 0

    # =========================================================================
    # Provider management
    # =========================================================================

    def _build_provider_pool(self) -> None:
        """Build the provider pool for all models that have API keys configured.

        Reuses the already-created primary and fallback provider instances
        to avoid opening duplicate HTTP connections to the same API.
        """
        for model_key, model_config in MODELS.items():
            # Reuse existing providers to avoid duplicate connections
            if model_key == self.config.primary_model:
                self._provider_pool[model_key] = self.primary
                continue
            if model_key == self.config.fallback_model and self.fallback is not None:
                self._provider_pool[model_key] = self.fallback
                continue

            provider_name = model_config.provider.value
            try:
                self._validate_api_key(provider_name)
            except ValueError:
                # No API key for this provider — skip silently
                continue
            try:
                provider = self._create_provider(provider_name, model_config.model_id)
                self._provider_pool[model_key] = provider
            except Exception as e:
                logger.debug(f"Skipping model {model_key} in pool: {e}")

    def _validate_api_key(self, provider: str) -> None:
        """
        Validate that required API key is configured for the provider.

        Args:
            provider: Provider name

        Raises:
            ValueError: If required API key is missing
        """
        if provider == "anthropic" and not self.config.anthropic_api_key:
            raise ValueError(
                "anthropic_api_key is required for Anthropic provider. "
                "Set ANTHROPIC_API_KEY environment variable or pass in config."
            )
        if provider == "openai" and not self.config.openai_api_key:
            raise ValueError(
                "openai_api_key is required for OpenAI provider. "
                "Set OPENAI_API_KEY environment variable or pass in config."
            )
        if provider == "azure_openai" and not self.config.azure_openai_api_key:
            raise ValueError(
                "azure_openai_api_key is required for Azure OpenAI provider. "
                "Set AZURE_OPENAI_API_KEY environment variable or pass in config."
            )

    def _create_provider(self, provider: str, model_id: str) -> LLMProviderBase:
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
                api_key=self.config.anthropic_api_key,  # type: ignore[arg-type]
                model_id=model_id,
            )
        if provider == "openai":
            return LLMProviderFactory.create(
                provider="openai",
                api_key=self.config.openai_api_key,  # type: ignore[arg-type]
                model_id=model_id,
            )
        if provider == "azure_openai":
            return LLMProviderFactory.create(
                provider="azure_openai",
                api_key=self.config.azure_openai_api_key,  # type: ignore[arg-type]
                model_id=model_id,
                azure_endpoint=self.config.azure_openai_endpoint,
                deployment_name=self.config.azure_openai_deployment,
                api_version=self.config.azure_openai_api_version,
            )
        if provider == "vertex":
            return LLMProviderFactory.create(
                provider="vertex",
                api_key="",
                model_id=model_id,
                project_id=self.config.vertex_project_id,
                location=self.config.vertex_location,
            )
        raise ValueError(
            f"Unsupported LLM provider: {provider}. "
            "Supported providers: anthropic, openai, azure_openai, vertex"
        )

    def _get_provider_for_context(
        self, task_context: TaskContext | None
    ) -> tuple[LLMProviderBase, str]:
        """
        Select provider and model key for a call.

        Uses the router when task_context is provided and routing is enabled.
        Falls back to the legacy primary provider otherwise.

        Returns:
            (provider, model_key)
        """
        if task_context is not None and self._router is not None:
            decision = self._router.route(task_context)
            provider = self._provider_pool.get(decision.model_key)
            if provider is not None:
                return provider, decision.model_key
            # Router returned a model not in pool (shouldn't happen) — fall through
            logger.warning(
                f"Router selected {decision.model_key} but it's not in provider pool"
            )
        return self.primary, self.config.primary_model

    def _get_fallback_provider(
        self, failed_model_key: str, task_context: TaskContext | None
    ) -> tuple[LLMProviderBase, str] | None:
        """
        Get fallback provider after a failure.

        With routing enabled: records the failure, then re-routes with
        retry_count+1 to trigger tier escalation.
        Without routing: uses the legacy fallback provider.

        Returns:
            (provider, model_key) or None if no fallback available
        """
        if task_context is not None and self._router is not None:
            self._router.record_failure(failed_model_key)
            escalated = TaskContext(
                task_type=task_context.task_type,
                priority=task_context.priority,
                estimated_input_tokens=task_context.estimated_input_tokens,
                requires_tool_use=task_context.requires_tool_use,
                requires_structured_output=task_context.requires_structured_output,
                latency_sensitive=task_context.latency_sensitive,
                quality_threshold=task_context.quality_threshold,
                retry_count=task_context.retry_count + 1,
            )
            decision = self._router.route(escalated)
            if decision.model_key != failed_model_key:
                provider = self._provider_pool.get(decision.model_key)
                if provider is not None:
                    return provider, decision.model_key

        if self.fallback:
            return self.fallback, self.config.fallback_model or ""
        return None

    # =========================================================================
    # Public generate_* methods
    # =========================================================================

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        task_context: TaskContext | None = None,
    ) -> LLMResponse:
        """
        Generate completion.

        Automatically falls back to secondary provider if primary fails.

        Args:
            prompt: User prompt
            system: System message (optional)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-2.0)
            task_context: Routing context (optional; uses primary when omitted)

        Returns:
            LLM response
        """
        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))

        request = LLMRequest(messages=messages, max_tokens=max_tokens, temperature=temperature)

        provider, model_key = self._get_provider_for_context(task_context)
        try:
            response = await provider.generate(request)
            self._track_cost_for_model(response, model_key)
            if self._router:
                self._router.record_success(model_key)
                self._router.record_cost(model_key, response.usage)
            return response

        except Exception as e:
            logger.error(f"Provider {model_key} failed: {e}")
            fallback = self._get_fallback_provider(model_key, task_context)
            if fallback:
                fb_provider, fb_key = fallback
                logger.info(f"Falling back to {fb_key}")
                response = await fb_provider.generate(request)
                self._track_cost_for_model(response, fb_key)
                if self._router:
                    self._router.record_success(fb_key)
                    self._router.record_cost(fb_key, response.usage)
                return response
            raise

    async def generate_structured(
        self,
        prompt: str,
        response_format: type[BaseModel],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        task_context: TaskContext | None = None,
    ) -> tuple[LLMResponse, BaseModel]:
        """
        Generate structured output (Pydantic model).

        Args:
            prompt: User prompt
            response_format: Pydantic model class for output
            system: System message (optional)
            max_tokens: Maximum tokens
            temperature: Sampling temperature
            task_context: Routing context (optional)

        Returns:
            Tuple of (LLM response, parsed output)
        """
        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))

        request = LLMRequest(messages=messages, max_tokens=max_tokens, temperature=temperature)

        provider, model_key = self._get_provider_for_context(task_context)
        try:
            response, parsed = await provider.generate_structured(request, response_format)
            self._track_cost_for_model(response, model_key)
            if self._router:
                self._router.record_success(model_key)
                self._router.record_cost(model_key, response.usage)
            return response, parsed

        except Exception as e:
            logger.error(f"Provider {model_key} failed: {e}")
            fallback = self._get_fallback_provider(model_key, task_context)
            if fallback:
                fb_provider, fb_key = fallback
                logger.info(f"Falling back to {fb_key}")
                response, parsed = await fb_provider.generate_structured(request, response_format)
                self._track_cost_for_model(response, fb_key)
                if self._router:
                    self._router.record_success(fb_key)
                    self._router.record_cost(fb_key, response.usage)
                return response, parsed
            raise

    async def generate_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        task_context: TaskContext | None = None,
    ) -> LLMResponse:
        """
        Generate with function calling. Returns response that may contain tool_calls.

        Args:
            messages: Conversation messages (including tool results)
            tools: Tool schemas for function calling
            tool_choice: "auto", "required", or "none"
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            task_context: Routing context (optional)

        Returns:
            LLM response, potentially with tool_calls
        """
        request = LLMRequest(
            messages=messages,
            tools=tools,
            tool_choice=cast(Literal["auto", "required", "none"] | None, tool_choice),
            max_tokens=max_tokens,
            temperature=temperature,
        )

        provider, model_key = self._get_provider_for_context(task_context)
        try:
            response = await provider.generate_with_tools(request)
            self._track_cost_for_model(response, model_key)
            if self._router:
                self._router.record_success(model_key)
                self._router.record_cost(model_key, response.usage)
            return response

        except NotImplementedError:
            raise

        except Exception:
            logger.error(f"Provider {model_key} failed for generate_with_tools", exc_info=True)
            fallback = self._get_fallback_provider(model_key, task_context)
            if fallback:
                fb_provider, fb_key = fallback
                logger.info(f"Falling back to {fb_key} for generate_with_tools")
                response = await fb_provider.generate_with_tools(request)
                self._track_cost_for_model(response, fb_key)
                if self._router:
                    self._router.record_success(fb_key)
                    self._router.record_cost(fb_key, response.usage)
                return response
            raise

    async def stream(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        task_context: TaskContext | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream completion.

        Args:
            prompt: User prompt
            system: System message (optional)
            max_tokens: Maximum tokens
            temperature: Sampling temperature
            task_context: Routing context (optional)

        Yields:
            Content chunks as they arrive

        Note:
            Streaming calls use the router for model selection but do not update
            the router's cost tracking or circuit breaker state, because token
            counts are only known after the stream is fully consumed. If accurate
            budget accounting is required, use ``generate()`` instead.
        """
        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))

        request = LLMRequest(messages=messages, max_tokens=max_tokens, temperature=temperature)

        provider, _ = self._get_provider_for_context(task_context)
        async for chunk in provider.stream(request):  # type: ignore[attr-defined]
            yield chunk

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings.

        Uses OpenAI embeddings (text-embedding-3-large) as default.
        Falls back to creating a temporary OpenAI provider if primary/fallback
        don't support embeddings.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors

        Raises:
            ValueError: If OpenAI API key or embedding model is not configured
                when falling back to OpenAI for embeddings
        """
        if hasattr(self.primary, "embed"):
            try:
                return await self.primary.embed(texts)
            except NotImplementedError:
                pass

        if self.fallback and hasattr(self.fallback, "embed"):
            try:
                return await self.fallback.embed(texts)
            except NotImplementedError:
                pass

        if not self.config.openai_api_key:
            raise ValueError(
                "openai_api_key is required for embeddings when primary/fallback "
                "providers don't support embed(). Set OPENAI_API_KEY environment "
                "variable or pass in config."
            )
        if not self.config.embedding_model:
            raise ValueError(
                "embedding_model is required for embeddings. "
                "Set a valid OpenAI embedding model (e.g., 'text-embedding-3-large')."
            )

        from empla.llm.openai import OpenAIProvider

        openai_provider = OpenAIProvider(
            api_key=self.config.openai_api_key,
            model_id=self.config.embedding_model,
        )
        return await openai_provider.embed(texts)

    # =========================================================================
    # Cost tracking
    # =========================================================================

    def _track_cost_for_model(self, response: LLMResponse, model_key: str) -> None:
        """
        Track cost of LLM call for a specific model key.

        Args:
            response: LLM response
            model_key: Key identifying the model used
        """
        if not self.config.enable_cost_tracking:
            return

        model_config = MODELS.get(model_key)
        if model_config:
            cost = response.usage.calculate_cost(model_config)
            self.total_cost += cost
            self.requests_count += 1

            logger.debug(
                f"LLM call cost: ${cost:.4f} "
                f"(model: {model_key}, total: ${self.total_cost:.2f}, "
                f"requests: {self.requests_count})"
            )

    def get_cost_summary(self) -> dict[str, Any]:
        """
        Get cost summary.

        Returns:
            Dictionary with cost statistics
        """
        summary: dict[str, Any] = {
            "total_cost": self.total_cost,
            "requests_count": self.requests_count,
            "average_cost_per_request": (
                self.total_cost / self.requests_count if self.requests_count > 0 else 0.0
            ),
        }
        if self._router:
            summary["routing"] = self._router.get_budget_state()
        return summary

    async def close(self) -> None:
        """
        Close the LLM service and release resources.

        Closes all underlying provider connections (HTTP clients, etc.),
        deduplicating across the provider pool and legacy primary/fallback.
        The pool may hold references to primary/fallback; id() dedup prevents
        double-close.
        """
        closed_ids: set[int] = set()

        async def _close(provider: LLMProviderBase | None) -> None:
            if provider is not None and id(provider) not in closed_ids:
                closed_ids.add(id(provider))
                await provider.close()

        await _close(self.primary)
        await _close(self.fallback)

        for provider in self._provider_pool.values():
            await _close(provider)


# Export main classes
__all__ = [
    "MODELS",
    "LLMConfig",
    "LLMProviderFactory",
    "LLMRouter",
    "LLMService",
    "RouterDecision",
    "TaskContext",
    "TaskType",
    "ToolCall",
]
