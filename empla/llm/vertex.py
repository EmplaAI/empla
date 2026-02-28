"""
Google Vertex AI provider implementation.

This module implements the LLM provider interface for Google's Gemini models via Vertex AI.
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from empla.llm.models import LLMRequest, LLMResponse, Message, TokenUsage, ToolCall
from empla.llm.provider import LLMProviderBase

logger = logging.getLogger(__name__)


class VertexAIProvider(LLMProviderBase):
    """Google Vertex AI / Gemini provider."""

    def __init__(
        self,
        api_key: str,
        model_id: str,
        project_id: str,
        location: str = "us-central1",
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, model_id, **kwargs)
        self.project_id = project_id
        self.location = location

        # Import here to avoid requiring google-cloud-aiplatform if not using Vertex
        try:
            from google.cloud import aiplatform

            # Initialize Vertex AI
            aiplatform.init(project=project_id, location=location)
            # Note: We'll create the model instance per-request to support system instructions
        except ImportError as err:
            raise ImportError(
                "google-cloud-aiplatform is required for Vertex AI provider. "
                "Install with: pip install google-cloud-aiplatform"
            ) from err

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generate completion using Vertex AI API.

        Args:
            request: LLM request

        Returns:
            LLM response
        """
        from vertexai.generative_models import Content, GenerativeModel, Part

        # Convert messages to Vertex AI format
        contents = []
        system_instruction = None

        for msg in request.messages:
            if msg.role == "system":
                system_instruction = msg.content
            else:
                role = "user" if msg.role == "user" else "model"
                contents.append(Content(role=role, parts=[Part.from_text(msg.content)]))

        # Create model instance with system instruction
        # System instruction is set in the constructor, not in generate_content
        model = GenerativeModel(
            self.model_id,
            system_instruction=system_instruction if system_instruction else None,
        )

        # Generate
        generation_config = {
            "max_output_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stop_sequences": request.stop_sequences,
        }

        response = await model.generate_content_async(
            contents,
            generation_config=generation_config,
        )

        # Extract usage (Vertex AI provides this in response metadata)
        usage = response.usage_metadata

        return LLMResponse(
            content=response.text,
            model=self.model_id,
            usage=TokenUsage(
                input_tokens=usage.prompt_token_count,
                output_tokens=usage.candidates_token_count,
                total_tokens=usage.total_token_count,
            ),
            finish_reason=response.candidates[0].finish_reason.name,
        )

    async def generate_with_tools(self, request: LLMRequest) -> LLMResponse:
        """Generate completion with function calling via Vertex AI tools parameter."""
        from vertexai.generative_models import (
            Content,
            FunctionDeclaration,
            GenerativeModel,
            Part,
            Tool,
            ToolConfig,
        )

        # Convert tool schemas to Vertex FunctionDeclarations
        func_declarations = []
        for tool in request.tools or []:
            if (
                not isinstance(tool, dict)
                or not isinstance(tool.get("name"), str)
                or not tool["name"]
            ):
                raise ValueError(
                    f"Invalid tool descriptor: missing or invalid 'name' — got {tool!r}"
                )
            func_declarations.append(
                FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=tool.get("input_schema", {"type": "object", "properties": {}}),
                )
            )
        vertex_tools = [Tool(function_declarations=func_declarations)]

        # Build tool_call_id → function name map for tool result messages
        tool_name_map: dict[str, str] = {}
        for msg in request.messages:
            if msg.role == "assistant" and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_name_map[tc.id] = tc.name

        # Build conversation contents
        contents: list[Content] = []
        system_instruction: str | None = None
        pending_tool_parts: list[Part] = []

        for msg in request.messages:
            if msg.role == "system":
                system_instruction = msg.content
            elif msg.role == "tool":
                # Accumulate tool results — they'll be sent as a single user turn
                tool_call_id = msg.tool_call_id or ""
                tool_name = tool_name_map.get(tool_call_id, "unknown")
                if tool_name == "unknown":
                    logger.warning(
                        "tool_call_id %r not found in tool_name_map, using 'unknown'; content preview: %.120s",
                        tool_call_id or "(empty)",
                        msg.content,
                    )
                try:
                    response_data = json.loads(msg.content)
                    if not isinstance(response_data, dict):
                        response_data = {"result": response_data}
                except json.JSONDecodeError:
                    response_data = {"result": msg.content}
                pending_tool_parts.append(
                    Part.from_function_response(name=tool_name, response=response_data)
                )
            else:
                # Flush any pending tool results before the next non-tool message
                if pending_tool_parts:
                    contents.append(Content(role="user", parts=pending_tool_parts))
                    pending_tool_parts = []

                if msg.role == "assistant" and msg.tool_calls:
                    parts: list[Part] = []
                    if msg.content:
                        parts.append(Part.from_text(msg.content))
                    for tc in msg.tool_calls:
                        parts.append(
                            Part.from_dict(
                                {"function_call": {"name": tc.name, "args": tc.arguments}}
                            )
                        )
                    contents.append(Content(role="model", parts=parts))
                elif msg.role == "assistant":
                    contents.append(Content(role="model", parts=[Part.from_text(msg.content)]))
                else:  # user
                    contents.append(Content(role="user", parts=[Part.from_text(msg.content)]))

        # Flush remaining tool results
        if pending_tool_parts:
            contents.append(Content(role="user", parts=pending_tool_parts))

        # Build ToolConfig for tool_choice
        tool_config: ToolConfig | None = None
        if request.tool_choice == "required":
            tool_config = ToolConfig(
                function_calling_config=ToolConfig.FunctionCallingConfig(
                    mode=ToolConfig.FunctionCallingConfig.Mode.ANY
                )
            )
        elif request.tool_choice == "none":
            tool_config = ToolConfig(
                function_calling_config=ToolConfig.FunctionCallingConfig(
                    mode=ToolConfig.FunctionCallingConfig.Mode.NONE
                )
            )
        elif request.tool_choice == "auto":
            tool_config = ToolConfig(
                function_calling_config=ToolConfig.FunctionCallingConfig(
                    mode=ToolConfig.FunctionCallingConfig.Mode.AUTO
                )
            )

        # Create model and generate
        model = GenerativeModel(
            self.model_id,
            system_instruction=system_instruction if system_instruction else None,
        )

        generation_config = {
            "max_output_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stop_sequences": request.stop_sequences,
        }

        kwargs: dict[str, Any] = {
            "generation_config": generation_config,
            "tools": vertex_tools,
        }
        if tool_config is not None:
            kwargs["tool_config"] = tool_config

        response = await model.generate_content_async(contents, **kwargs)

        # Parse response — extract text and function calls
        text_content = ""
        tool_calls: list[ToolCall] = []
        finish_reason = "STOP"

        candidates = response.candidates or []
        if candidates:
            candidate = candidates[0]
            parts = getattr(getattr(candidate, "content", None), "parts", None) or []
            for part in parts:
                fc = getattr(part, "function_call", None)
                if fc and getattr(fc, "name", None):
                    args = getattr(fc, "args", None)
                    tool_calls.append(
                        ToolCall(
                            id=f"call_{uuid4().hex[:8]}",
                            name=fc.name,
                            arguments=dict(args) if args else {},
                        )
                    )
                elif getattr(part, "text", None):
                    text_content += part.text
            finish_reason = getattr(getattr(candidate, "finish_reason", None), "name", "STOP")

        usage = response.usage_metadata

        return LLMResponse(
            content=text_content,
            model=self.model_id,
            usage=TokenUsage(
                input_tokens=usage.prompt_token_count,
                output_tokens=usage.candidates_token_count,
                total_tokens=usage.total_token_count,
            ),
            finish_reason=finish_reason,
            tool_calls=tool_calls if tool_calls else None,
        )

    async def generate_structured(
        self, request: LLMRequest, response_format: type[BaseModel]
    ) -> tuple[LLMResponse, BaseModel]:
        """
        Generate structured output using Vertex AI's JSON mode.

        Args:
            request: LLM request
            response_format: Pydantic model class for output

        Returns:
            Tuple of (LLM response, parsed output)
        """
        # Add schema to system instruction
        schema = response_format.model_json_schema()
        schema_prompt = (
            f"Respond with valid JSON matching this schema:\n"
            f"{json.dumps(schema, indent=2)}\n\n"
            f"Output only the JSON object, no additional text."
        )

        # Modify request
        modified_request = request.model_copy()
        system_found = False
        for msg in modified_request.messages:
            if msg.role == "system":
                msg.content += f"\n\n{schema_prompt}"
                system_found = True
                break

        if not system_found:
            modified_request.messages.insert(0, Message(role="system", content=schema_prompt))

        # Generate
        response = await self.generate(modified_request)

        # Parse JSON
        try:
            parsed = response_format.model_validate_json(response.content)
        except Exception:
            # Try to extract JSON from response if wrapped
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
        Stream completion using Vertex AI API.

        Args:
            request: LLM request

        Yields:
            Content chunks as they arrive
        """
        from vertexai.generative_models import Content, GenerativeModel, Part

        contents = []
        system_instruction = None

        for msg in request.messages:
            if msg.role == "system":
                system_instruction = msg.content
            else:
                role = "user" if msg.role == "user" else "model"
                contents.append(Content(role=role, parts=[Part.from_text(msg.content)]))

        # Create model instance with system instruction
        model = GenerativeModel(
            self.model_id,
            system_instruction=system_instruction if system_instruction else None,
        )

        generation_config = {
            "max_output_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stop_sequences": request.stop_sequences,
        }

        response_stream = await model.generate_content_async(
            contents,
            generation_config=generation_config,
            stream=True,
        )

        async for chunk in response_stream:
            if chunk.text:
                yield chunk.text

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings using Vertex AI Embeddings API.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        from vertexai.language_models import TextEmbeddingModel

        model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        embeddings = await model.get_embeddings_async(texts)

        return [emb.values for emb in embeddings]
