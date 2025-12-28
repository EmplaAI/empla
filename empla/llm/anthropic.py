"""
Anthropic Claude provider implementation.

This module implements the LLM provider interface for Anthropic's Claude models.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from empla.llm.models import LLMRequest, LLMResponse, Message, TokenUsage
from empla.llm.provider import LLMProviderBase


class AnthropicProvider(LLMProviderBase):
    """Anthropic Claude provider."""

    def __init__(self, api_key: str, model_id: str, **kwargs: Any) -> None:
        super().__init__(api_key, model_id, **kwargs)
        self.client = AsyncAnthropic(api_key=api_key)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generate completion using Anthropic API.

        Args:
            request: LLM request

        Returns:
            LLM response
        """
        # Convert messages (extract system message if present)
        system_message = None
        messages = []
        for msg in request.messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                messages.append({"role": msg.role, "content": msg.content})

        # Call Anthropic API
        response = await self.client.messages.create(
            model=self.model_id,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system=system_message,
            messages=messages,
            stop_sequences=request.stop_sequences,
        )

        # Convert to standard response
        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            usage=TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            ),
            finish_reason=response.stop_reason,
        )

    async def generate_structured(
        self, request: LLMRequest, response_format: type[BaseModel]
    ) -> tuple[LLMResponse, BaseModel]:
        """
        Generate structured output using Anthropic's JSON mode.

        Args:
            request: LLM request
            response_format: Pydantic model class for output

        Returns:
            Tuple of (LLM response, parsed output)
        """
        # Add JSON schema to system message
        schema = response_format.model_json_schema()
        schema_prompt = (
            f"\n\nRespond with valid JSON matching this schema:\n"
            f"{json.dumps(schema, indent=2)}\n\n"
            f"Output only the JSON object, no additional text."
        )

        # Modify request
        modified_request = request.model_copy()
        system_found = False
        for msg in modified_request.messages:
            if msg.role == "system":
                msg.content += schema_prompt
                system_found = True
                break

        if not system_found:
            # No system message, add one
            modified_request.messages.insert(
                0, Message(role="system", content=schema_prompt.strip())
            )

        # Generate
        response = await self.generate(modified_request)

        # Parse JSON
        try:
            parsed = response_format.model_validate_json(response.content)
        except Exception:
            # Try to extract JSON from response if wrapped in markdown
            content = response.content.strip()
            if content.startswith("```json"):
                content = content.split("```json")[1].split("```")[0].strip()
            elif content.startswith("```"):
                content = content.split("```")[1].split("```")[0].strip()

            parsed = response_format.model_validate_json(content)

        response.structured_output = parsed

        return response, parsed

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Stream completion using Anthropic API.

        Args:
            request: LLM request

        Yields:
            Content chunks as they arrive
        """
        system_message = None
        messages = []
        for msg in request.messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                messages.append({"role": msg.role, "content": msg.content})

        async with self.client.messages.stream(
            model=self.model_id,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system=system_message,
            messages=messages,
            stop_sequences=request.stop_sequences,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings.

        Note: Anthropic doesn't provide native embeddings API.
        Use Voyage AI or OpenAI for embeddings instead.

        Args:
            texts: List of texts to embed

        Raises:
            NotImplementedError: Anthropic doesn't provide embeddings
        """
        raise NotImplementedError(
            "Anthropic doesn't provide embeddings API. "
            "Use OpenAI or Voyage AI for embeddings instead."
        )
