"""
Tests for empla.api.ratelimit module.

Tests:
- Rate limiter basic functionality
- Sliding window behavior
- Reset time calculation
- Client identifier extraction
"""

import time
from unittest.mock import MagicMock

from empla.api.ratelimit import (
    RateLimiter,
    RateLimitExceeded,
    get_client_identifier,
)


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_allows_requests_under_limit(self):
        """Requests under the limit should be allowed."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        key = "test_key"

        for _ in range(5):
            assert limiter.is_allowed(key) is True

    def test_blocks_requests_at_limit(self):
        """Requests at the limit should be blocked."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        key = "test_key"

        # Exhaust the limit
        for _ in range(5):
            limiter.is_allowed(key)

        # Next request should be blocked
        assert limiter.is_allowed(key) is False

    def test_different_keys_tracked_separately(self):
        """Different keys should have separate limits."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)

        # Exhaust limit for key1
        assert limiter.is_allowed("key1") is True
        assert limiter.is_allowed("key1") is True
        assert limiter.is_allowed("key1") is False

        # key2 should still have full allowance
        assert limiter.is_allowed("key2") is True
        assert limiter.is_allowed("key2") is True
        assert limiter.is_allowed("key2") is False

    def test_get_remaining(self):
        """get_remaining should return correct count."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        key = "test_key"

        assert limiter.get_remaining(key) == 5

        limiter.is_allowed(key)
        assert limiter.get_remaining(key) == 4

        limiter.is_allowed(key)
        limiter.is_allowed(key)
        assert limiter.get_remaining(key) == 2

    def test_get_reset_time_returns_zero_for_no_requests(self):
        """get_reset_time should return 0 for keys with no requests."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        assert limiter.get_reset_time("unknown_key") == 0

    def test_get_reset_time_returns_positive_for_active_key(self):
        """get_reset_time should return positive value for active keys."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        key = "test_key"

        limiter.is_allowed(key)
        reset_time = limiter.get_reset_time(key)

        # Should be close to window_seconds (60)
        assert 0 < reset_time <= 60


class TestRateLimitExceeded:
    """Tests for RateLimitExceeded exception."""

    def test_default_values(self):
        """Exception should have sensible defaults."""
        exc = RateLimitExceeded()

        assert exc.status_code == 429
        assert exc.retry_after == 60
        assert "Retry-After" in exc.headers
        assert exc.headers["Retry-After"] == "60"

    def test_custom_retry_after(self):
        """Should accept custom retry_after value."""
        exc = RateLimitExceeded(retry_after=120)

        assert exc.retry_after == 120
        assert exc.headers["Retry-After"] == "120"

    def test_custom_detail(self):
        """Should accept custom detail message."""
        exc = RateLimitExceeded(detail="Custom error message")
        assert exc.detail == "Custom error message"


class TestGetClientIdentifier:
    """Tests for get_client_identifier function."""

    def test_uses_x_forwarded_for_header(self):
        """Should use X-Forwarded-For header when present."""
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "1.2.3.4"}
        request.client = MagicMock(host="5.6.7.8")

        assert get_client_identifier(request) == "1.2.3.4"

    def test_uses_first_ip_from_forwarded_chain(self):
        """Should use first IP from X-Forwarded-For chain."""
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "1.2.3.4, 10.0.0.1, 192.168.1.1"}
        request.client = MagicMock(host="5.6.7.8")

        assert get_client_identifier(request) == "1.2.3.4"

    def test_falls_back_to_client_host(self):
        """Should fall back to client host when no forwarded header."""
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock(host="5.6.7.8")

        assert get_client_identifier(request) == "5.6.7.8"

    def test_returns_unknown_when_no_client(self):
        """Should return 'unknown' when client is None."""
        request = MagicMock()
        request.headers = {}
        request.client = None

        assert get_client_identifier(request) == "unknown"


class TestRateLimiterCleanup:
    """Tests for rate limiter cleanup functionality."""

    def test_cleanup_removes_expired_entries(self):
        """Cleanup should remove expired entries."""
        limiter = RateLimiter(
            max_requests=5,
            window_seconds=1,  # Very short window
            cleanup_interval=0,  # Clean up every time
        )

        # Make some requests
        limiter.is_allowed("key1")
        limiter.is_allowed("key2")

        # Wait for window to expire
        time.sleep(1.1)

        # Trigger cleanup by making a new request
        limiter.is_allowed("key3")

        # Old keys should have been cleaned up
        # (no requests means they're removed)
        assert limiter.get_remaining("key1") == 5
        assert limiter.get_remaining("key2") == 5
