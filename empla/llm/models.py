"""
Shared LLM models and types.

This module defines common data models used across all LLM providers.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, model_validator


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
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


class ToolCall(BaseModel):
    """A tool call from the LLM."""

    id: str
    """Provider-assigned ID"""

    name: str
    """Tool name (e.g., "email.send")"""

    arguments: dict[str, Any]
    """Parsed arguments"""


class Message(BaseModel):
    """Chat message."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str

    tool_calls: list[ToolCall] | None = None
    """For assistant messages: tool calls the LLM wants to make"""

    tool_call_id: str | None = None
    """For tool messages: ID of the tool call this result is for"""

    @model_validator(mode="after")
    def validate_role_field_consistency(self) -> "Message":
        if self.role == "tool" and not self.tool_call_id:
            raise ValueError("tool messages must have tool_call_id")
        if self.role == "tool" and self.tool_calls:
            raise ValueError("tool messages cannot have tool_calls")
        if self.role in ("system", "user") and self.tool_calls is not None:
            raise ValueError(f"{self.role} messages cannot have tool_calls")
        if self.role in ("system", "user") and self.tool_call_id is not None:
            raise ValueError(f"{self.role} messages cannot have tool_call_id")
        if self.role == "assistant" and self.tool_call_id is not None:
            raise ValueError("assistant messages cannot have tool_call_id")
        return self


class LLMRequest(BaseModel):
    """LLM generation request."""

    messages: list[Message]
    max_tokens: int = 4096
    temperature: float = 0.7
    stop_sequences: list[str] | None = None

    # Structured output (optional)
    response_format: type[BaseModel] | None = None

    # Function calling (optional)
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | None = None  # "auto", "required", "none"

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
    finish_reason: str  # "end_turn" | "tool_use" | "stop"

    # For structured outputs
    structured_output: Any | None = None

    # For function calling
    tool_calls: list[ToolCall] | None = None

    class Config:
        arbitrary_types_allowed = True
