"""
OpenAI provider implementation.

This module implements the LLM provider interface for OpenAI's GPT models.
"""

from collections.abc import AsyncIterator

from openai import AsyncOpenAI
from pydantic import BaseModel

from empla.llm.models import LLMRequest, LLMResponse, TokenUsage
from empla.llm.provider import LLMProviderBase


class OpenAIProvider(LLMProviderBase):
    """OpenAI GPT provider."""

    def __init__(self, api_key: str, model_id: str, **kwargs):
        super().__init__(api_key, model_id, **kwargs)
        self.client = AsyncOpenAI(api_key=api_key)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generate completion using OpenAI API.

        Args:
            request: LLM request

        Returns:
            LLM response
        """
        # Convert messages
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        # Call OpenAI API
        response = await self.client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stop=request.stop_sequences,
        )

        # Convert to standard response
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
        Generate structured output using OpenAI's native structured outputs.

        Args:
            request: LLM request
            response_format: Pydantic model class for output

        Returns:
            Tuple of (LLM response, parsed output)
        """
        # Convert messages
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        # Use OpenAI's response_format with strict mode
        response = await self.client.beta.chat.completions.parse(
            model=self.model_id,
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            response_format=response_format,  # Native structured output
        )

        # Parse response
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
        Stream completion using OpenAI API.

        Args:
            request: LLM request

        Yields:
            Content chunks as they arrive
        """
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        stream = await self.client.chat.completions.create(
            model=self.model_id,
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
        Generate embeddings using OpenAI API.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        model_name = self.kwargs.get("embedding_model") or self.model_id
        if not model_name or not model_name.startswith("text-embedding-"):
            model_name = "text-embedding-3-large"

        response = await self.client.embeddings.create(
            model=model_name,
            input=texts,
        )

        return [item.embedding for item in response.data]
