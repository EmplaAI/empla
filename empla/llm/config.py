"""
LLM provider configuration.

This module provides configuration for LLM providers and pre-configured model definitions.
"""

from pydantic import BaseModel, Field

from empla.llm.models import LLMModel, LLMProvider

# Pre-configured models with pricing
MODELS = {
    # Anthropic Claude
    "claude-sonnet-4": LLMModel(
        provider=LLMProvider.ANTHROPIC,
        model_id="claude-sonnet-4-20250514",
        max_tokens=8192,
        temperature=0.7,
        input_cost_per_1m=3.00,
        output_cost_per_1m=15.00,
    ),
    "claude-opus-4": LLMModel(
        provider=LLMProvider.ANTHROPIC,
        model_id="claude-opus-4-20250514",
        max_tokens=8192,
        temperature=0.7,
        input_cost_per_1m=15.00,
        output_cost_per_1m=75.00,
    ),
    # OpenAI GPT
    "gpt-4o": LLMModel(
        provider=LLMProvider.OPENAI,
        model_id="gpt-4o",
        max_tokens=4096,
        temperature=0.7,
        input_cost_per_1m=2.50,
        output_cost_per_1m=10.00,
    ),
    "gpt-4o-mini": LLMModel(
        provider=LLMProvider.OPENAI,
        model_id="gpt-4o-mini",
        max_tokens=4096,
        temperature=0.7,
        input_cost_per_1m=0.15,
        output_cost_per_1m=0.60,
    ),
    # Google Vertex AI / Gemini
    "gemini-1.5-pro": LLMModel(
        provider=LLMProvider.VERTEX,
        model_id="gemini-1.5-pro",
        max_tokens=8192,
        temperature=0.7,
        input_cost_per_1m=1.25,
        output_cost_per_1m=5.00,
    ),
    "gemini-2.0-flash": LLMModel(
        provider=LLMProvider.VERTEX,
        model_id="gemini-2.0-flash",
        max_tokens=8192,
        temperature=0.7,
        input_cost_per_1m=0.15,
        output_cost_per_1m=0.60,
    ),
    "gemini-3-flash-preview": LLMModel(
        provider=LLMProvider.VERTEX,
        model_id="gemini-3-flash-preview",
        max_tokens=8192,
        temperature=0.7,
        input_cost_per_1m=0.10,
        output_cost_per_1m=0.40,
    ),
}


class LLMConfig(BaseModel):
    """LLM configuration."""

    # Primary model (main model for reasoning)
    primary_model: str = "gemini-3-flash-preview"

    # Fallback model (different provider for redundancy)
    fallback_model: str | None = "claude-sonnet-4"

    # Embedding model (use OpenAI for now)
    embedding_model: str = "text-embedding-3-large"

    # Request defaults
    temperature: float = 0.7
    max_tokens: int = 4096

    # API keys (exclude from serialization for security)
    anthropic_api_key: str | None = Field(default=None, exclude=True)
    openai_api_key: str | None = Field(default=None, exclude=True)

    # Azure OpenAI configuration
    azure_openai_api_key: str | None = Field(default=None, exclude=True)
    azure_openai_endpoint: str | None = None  # e.g., "https://myresource.openai.azure.com"
    azure_openai_deployment: str | None = None  # e.g., "gpt-4o-deployment"
    azure_openai_api_version: str = "2024-08-01-preview"

    # Google Vertex AI configuration
    vertex_project_id: str | None = None
    vertex_location: str = "us-central1"

    # Performance settings
    max_retries: int = 3
    timeout_seconds: int = 60

    # Cost tracking
    enable_cost_tracking: bool = True

    class Config:
        # Don't serialize sensitive fields
        json_encoders = {str: lambda v: "***" if "key" in str(v).lower() else v}
