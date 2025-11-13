"""
Google Vertex AI provider implementation.

This module implements the LLM provider interface for Google's Gemini models via Vertex AI.
"""

import json
from typing import AsyncIterator

from pydantic import BaseModel

from empla.llm.models import LLMRequest, LLMResponse, Message, TokenUsage
from empla.llm.provider import LLMProviderBase


class VertexAIProvider(LLMProviderBase):
    """Google Vertex AI / Gemini provider."""

    def __init__(
        self, api_key: str, model_id: str, project_id: str, location: str = "us-central1", **kwargs
    ):
        super().__init__(api_key, model_id, **kwargs)
        self.project_id = project_id
        self.location = location

        # Import here to avoid requiring google-cloud-aiplatform if not using Vertex
        try:
            from google.cloud import aiplatform
            from vertexai.generative_models import GenerativeModel

            # Initialize Vertex AI
            aiplatform.init(project=project_id, location=location)
            self.model = GenerativeModel(model_id)
        except ImportError:
            raise ImportError(
                "google-cloud-aiplatform is required for Vertex AI provider. "
                "Install with: pip install google-cloud-aiplatform"
            )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generate completion using Vertex AI API.

        Args:
            request: LLM request

        Returns:
            LLM response
        """
        from vertexai.generative_models import Content, Part

        # Convert messages to Vertex AI format
        contents = []
        system_instruction = None

        for msg in request.messages:
            if msg.role == "system":
                system_instruction = msg.content
            else:
                role = "user" if msg.role == "user" else "model"
                contents.append(Content(role=role, parts=[Part.from_text(msg.content)]))

        # Generate
        generation_config = {
            "max_output_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stop_sequences": request.stop_sequences,
        }

        response = await self.model.generate_content_async(
            contents,
            generation_config=generation_config,
            system_instruction=system_instruction,
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
            modified_request.messages.insert(
                0, Message(role="system", content=schema_prompt)
            )

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
        from vertexai.generative_models import Content, Part

        contents = []
        system_instruction = None

        for msg in request.messages:
            if msg.role == "system":
                system_instruction = msg.content
            else:
                role = "user" if msg.role == "user" else "model"
                contents.append(Content(role=role, parts=[Part.from_text(msg.content)]))

        generation_config = {
            "max_output_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        response_stream = await self.model.generate_content_async(
            contents,
            generation_config=generation_config,
            system_instruction=system_instruction,
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
