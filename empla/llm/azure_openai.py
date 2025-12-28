"""
Azure OpenAI provider implementation.

This module implements the LLM provider interface for Azure OpenAI Service.
Azure OpenAI requires different configuration (endpoint, deployment name)
compared to standard OpenAI.
"""

from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncAzureOpenAI
from pydantic import BaseModel

from empla.llm.models import LLMRequest, LLMResponse, TokenUsage
from empla.llm.provider import LLMProviderBase


class AzureOpenAIProvider(LLMProviderBase):
    """
    Azure OpenAI provider.

    Azure OpenAI requires:
    - Azure endpoint (e.g., "https://myresource.openai.azure.com")
    - Deployment name (e.g., "gpt-4o-deployment")
    - API version (e.g., "2024-08-01-preview")

    Example:
        >>> provider = AzureOpenAIProvider(
        ...     api_key="your-azure-api-key",
        ...     model_id="gpt-4o",  # For reference only
        ...     azure_endpoint="https://myresource.openai.azure.com",
        ...     deployment_name="gpt-4o-deployment",
        ...     api_version="2024-08-01-preview",
        ... )
    """

    def __init__(
        self,
        api_key: str,
        model_id: str,
        azure_endpoint: str | None = None,
        deployment_name: str | None = None,
        api_version: str = "2024-08-01-preview",
        **kwargs: Any,
    ) -> None:
        """
        Initialize Azure OpenAI provider.

        Args:
            api_key: Azure OpenAI API key
            model_id: Model identifier (for reference/logging)
            azure_endpoint: Azure resource endpoint URL
            deployment_name: Name of the Azure OpenAI deployment
            api_version: Azure OpenAI API version
            **kwargs: Additional configuration
        """
        super().__init__(api_key, model_id, **kwargs)

        if not azure_endpoint:
            raise ValueError("azure_endpoint is required for Azure OpenAI")
        if not deployment_name:
            raise ValueError("deployment_name is required for Azure OpenAI")

        self.azure_endpoint = azure_endpoint
        self.deployment_name = deployment_name
        self.api_version = api_version

        self.client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generate completion using Azure OpenAI API.

        Args:
            request: LLM request

        Returns:
            LLM response
        """
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        response = await self.client.chat.completions.create(
            model=self.deployment_name,  # Azure uses deployment name
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stop=request.stop_sequences,
        )

        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content,
            model=response.model,
            usage=TokenUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            ),
            finish_reason=choice.finish_reason,
        )

    async def generate_structured(
        self, request: LLMRequest, response_format: type[BaseModel]
    ) -> tuple[LLMResponse, BaseModel]:
        """
        Generate structured output using Azure OpenAI's native structured outputs.

        Args:
            request: LLM request
            response_format: Pydantic model class for output

        Returns:
            Tuple of (LLM response, parsed output)
        """
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        response = await self.client.beta.chat.completions.parse(
            model=self.deployment_name,
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            response_format=response_format,
        )

        choice = response.choices[0]
        parsed = choice.message.parsed

        llm_response = LLMResponse(
            content=choice.message.content,
            model=response.model,
            usage=TokenUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            ),
            finish_reason=choice.finish_reason,
            structured_output=parsed,
        )

        return llm_response, parsed

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Stream completion using Azure OpenAI API.

        Args:
            request: LLM request

        Yields:
            Content chunks as they arrive
        """
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        stream = await self.client.chat.completions.create(
            model=self.deployment_name,
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stop=request.stop_sequences,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings using Azure OpenAI API.

        Note: Requires an embedding model deployment in Azure.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        # Use embedding deployment name from kwargs or fall back to text-embedding-3-large
        embedding_deployment = self.kwargs.get("embedding_deployment") or self.deployment_name
        if not embedding_deployment.startswith("text-embedding-"):
            embedding_deployment = "text-embedding-3-large"

        response = await self.client.embeddings.create(
            model=embedding_deployment,
            input=texts,
        )

        return [item.embedding for item in response.data]
