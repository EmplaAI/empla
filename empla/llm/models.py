"""
Shared LLM models and types.

This module defines common data models used across all LLM providers.
"""

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    VERTEX = "vertex"


class LLMModel(BaseModel):
    """LLM model configuration."""

    provider: LLMProvider
    model_id: str  # e.g., "claude-sonnet-4-20250514", "gpt-4o", "gemini-1.5-pro"
    max_tokens: int = 4096
    temperature: float = 0.7

    # Cost per 1M tokens (for tracking)
    input_cost_per_1m: float
    output_cost_per_1m: float


class Message(BaseModel):
    """Chat message."""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMRequest(BaseModel):
    """LLM generation request."""

    messages: list[Message]
    max_tokens: int = 4096
    temperature: float = 0.7
    stop_sequences: Optional[list[str]] = None

    # Structured output (optional)
    response_format: Optional[type[BaseModel]] = None

    class Config:
        arbitrary_types_allowed = True


class TokenUsage(BaseModel):
    """Token usage tracking."""

    input_tokens: int
    output_tokens: int
    total_tokens: int

    def calculate_cost(self, model: LLMModel) -> float:
        """
        Calculate cost of this request.

        Args:
            model: Model configuration with pricing

        Returns:
            Cost in USD
        """
        input_cost = (self.input_tokens / 1_000_000) * model.input_cost_per_1m
        output_cost = (self.output_tokens / 1_000_000) * model.output_cost_per_1m
        return input_cost + output_cost


class LLMResponse(BaseModel):
    """LLM generation response."""

    content: str
    model: str
    usage: TokenUsage
    finish_reason: str

    # For structured outputs
    structured_output: Optional[Any] = None

    class Config:
        arbitrary_types_allowed = True
