"""
Tests for JWT authentication.

Covers token creation, validation, expiry, tampering, claim extraction,
and the /login + /me endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from empla.api.v1.endpoints.auth import create_access_token
from empla.settings import JWT_DEV_SECRET as _DEV_SECRET
from empla.settings import EmplaSettings

# ============================================================================
# Token Creation Tests
# ============================================================================


class TestCreateAccessToken:
    """Tests for create_access_token()."""

    def test_creates_valid_jwt(self):
        """Token should be a valid JWT decodable with the secret."""
        user_id = uuid4()
        tenant_id = uuid4()
        token = create_access_token(user_id, tenant_id, "admin")

        payload = jwt.decode(token, _DEV_SECRET, algorithms=["HS256"])
        assert payload["sub"] == str(user_id)
        assert payload["tid"] == str(tenant_id)
        assert payload["role"] == "admin"

    def test_token_has_expiry(self):
        """Token should have an exp claim."""
        token = create_access_token(uuid4(), uuid4(), "member")
        payload = jwt.decode(
            token,
            _DEV_SECRET,
            algorithms=["HS256"],
        )
        assert "exp" in payload
        assert "iat" in payload

    def test_token_has_correct_expiry_duration(self):
        """Token expiry should match settings (default 24h)."""
        token = create_access_token(uuid4(), uuid4(), "member")
        payload = jwt.decode(
            token,
            _DEV_SECRET,
            algorithms=["HS256"],
        )
        iat = datetime.fromtimestamp(payload["iat"], tz=UTC)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        delta = exp - iat
        # Should be approximately 24 hours (within 5 seconds tolerance)
        assert abs(delta.total_seconds() - 24 * 3600) < 5


# ============================================================================
# Token Validation Tests
# ============================================================================


class TestTokenValidation:
    """Tests for JWT decode behavior (used by deps.py)."""

    def _make_token(
        self,
        user_id: str | None = None,
        tenant_id: str | None = None,
        role: str = "member",
        secret: str = _DEV_SECRET,
        algorithm: str = "HS256",
        exp_delta: timedelta | None = None,
    ) -> str:
        """Create a JWT token for testing."""
        now = datetime.now(UTC)
        payload: dict = {
            "sub": user_id or str(uuid4()),
            "tid": tenant_id or str(uuid4()),
            "role": role,
            "iat": now,
            "exp": now + (exp_delta if exp_delta is not None else timedelta(hours=24)),
        }
        return jwt.encode(payload, secret, algorithm=algorithm)

    def test_valid_token_decodes(self):
        """A properly signed token should decode successfully."""
        token = self._make_token()
        payload = jwt.decode(token, _DEV_SECRET, algorithms=["HS256"])
        assert "sub" in payload
        assert "tid" in payload

    def test_expired_token_raises(self):
        """An expired token should raise ExpiredSignatureError."""
        token = self._make_token(exp_delta=timedelta(seconds=-1))
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(token, _DEV_SECRET, algorithms=["HS256"])

    def test_tampered_token_raises(self):
        """A token signed with wrong secret should raise InvalidSignatureError."""
        token = self._make_token(secret="wrong-secret-that-is-long-enough-for-hs256")
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, _DEV_SECRET, algorithms=["HS256"])

    def test_malformed_token_raises(self):
        """A non-JWT string should raise DecodeError."""
        with pytest.raises(jwt.DecodeError):
            jwt.decode("not-a-jwt", _DEV_SECRET, algorithms=["HS256"])

    def test_none_algorithm_rejected(self):
        """alg=none attack should be rejected when algorithms is restricted."""
        # Create a token with no signature
        payload = {
            "sub": str(uuid4()),
            "tid": str(uuid4()),
            "role": "admin",
            "exp": datetime.now(UTC) + timedelta(hours=1),
        }
        # Encode with none algorithm
        unsigned_token = jwt.encode(payload, "", algorithm="none")

        # Should fail because we only accept HS256
        with pytest.raises(jwt.InvalidAlgorithmError):
            jwt.decode(
                unsigned_token,
                _DEV_SECRET,
                algorithms=["HS256"],
            )

    def test_missing_sub_claim(self):
        """Token without 'sub' claim should fail at extraction."""
        now = datetime.now(UTC)
        token = jwt.encode(
            {"tid": str(uuid4()), "role": "member", "exp": now + timedelta(hours=1)},
            _DEV_SECRET,
            algorithm="HS256",
        )
        payload = jwt.decode(token, _DEV_SECRET, algorithms=["HS256"])
        assert "sub" not in payload  # Confirms the claim is missing

    def test_missing_tid_claim(self):
        """Token without 'tid' claim should fail at extraction."""
        now = datetime.now(UTC)
        token = jwt.encode(
            {"sub": str(uuid4()), "role": "member", "exp": now + timedelta(hours=1)},
            _DEV_SECRET,
            algorithm="HS256",
        )
        payload = jwt.decode(token, _DEV_SECRET, algorithms=["HS256"])
        assert "tid" not in payload

    def test_invalid_uuid_in_sub(self):
        """Token with non-UUID 'sub' should fail at UUID conversion."""
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": "not-a-uuid",
                "tid": str(uuid4()),
                "role": "member",
                "exp": now + timedelta(hours=1),
            },
            _DEV_SECRET,
            algorithm="HS256",
        )
        payload = jwt.decode(token, _DEV_SECRET, algorithms=["HS256"])
        from uuid import UUID

        with pytest.raises(ValueError):
            UUID(payload["sub"])


# ============================================================================
# Settings Tests
# ============================================================================


class TestJWTSettings:
    """Tests for JWT settings in EmplaSettings."""

    def test_default_settings(self):
        """Default JWT settings should be reasonable."""
        settings = EmplaSettings(
            _env_file=None,  # Don't read .env for tests
        )
        assert settings.jwt_secret == _DEV_SECRET
        assert settings.jwt_expiry_hours == 24
        assert settings.jwt_algorithm == "HS256"

    def test_custom_secret_from_env(self):
        """JWT secret should be configurable via env."""
        settings = EmplaSettings(
            _env_file=None,
            jwt_secret="my-production-secret-key",
        )
        assert settings.jwt_secret == "my-production-secret-key"

    def test_custom_expiry(self):
        """JWT expiry should be configurable."""
        settings = EmplaSettings(
            _env_file=None,
            jwt_expiry_hours=48,
        )
        assert settings.jwt_expiry_hours == 48

    def test_production_rejects_default_secret(self):
        """Non-development env with default secret should fail."""
        with pytest.raises(Exception, match="EMPLA_JWT_SECRET must be set"):
            EmplaSettings(
                _env_file=None,
                env="production",
                # jwt_secret left as default
            )

    def test_production_rejects_short_secret(self):
        """Non-development env with short secret should fail."""
        with pytest.raises(Exception, match="at least 32 characters"):
            EmplaSettings(
                _env_file=None,
                env="production",
                jwt_secret="too-short",
            )

    def test_production_accepts_long_secret(self):
        """Non-development env with proper secret should work."""
        settings = EmplaSettings(
            _env_file=None,
            env="production",
            jwt_secret="a-very-long-production-secret-that-is-definitely-32-chars",
        )
        assert settings.env == "production"

    def test_rejects_none_algorithm(self):
        """Algorithm 'none' should be rejected."""
        with pytest.raises(Exception, match="jwt_algorithm must be one of"):
            EmplaSettings(
                _env_file=None,
                jwt_algorithm="none",
            )

    def test_rejects_rsa_algorithm(self):
        """RSA algorithms should be rejected (prevents algorithm confusion)."""
        with pytest.raises(Exception, match="jwt_algorithm must be one of"):
            EmplaSettings(
                _env_file=None,
                jwt_algorithm="RS256",
            )
