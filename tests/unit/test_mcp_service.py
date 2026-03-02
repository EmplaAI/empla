"""
tests/unit/test_mcp_service.py - MCP Service Unit Tests

Tests for:
- build_auth_headers (credential data → HTTP headers)
- _resolve_credential_type (auth_type → credential_type mapping)
"""

import pytest

from empla.services.integrations.mcp_service import (
    _resolve_credential_type,
    build_auth_headers,
)


class TestBuildAuthHeaders:
    """Tests for build_auth_headers."""

    def test_api_key_produces_correct_header(self):
        headers = build_auth_headers("api_key", {"api_key": "sk-123"})
        assert headers == {"X-API-Key": "sk-123"}

    def test_bearer_token_produces_correct_header(self):
        headers = build_auth_headers("bearer_token", {"token": "tok-abc"})
        assert headers == {"Authorization": "Bearer tok-abc"}

    def test_api_key_missing_key_raises(self):
        with pytest.raises(ValueError, match="no 'api_key' key"):
            build_auth_headers("api_key", {"wrong": "value"})

    def test_api_key_empty_key_raises(self):
        with pytest.raises(ValueError, match="no 'api_key' key"):
            build_auth_headers("api_key", {"api_key": ""})

    def test_bearer_token_missing_token_raises(self):
        with pytest.raises(ValueError, match="no 'token' key"):
            build_auth_headers("bearer_token", {"wrong": "value"})

    def test_bearer_token_empty_token_raises(self):
        with pytest.raises(ValueError, match="no 'token' key"):
            build_auth_headers("bearer_token", {"token": ""})

    def test_unsupported_auth_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported auth_type"):
            build_auth_headers("oauth", {"access_token": "tok"})

    def test_unsupported_none_raises(self):
        with pytest.raises(ValueError, match="Unsupported auth_type"):
            build_auth_headers("none", {})


class TestResolveCredentialType:
    """Tests for _resolve_credential_type."""

    def test_api_key(self):
        assert _resolve_credential_type("api_key") == "api_key"

    def test_bearer_token(self):
        assert _resolve_credential_type("bearer_token") == "bearer_token"

    def test_oauth(self):
        assert _resolve_credential_type("oauth") == "oauth_tokens"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown auth_type"):
            _resolve_credential_type("none")

    def test_garbage_raises(self):
        with pytest.raises(ValueError, match="Unknown auth_type"):
            _resolve_credential_type("password")
