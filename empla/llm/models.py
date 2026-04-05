"""
Shared LLM models and types.

This module defines common data models used across all LLM providers.
"""

from dataclasses import dataclass
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
        if self.role == "tool" and self.tool_calls is not None:
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
    tool_choice: Literal["auto", "required", "none"] | None = None

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


# ============================================================================
# Routing Types
# ============================================================================


class TaskType(str, Enum):
    """Type of LLM task — used by the router to select the appropriate model tier."""

    BELIEF_EXTRACTION = "belief_extraction"
    PLAN_GENERATION = "plan_generation"
    SITUATION_ANALYSIS = "situation_analysis"
    GOAL_MANAGEMENT = "goal_management"
    AGENTIC_EXECUTION = "agentic_execution"
    REFLECTION = "reflection"
    GENERAL = "general"


@dataclass(slots=True)
class TaskContext:
    """Context for a single LLM call — used by LLMRouter to select the model.

    Using @dataclass(slots=True) (not Pydantic) to minimize validation and
    memory overhead on the hot path.
    """

    task_type: TaskType = TaskType.GENERAL
    priority: int = 5  # 1-10
    estimated_input_tokens: int = 0
    requires_tool_use: bool = False
    requires_structured_output: bool = False
    latency_sensitive: bool = False
    quality_threshold: float = 0.5  # 0.0-1.0; ≥0.9 triggers premium tier
    retry_count: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.priority <= 10:
            raise ValueError(f"priority must be between 1 and 10, got {self.priority}")
        if not 0.0 <= self.quality_threshold <= 1.0:
            raise ValueError(
                f"quality_threshold must be between 0.0 and 1.0, got {self.quality_threshold}"
            )
        if self.estimated_input_tokens < 0:
            raise ValueError(
                f"estimated_input_tokens must be >= 0, got {self.estimated_input_tokens}"
            )
        if self.retry_count < 0:
            raise ValueError(f"retry_count must be >= 0, got {self.retry_count}")


class RouterDecision(BaseModel):
    """Decision made by LLMRouter for a single call."""

    model_key: str
    tier: int
    reason: str
    fallback_model_key: str | None = None


class ModelTier:
    """Model tier definitions by cost/capability.

    Tier lists use tuples (immutable) to prevent accidental mutation.
    Capability sets use frozensets for O(1) membership tests.
    """

    TIER_1: tuple[str, ...] = ("gemini-3-flash-preview",)
    TIER_2: tuple[str, ...] = ("gemini-2.0-flash", "gpt-4o-mini")
    TIER_3: tuple[str, ...] = ("gemini-1.5-pro", "gpt-4o")
    TIER_4: tuple[str, ...] = ("claude-sonnet-4", "claude-opus-4")

    # Models with ≥1M context window — preferred for long-context calls
    LONG_CONTEXT_MODELS: frozenset[str] = frozenset({"gemini-1.5-pro"})

    # Models with reliable tool/function calling support
    TOOL_CALL_PREFERRED: frozenset[str] = frozenset(
        {
            "gemini-2.0-flash",
            "gpt-4o-mini",
            "gemini-1.5-pro",
            "gpt-4o",
            "claude-sonnet-4",
            "claude-opus-4",
        }
    )

    # Models with reliable structured output (JSON mode / constrained decoding)
    STRUCTURED_OUTPUT_RELIABLE: frozenset[str] = frozenset(
        {
            "gemini-2.0-flash",
            "gpt-4o-mini",
            "gemini-1.5-pro",
            "gpt-4o",
            "claude-sonnet-4",
            "claude-opus-4",
        }
    )

    @classmethod
    def get_tier_models(cls, tier: int) -> tuple[str, ...]:
        """Return ordered tuple of model keys for the given tier number."""
        match tier:
            case 1:
                return cls.TIER_1
            case 2:
                return cls.TIER_2
            case 3:
                return cls.TIER_3
            case 4:
                return cls.TIER_4
            case _:
                return ()
