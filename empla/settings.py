"""
empla.settings - Centralized Configuration

Single source of truth for all empla configuration.
Loads from .env files and environment variables using pydantic-settings.

Settings hierarchy (highest wins):
    Employee.config  (per-employee JSONB in DB)
        |
    Tenant.settings  (optional DB override -- wired but deferred)
        |
    EmplaSettings    (.env / env vars -- server defaults)

Usage:
    >>> from empla.settings import get_settings
    >>> settings = get_settings()
    >>> settings.database_url
    'postgresql+asyncpg://localhost/empla_dev'

    >>> from empla.settings import resolve_llm_config
    >>> llm_config = resolve_llm_config(settings, employee_llm=employee.config.llm)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from empla.employees.config import LLMSettings
from empla.llm.config import LLMConfig


class EmplaSettings(BaseSettings):
    """Centralized empla configuration loaded from .env / environment variables.

    All EMPLA_* prefixed env vars are loaded automatically.
    API keys use standard names (no prefix) via aliases for backward compatibility.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="EMPLA_",
        extra="ignore",
    )

    # -- Environment -----------------------------------------------------------
    env: str = "development"

    # -- Database --------------------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://localhost/empla_dev",
        alias="DATABASE_URL",
    )

    # -- API Server ------------------------------------------------------------
    # Defaults to loopback; set EMPLA_API_HOST=0.0.0.0 for production/container use.
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # -- Logging ---------------------------------------------------------------
    log_level: str = "INFO"

    # -- LLM Defaults ----------------------------------------------------------
    llm_primary_model: str = "gemini-3-flash-preview"
    llm_fallback_model: str | None = "claude-sonnet-4"
    llm_embedding_model: str = "text-embedding-3-large"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    llm_max_retries: int = 3
    llm_timeout_seconds: int = 60
    llm_enable_cost_tracking: bool = True

    # -- API Keys (standard names via alias, no EMPLA_ prefix) -----------------
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    azure_openai_api_key: str | None = Field(default=None, alias="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: str | None = Field(default=None, alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_deployment: str | None = Field(default=None, alias="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_api_version: str = "2024-08-01-preview"
    vertex_project_id: str | None = Field(default=None, alias="VERTEX_PROJECT_ID")
    vertex_location: str = "us-central1"

    # -- Validators ------------------------------------------------------------

    @model_validator(mode="before")
    @classmethod
    def _google_cloud_project_fallback(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Fall back to GOOGLE_CLOUD_PROJECT if VERTEX_PROJECT_ID is not set."""
        if (
            isinstance(data, dict)
            and not data.get("VERTEX_PROJECT_ID")
            and not data.get("vertex_project_id")
        ):
            import os

            gcp = os.environ.get("GOOGLE_CLOUD_PROJECT")
            if gcp:
                data["VERTEX_PROJECT_ID"] = gcp
        return data

    # -- Helpers ---------------------------------------------------------------

    def has_llm_credentials(self) -> bool:
        """Return True if at least one LLM provider is configured."""
        return bool(
            self.anthropic_api_key
            or self.openai_api_key
            or self.vertex_project_id
            or self.azure_openai_api_key
        )

    def build_llm_config(self) -> LLMConfig:
        """Build an LLMConfig from server-level settings."""
        return LLMConfig(
            primary_model=self.llm_primary_model,
            fallback_model=self.llm_fallback_model,
            embedding_model=self.llm_embedding_model,
            temperature=self.llm_temperature,
            max_tokens=self.llm_max_tokens,
            anthropic_api_key=self.anthropic_api_key,
            openai_api_key=self.openai_api_key,
            vertex_project_id=self.vertex_project_id,
            vertex_location=self.vertex_location,
            azure_openai_api_key=self.azure_openai_api_key,
            azure_openai_endpoint=self.azure_openai_endpoint,
            azure_openai_deployment=self.azure_openai_deployment,
            azure_openai_api_version=self.azure_openai_api_version,
            max_retries=self.llm_max_retries,
            timeout_seconds=self.llm_timeout_seconds,
            enable_cost_tracking=self.llm_enable_cost_tracking,
        )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_settings() -> EmplaSettings:
    """Return the cached EmplaSettings singleton."""
    return EmplaSettings()


def clear_settings_cache() -> None:
    """Clear the settings cache (useful for tests)."""
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Hierarchy merge
# ---------------------------------------------------------------------------


def resolve_llm_config(
    server_settings: EmplaSettings,
    *,
    tenant_settings: dict[str, Any] | None = None,
    employee_llm: LLMSettings | None = None,
) -> LLMConfig:
    """Merge settings hierarchy into a single LLMConfig.

    Priority (highest wins): employee_llm > tenant_settings > server_settings.

    Args:
        server_settings: Base EmplaSettings (from .env / env vars).
        tenant_settings: Optional tenant-level overrides (deferred -- pass None).
        employee_llm: Optional per-employee LLMSettings from EmployeeConfig.

    Returns:
        Fully resolved LLMConfig ready for LLMService.
    """
    # Start with server defaults
    primary_model = server_settings.llm_primary_model
    fallback_model = server_settings.llm_fallback_model
    embedding_model = server_settings.llm_embedding_model
    temperature = server_settings.llm_temperature
    max_tokens = server_settings.llm_max_tokens

    # Layer 2: tenant overrides (deferred -- just wire the shape)
    if tenant_settings:
        if isinstance(tenant_settings.get("primary_model"), str):
            primary_model = tenant_settings["primary_model"]
        if isinstance(tenant_settings.get("fallback_model"), str):
            fallback_model = tenant_settings["fallback_model"]
        if isinstance(tenant_settings.get("embedding_model"), str):
            embedding_model = tenant_settings["embedding_model"]
        if isinstance(tenant_settings.get("temperature"), int | float):
            temperature = float(tenant_settings["temperature"])
        if isinstance(tenant_settings.get("max_tokens"), int):
            max_tokens = tenant_settings["max_tokens"]

    # Layer 3: employee overrides (only fields explicitly set by the employee)
    if employee_llm:
        explicitly_set = employee_llm.model_fields_set
        if "primary_model" in explicitly_set:
            primary_model = employee_llm.primary_model
        if "fallback_model" in explicitly_set:
            fallback_model = employee_llm.fallback_model
        if "temperature" in explicitly_set:
            temperature = employee_llm.temperature
        if "max_tokens" in explicitly_set:
            max_tokens = employee_llm.max_tokens

    return LLMConfig(
        primary_model=primary_model,
        fallback_model=fallback_model,
        embedding_model=embedding_model,
        temperature=temperature,
        max_tokens=max_tokens,
        anthropic_api_key=server_settings.anthropic_api_key,
        openai_api_key=server_settings.openai_api_key,
        vertex_project_id=server_settings.vertex_project_id,
        vertex_location=server_settings.vertex_location,
        azure_openai_api_key=server_settings.azure_openai_api_key,
        azure_openai_endpoint=server_settings.azure_openai_endpoint,
        azure_openai_deployment=server_settings.azure_openai_deployment,
        azure_openai_api_version=server_settings.azure_openai_api_version,
        max_retries=server_settings.llm_max_retries,
        timeout_seconds=server_settings.llm_timeout_seconds,
        enable_cost_tracking=server_settings.llm_enable_cost_tracking,
    )
