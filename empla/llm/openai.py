"""
OpenAI provider implementation.

This module implements the LLM provider interface for OpenAI's GPT models.
"""

import json
from collections.abc import AsyncIterator
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
from pydantic import BaseModel

from empla.llm.models import LLMRequest, LLMResponse, TokenUsage, ToolCall
from empla.llm.provider import LLMProviderBase


class OpenAIProvider(LLMProviderBase):
    """OpenAI GPT provider."""

    def __init__(self, api_key: str, model_id: str, **kwargs: Any) -> None:
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
        messages: list[dict[str, Any]] = [
            {"role": msg.role, "content": msg.content} for msg in request.messages
        ]

        # Call OpenAI API
        response = await self.client.chat.completions.create(
            model=self.model_id,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stop=request.stop_sequences,
        )

        # Convert to standard response
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

    async def generate_with_tools(self, request: LLMRequest) -> LLMResponse:
        """Generate completion with tool calling via OpenAI tools parameter."""
        messages: list[dict[str, Any]] = []

        for msg in request.messages:
            if msg.role == "tool":
                messages.append(
                    {
                        "role": "tool",
                        "content": msg.content,
                        "tool_call_id": msg.tool_call_id,
                    }
                )
            elif msg.role == "assistant" and msg.tool_calls:
                oai_tool_calls = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or None,
                        "tool_calls": oai_tool_calls,
                    }
                )
            else:
                messages.append({"role": msg.role, "content": msg.content})

        # Build OpenAI tools parameter
        oai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
            for tool in request.tools or []
        ]

        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "tools": oai_tools,
        }
        if request.tool_choice:
            kwargs["tool_choice"] = request.tool_choice

        response = await self.client.chat.completions.create(**kwargs)  # type: ignore[call-overload]

        if not response.choices:
            raise ValueError(
                f"OpenAI returned empty choices list (model={response.model}). "
                "This may indicate content filtering or a provider-side issue."
            )
        choice = response.choices[0]
        usage = response.usage

        # Parse tool calls from response
        tool_calls: list[ToolCall] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    parsed_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"LLM returned malformed JSON for tool call '{tc.function.name}': {e}"
                    ) from e
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=parsed_args,
                    )
                )

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage=TokenUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            ),
            finish_reason=choice.finish_reason or "stop",
            tool_calls=tool_calls if tool_calls else None,
        )

    async def generate_structured(
        self, request: LLMRequest, response_format: type[BaseModel]
    ) -> tuple[LLMResponse, BaseModel]:
        """
        Generate structured output using OpenAI's stable structured outputs API.

        Uses the stable chat.completions.create() endpoint with response_format
        parameter instead of the beta.parse() endpoint.

        Args:
            request: LLM request
            response_format: Pydantic model class for output

        Returns:
            Tuple of (LLM response, parsed output)
        """
        # Convert messages
        messages: list[dict[str, Any]] = [
            {"role": msg.role, "content": msg.content} for msg in request.messages
        ]

        # Build JSON schema from Pydantic model for stable API
        # OpenAI requires additionalProperties: false for strict mode
        schema = response_format.model_json_schema()
        self._add_additional_properties_false(schema)

        json_schema: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": response_format.__name__,
                "strict": True,
                "schema": schema,
            },
        }

        # Use stable API with response_format
        # Note: type: ignore needed because OpenAI SDK uses strict literal types
        response = cast(
            ChatCompletion,
            await self.client.chat.completions.create(  # type: ignore[call-overload]
                model=self.model_id,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                response_format=json_schema,
            ),
        )

        # Parse response
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

    def _add_additional_properties_false(self, schema: dict[str, Any]) -> None:
        """
        Recursively add additionalProperties: false to all objects in schema.

        OpenAI's structured output with strict mode requires this property
        to be set on all object types in the schema.
        """
        if not isinstance(schema, dict):
            return

        # Add to this level if it has properties (is an object type)
        if "properties" in schema:
            schema["additionalProperties"] = False

        # Recurse into nested schemas
        for _key, value in schema.items():
            if isinstance(value, dict):
                self._add_additional_properties_false(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._add_additional_properties_false(item)

        # Handle $defs (Pydantic v2 uses $defs for nested models)
        if "$defs" in schema:
            for def_schema in schema["$defs"].values():
                self._add_additional_properties_false(def_schema)

    async def close(self) -> None:
        """Close the OpenAI client and release resources."""
        await self.client.close()
