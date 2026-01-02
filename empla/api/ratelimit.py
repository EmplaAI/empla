"""
empla.api.ratelimit - Simple Rate Limiting for API Endpoints

Provides in-memory rate limiting for API endpoints. Suitable for single-instance
deployments. For multi-instance deployments, use Redis-based rate limiting.

Usage:
    from empla.api.ratelimit import RateLimiter, RateLimitExceeded

    # Create a rate limiter: 10 requests per minute
    limiter = RateLimiter(max_requests=10, window_seconds=60)

    @router.get("/endpoint")
    async def endpoint(request: Request):
        client_ip = request.client.host
        if not limiter.is_allowed(client_ip):
            raise RateLimitExceeded()
        return {"status": "ok"}
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


class RateLimitExceeded(HTTPException):
    """Exception raised when rate limit is exceeded."""

    def __init__(
        self,
        retry_after: int = 60,
        detail: str = "Too many requests. Please try again later.",
    ) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(retry_after)},
        )
        self.retry_after = retry_after


@dataclass
class RateLimitState:
    """Tracks rate limit state for a single key."""

    request_times: list[float] = field(default_factory=list)


class RateLimiter:
    """
    Simple in-memory rate limiter using sliding window algorithm.

    Not suitable for multi-instance deployments without shared state (e.g., Redis).

    Attributes:
        max_requests: Maximum number of requests allowed in the window
        window_seconds: Size of the sliding window in seconds

    Example:
        >>> limiter = RateLimiter(max_requests=5, window_seconds=60)
        >>> limiter.is_allowed("user_123")  # True
        >>> # ... 5 more requests ...
        >>> limiter.is_allowed("user_123")  # False
    """

    def __init__(
        self,
        max_requests: int = 10,
        window_seconds: int = 60,
        cleanup_interval: int = 300,
    ) -> None:
        """
        Initialize the rate limiter.

        Args:
            max_requests: Maximum requests allowed per window
            window_seconds: Window size in seconds
            cleanup_interval: How often to clean up old entries (seconds)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.cleanup_interval = cleanup_interval
        self._states: dict[str, RateLimitState] = defaultdict(RateLimitState)
        self._lock = Lock()
        self._last_cleanup = time.time()

    def is_allowed(self, key: str) -> bool:
        """
        Check if a request is allowed for the given key.

        Args:
            key: Identifier for rate limiting (e.g., IP address, user ID)

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            # Periodic cleanup of old entries
            if now - self._last_cleanup > self.cleanup_interval:
                self._cleanup(now)

            state = self._states[key]

            # Remove old requests outside the window
            state.request_times = [t for t in state.request_times if t > cutoff]

            # Check if under limit
            if len(state.request_times) >= self.max_requests:
                logger.warning(
                    f"Rate limit exceeded for key: {key[:20]}...",
                    extra={"key_prefix": key[:20], "requests_in_window": len(state.request_times)},
                )
                return False

            # Record this request
            state.request_times.append(now)
            return True

    def get_remaining(self, key: str) -> int:
        """
        Get remaining requests allowed for the key.

        Args:
            key: Identifier for rate limiting

        Returns:
            Number of remaining requests in current window
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            state = self._states[key]
            current_count = len([t for t in state.request_times if t > cutoff])
            return max(0, self.max_requests - current_count)

    def get_reset_time(self, key: str) -> float:
        """
        Get time until rate limit resets for the key.

        Args:
            key: Identifier for rate limiting

        Returns:
            Seconds until oldest request expires from window
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            state = self._states[key]
            valid_times = [t for t in state.request_times if t > cutoff]

            if not valid_times:
                return 0

            oldest = min(valid_times)
            return max(0, oldest + self.window_seconds - now)

    def _cleanup(self, now: float) -> None:
        """Remove stale entries to prevent memory growth."""
        cutoff = now - self.window_seconds
        keys_to_remove = []

        for key, state in self._states.items():
            # Remove old requests
            state.request_times = [t for t in state.request_times if t > cutoff]
            # Mark empty states for removal
            if not state.request_times:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._states[key]

        self._last_cleanup = now

        if keys_to_remove:
            logger.debug(f"Rate limiter cleanup: removed {len(keys_to_remove)} stale entries")


def get_client_identifier(request: Request) -> str:
    """
    Extract client identifier from request for rate limiting.

    Uses X-Forwarded-For if behind proxy, otherwise client IP.

    Args:
        request: FastAPI request object

    Returns:
        Client identifier string
    """
    # Check for forwarded header (behind proxy/load balancer)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP in the chain (original client)
        return forwarded.split(",")[0].strip()

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return "unknown"


# Default rate limiters for common use cases
oauth_callback_limiter = RateLimiter(
    max_requests=10,  # 10 OAuth callbacks per IP
    window_seconds=60,  # per minute
)

api_default_limiter = RateLimiter(
    max_requests=100,  # 100 requests per IP
    window_seconds=60,  # per minute
)
