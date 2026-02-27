"""
Unit tests for empla.settings - Centralized Configuration

Tests default values, environment variable overrides, .env file loading,
build_llm_config(), resolve_llm_config(), has_llm_credentials(),
GOOGLE_CLOUD_PROJECT fallback, and clear_settings_cache().
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from empla.employees.config import LLMSettings
from empla.settings import (
    EmplaSettings,
    clear_settings_cache,
    get_settings,
    resolve_llm_config,
)

# Keys that alias-based fields read from the environment (no EMPLA_ prefix).
# We strip these during tests so the real env doesn't leak in.
_ALIAS_KEYS = [
    "DATABASE_URL",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
    "VERTEX_PROJECT_ID",
    "GOOGLE_CLOUD_PROJECT",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    """Clear settings cache and strip LLM env vars so tests are isolated."""
    clear_settings_cache()
    for key in _ALIAS_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    clear_settings_cache()


# ============================================================================
# Default Values
# ============================================================================


class TestDefaults:
    def test_default_env(self):
        settings = EmplaSettings(_env_file=None)
        assert settings.env == "development"

    def test_default_database_url(self):
        settings = EmplaSettings(_env_file=None)
        assert settings.database_url == "postgresql+asyncpg://localhost/empla_dev"

    def test_default_cors_origins(self):
        settings = EmplaSettings(_env_file=None)
        assert "http://localhost:3000" in settings.cors_origins
        assert "http://localhost:5173" in settings.cors_origins

    def test_default_llm_settings(self):
        settings = EmplaSettings(_env_file=None)
        assert settings.llm_primary_model == "gemini-3-flash-preview"
        assert settings.llm_fallback_model == "claude-sonnet-4"
        assert settings.llm_embedding_model == "text-embedding-3-large"
        assert settings.llm_temperature == 0.7
        assert settings.llm_max_tokens == 4096

    def test_default_api_keys_are_none(self):
        settings = EmplaSettings(_env_file=None)
        assert settings.anthropic_api_key is None
        assert settings.openai_api_key is None
        assert settings.azure_openai_api_key is None
        assert settings.vertex_project_id is None


# ============================================================================
# Environment Variable Overrides
# ============================================================================


class TestEnvOverrides:
    def test_empla_prefix_overrides(self):
        env = {
            "EMPLA_ENV": "production",
            "EMPLA_LLM_PRIMARY_MODEL": "gpt-4o",
            "EMPLA_LLM_TEMPERATURE": "0.3",
            "EMPLA_LOG_LEVEL": "DEBUG",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = EmplaSettings(_env_file=None)
            assert settings.env == "production"
            assert settings.llm_primary_model == "gpt-4o"
            assert settings.llm_temperature == 0.3
            assert settings.log_level == "DEBUG"

    def test_database_url_alias(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://db/prod"}, clear=False):
            settings = EmplaSettings(_env_file=None)
            assert settings.database_url == "postgresql+asyncpg://db/prod"

    def test_cors_origins_json_format(self):
        env = {"EMPLA_CORS_ORIGINS": '["https://app.example.com","https://admin.example.com"]'}
        with patch.dict(os.environ, env, clear=False):
            settings = EmplaSettings(_env_file=None)
            assert settings.cors_origins == [
                "https://app.example.com",
                "https://admin.example.com",
            ]

    def test_api_key_aliases(self):
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "OPENAI_API_KEY": "sk-test",
            "AZURE_OPENAI_API_KEY": "az-test",
            "VERTEX_PROJECT_ID": "my-project",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = EmplaSettings(_env_file=None)
            assert settings.anthropic_api_key == "sk-ant-test"
            assert settings.openai_api_key == "sk-test"
            assert settings.azure_openai_api_key == "az-test"
            assert settings.vertex_project_id == "my-project"


# ============================================================================
# .env File Loading
# ============================================================================


class TestDotenvLoading:
    def test_loads_from_env_file(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("EMPLA_ENV=staging\nEMPLA_LOG_LEVEL=WARNING\n")

        settings = EmplaSettings(_env_file=str(env_file))
        assert settings.env == "staging"
        assert settings.log_level == "WARNING"

    def test_env_vars_override_env_file(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("EMPLA_ENV=staging\n")

        with patch.dict(os.environ, {"EMPLA_ENV": "production"}, clear=False):
            settings = EmplaSettings(_env_file=str(env_file))
            assert settings.env == "production"


# ============================================================================
# has_llm_credentials()
# ============================================================================


class TestHasLLMCredentials:
    def test_no_credentials(self):
        settings = EmplaSettings(_env_file=None)
        assert settings.has_llm_credentials() is False

    def test_anthropic_only(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
            settings = EmplaSettings(_env_file=None)
            assert settings.has_llm_credentials() is True

    def test_openai_only(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
            settings = EmplaSettings(_env_file=None)
            assert settings.has_llm_credentials() is True

    def test_vertex_only(self):
        with patch.dict(os.environ, {"VERTEX_PROJECT_ID": "project"}, clear=False):
            settings = EmplaSettings(_env_file=None)
            assert settings.has_llm_credentials() is True

    def test_azure_only(self):
        with patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": "az-test"}, clear=False):
            settings = EmplaSettings(_env_file=None)
            assert settings.has_llm_credentials() is True


# ============================================================================
# GOOGLE_CLOUD_PROJECT Fallback
# ============================================================================


class TestGCPFallback:
    def test_google_cloud_project_fallback(self):
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "my-gcp-project"}, clear=False):
            settings = EmplaSettings(_env_file=None)
            assert settings.vertex_project_id == "my-gcp-project"

    def test_vertex_project_id_takes_precedence(self):
        env = {
            "VERTEX_PROJECT_ID": "explicit-project",
            "GOOGLE_CLOUD_PROJECT": "fallback-project",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = EmplaSettings(_env_file=None)
            assert settings.vertex_project_id == "explicit-project"


# ============================================================================
# build_llm_config()
# ============================================================================


class TestBuildLLMConfig:
    def test_builds_from_defaults(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
            settings = EmplaSettings(_env_file=None)
            config = settings.build_llm_config()

        assert config.primary_model == "gemini-3-flash-preview"
        assert config.fallback_model == "claude-sonnet-4"
        assert config.embedding_model == "text-embedding-3-large"
        assert config.temperature == 0.7
        assert config.max_tokens == 4096
        assert config.anthropic_api_key == "sk-ant-test"
        assert config.max_retries == 3
        assert config.timeout_seconds == 60
        assert config.enable_cost_tracking is True

    def test_builds_with_custom_model(self):
        env = {
            "EMPLA_LLM_PRIMARY_MODEL": "gpt-4o",
            "OPENAI_API_KEY": "sk-test",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = EmplaSettings(_env_file=None)
            config = settings.build_llm_config()

        assert config.primary_model == "gpt-4o"
        assert config.openai_api_key == "sk-test"

    def test_builds_with_azure_fields(self):
        env = {
            "AZURE_OPENAI_API_KEY": "az-key",
            "AZURE_OPENAI_ENDPOINT": "https://myresource.openai.azure.com",
            "AZURE_OPENAI_DEPLOYMENT": "gpt-4o-deploy",
            "EMPLA_AZURE_OPENAI_API_VERSION": "2025-01-01",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = EmplaSettings(_env_file=None)
            config = settings.build_llm_config()

        assert config.azure_openai_api_key == "az-key"
        assert config.azure_openai_endpoint == "https://myresource.openai.azure.com"
        assert config.azure_openai_deployment == "gpt-4o-deploy"
        assert config.azure_openai_api_version == "2025-01-01"

    def test_builds_with_vertex_fields(self):
        env = {
            "VERTEX_PROJECT_ID": "my-gcp-project",
            "EMPLA_VERTEX_LOCATION": "europe-west1",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = EmplaSettings(_env_file=None)
            config = settings.build_llm_config()

        assert config.vertex_project_id == "my-gcp-project"
        assert config.vertex_location == "europe-west1"

    def test_none_api_keys_stay_none(self):
        settings = EmplaSettings(_env_file=None)
        config = settings.build_llm_config()
        assert config.anthropic_api_key is None
        assert config.openai_api_key is None


# ============================================================================
# resolve_llm_config()
# ============================================================================


class TestResolveLLMConfig:
    def test_server_defaults_only(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
            settings = EmplaSettings(_env_file=None)
        config = resolve_llm_config(settings)
        assert config.primary_model == "gemini-3-flash-preview"
        assert config.fallback_model == "claude-sonnet-4"
        assert config.temperature == 0.7
        assert config.max_tokens == 4096

    def test_employee_overrides_model(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
            settings = EmplaSettings(_env_file=None)
        employee_llm = LLMSettings(primary_model="gpt-4o", fallback_model="gpt-4o-mini")
        config = resolve_llm_config(settings, employee_llm=employee_llm)
        assert config.primary_model == "gpt-4o"
        assert config.fallback_model == "gpt-4o-mini"

    def test_employee_explicit_temperature_overrides(self):
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "EMPLA_LLM_TEMPERATURE": "0.5",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = EmplaSettings(_env_file=None)
        employee_llm = LLMSettings(temperature=0.2)
        config = resolve_llm_config(settings, employee_llm=employee_llm)
        assert config.temperature == 0.2
        assert config.primary_model == "gemini-3-flash-preview"  # still server default

    def test_employee_explicit_max_tokens_overrides(self):
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "EMPLA_LLM_MAX_TOKENS": "8192",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = EmplaSettings(_env_file=None)
        employee_llm = LLMSettings(max_tokens=2048)
        config = resolve_llm_config(settings, employee_llm=employee_llm)
        assert config.max_tokens == 2048

    def test_employee_default_llm_does_not_override_server(self):
        """LLMSettings() with no explicit fields should not override server settings."""
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "EMPLA_LLM_PRIMARY_MODEL": "gpt-4o",
            "EMPLA_LLM_TEMPERATURE": "0.3",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = EmplaSettings(_env_file=None)
        # Employee uses defaults (no fields explicitly set)
        employee_llm = LLMSettings()
        config = resolve_llm_config(settings, employee_llm=employee_llm)
        # Server settings should win since employee didn't explicitly set anything
        assert config.primary_model == "gpt-4o"
        assert config.temperature == 0.3

    def test_tenant_overrides_server(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
            settings = EmplaSettings(_env_file=None)
        tenant = {"primary_model": "claude-opus-4"}
        config = resolve_llm_config(settings, tenant_settings=tenant)
        assert config.primary_model == "claude-opus-4"

    def test_tenant_overrides_temperature(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
            settings = EmplaSettings(_env_file=None)
        tenant = {"temperature": 0.1, "max_tokens": 16384}
        config = resolve_llm_config(settings, tenant_settings=tenant)
        assert config.temperature == 0.1
        assert config.max_tokens == 16384

    def test_employee_overrides_tenant(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
            settings = EmplaSettings(_env_file=None)
        tenant = {"primary_model": "claude-opus-4"}
        employee_llm = LLMSettings(primary_model="gpt-4o")
        config = resolve_llm_config(settings, tenant_settings=tenant, employee_llm=employee_llm)
        assert config.primary_model == "gpt-4o"

    def test_api_keys_always_from_server(self):
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "OPENAI_API_KEY": "sk-openai",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = EmplaSettings(_env_file=None)
        employee_llm = LLMSettings(primary_model="gpt-4o")
        config = resolve_llm_config(settings, employee_llm=employee_llm)
        assert config.anthropic_api_key == "sk-ant-test"
        assert config.openai_api_key == "sk-openai"


# ============================================================================
# get_settings() / clear_settings_cache()
# ============================================================================


class TestSettingsSingleton:
    def test_get_settings_returns_same_instance(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_clear_cache_resets_singleton(self):
        s1 = get_settings()
        clear_settings_cache()
        s2 = get_settings()
        assert s1 is not s2

    def test_clear_cache_picks_up_new_env(self):
        s1 = get_settings()
        original_env = s1.env

        with patch.dict(os.environ, {"EMPLA_ENV": "test-isolation"}, clear=False):
            clear_settings_cache()
            s2 = get_settings()
            assert s2.env == "test-isolation"

        # Clean up
        clear_settings_cache()
