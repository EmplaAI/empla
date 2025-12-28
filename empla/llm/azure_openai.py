"""
Azure OpenAI provider implementation.

This module implements the LLM provider interface for Azure OpenAI Service.
Azure OpenAI requires different configuration (endpoint, deployment name)
compared to standard OpenAI.
"""

import json
from collections.abc import AsyncIterator
from typing import Any, cast

from openai import AsyncAzureOpenAI
from openai.types.chat import ChatCompletion
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
        usage = response.usage
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage=TokenUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            ),
            finish_reason=choice.finish_reason or "stop",
        )

    async def generate_structured(
        self, request: LLMRequest, response_format: type[BaseModel]
    ) -> tuple[LLMResponse, BaseModel]:
        """
        Generate structured output using Azure OpenAI's stable structured outputs API.

        Uses the stable chat.completions.create() endpoint with response_format
        parameter instead of the beta.parse() endpoint.

        Args:
            request: LLM request
            response_format: Pydantic model class for output

        Returns:
            Tuple of (LLM response, parsed output)
        """
        messages: list[dict[str, Any]] = [
            {"role": msg.role, "content": msg.content} for msg in request.messages
        ]

        # Build JSON schema from Pydantic model for stable API
        json_schema: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": response_format.__name__,
                "strict": True,
                "schema": response_format.model_json_schema(),
            },
        }

        # Use stable API with response_format
        # Note: type: ignore needed because OpenAI SDK uses strict literal types
        response = cast(
            ChatCompletion,
            await self.client.chat.completions.create(  # type: ignore[call-overload]
                model=self.deployment_name,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                response_format=json_schema,
            ),
        )

        choice = response.choices[0]
        content = choice.message.content or ""
        usage = response.usage

        # Parse JSON response into Pydantic model
        try:
            parsed_data = json.loads(content)
            parsed = response_format.model_validate(parsed_data)
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Failed to parse structured output: {e}") from e

        llm_response = LLMResponse(
            content=content,
            model=response.model,
            usage=TokenUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            ),
            finish_reason=choice.finish_reason or "stop",
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

        Requires an explicit embedding deployment to be configured via the
        `embedding_deployment` kwarg when initializing the provider.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors

        Raises:
            ValueError: If no embedding deployment is configured
            RuntimeError: If the embedding deployment is not accessible

        Example:
            >>> provider = AzureOpenAIProvider(
            ...     api_key="...",
            ...     model_id="gpt-4o",
            ...     azure_endpoint="https://myresource.openai.azure.com",
            ...     deployment_name="gpt-4o-deployment",
            ...     embedding_deployment="text-embedding-3-large-deployment",
            ... )
        """
        # Require explicit embedding deployment - no silent fallbacks
        embedding_deployment = self.kwargs.get("embedding_deployment")

        if not embedding_deployment:
            raise ValueError(
                "Azure OpenAI embedding deployment not configured. "
                "To use embeddings, provide 'embedding_deployment' when initializing "
                "AzureOpenAIProvider:\n\n"
                "    provider = AzureOpenAIProvider(\n"
                "        api_key='...',\n"
                "        model_id='gpt-4o',\n"
                "        azure_endpoint='https://myresource.openai.azure.com',\n"
                "        deployment_name='gpt-4o-deployment',\n"
                "        embedding_deployment='your-embedding-deployment-name',  # Required\n"
                "    )\n\n"
                "The embedding_deployment must be the name of an Azure OpenAI embedding "
                "model deployment (e.g., 'text-embedding-3-large' or 'text-embedding-ada-002')."
            )

        try:
            response = await self.client.embeddings.create(
                model=embedding_deployment,
                input=texts,
            )
            return [item.embedding for item in response.data]

        except Exception as e:
            # Catch deployment errors and provide helpful guidance
            error_msg = str(e).lower()
            if "not found" in error_msg or "does not exist" in error_msg:
                raise RuntimeError(
                    f"Azure OpenAI embedding deployment '{embedding_deployment}' not found. "
                    f"Please verify that:\n"
                    f"  1. The deployment '{embedding_deployment}' exists in your "
                    f"Azure OpenAI resource\n"
                    f"  2. The deployment is an embedding model "
                    f"(e.g., text-embedding-3-large)\n"
                    f"  3. The API key has access to this deployment\n\n"
                    f"Original error: {e}"
                ) from e
            # Re-raise other errors as-is
            raise
