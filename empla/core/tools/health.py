"""
empla.core.tools.health - Integration Health Monitor

Tracks per-integration tool call success/failure/latency. The BDI loop
queries this to form beliefs about tool availability ("CRM is down",
"Calendar is rate-limited"). The dashboard API exposes it for visibility.

Architecture:
  ToolRouter.execute_tool_call()
       │
       ▼ (after each call)
  HealthMonitor.record(integration, success, duration_ms, error?)
       │
       ▼
  Per-integration stats: success_count, failure_count, avg_latency,
  last_error, last_success, status (healthy/degraded/down)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IntegrationHealth:
    """Health stats for a single integration."""

    name: str
    success_count: int = 0
    failure_count: int = 0
    timeout_count: int = 0
    total_duration_ms: float = 0.0
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_error: str | None = None

    @property
    def total_calls(self) -> int:
        return self.success_count + self.failure_count + self.timeout_count

    @property
    def avg_latency_ms(self) -> float:
        return self.total_duration_ms / max(self.total_calls, 1)

    @property
    def error_rate(self) -> float:
        total = self.total_calls
        if total == 0:
            return 0.0
        return (self.failure_count + self.timeout_count) / total

    @property
    def timeout_rate(self) -> float:
        total = self.total_calls
        if total == 0:
            return 0.0
        return self.timeout_count / total

    @property
    def status(self) -> str:
        """Derive health status from cumulative call outcomes.

        - "healthy": error rate < 20%
        - "degraded": error rate 20-50% or timeout rate > 5%
        - "down": error rate > 50%

        Note: Uses all-time counters. Call reset() at cycle boundaries
        to get fresh per-cycle status if needed.
        """
        if self.total_calls == 0:
            return "unknown"
        if self.error_rate > 0.5:
            return "down"
        if self.error_rate >= 0.2 or self.timeout_rate > 0.05:
            return "degraded"
        return "healthy"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "timeout_count": self.timeout_count,
            "total_calls": self.total_calls,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "error_rate": round(self.error_rate, 3),
            "last_error": self.last_error,
        }


class IntegrationHealthMonitor:
    """
    Tracks health of integrations based on tool call outcomes.

    Updated by ToolRouter after every tool call. Queried by:
    - BDI loop (to form beliefs about tool availability)
    - Dashboard API (to show integration status)

    Example:
        >>> monitor = IntegrationHealthMonitor()
        >>> monitor.record("hubspot", success=True, duration_ms=150.0)
        >>> monitor.record("hubspot", success=False, duration_ms=30000.0, error="timeout")
        >>> monitor.get_status("hubspot")
        {"name": "hubspot", "status": "degraded", ...}
    """

    def __init__(self) -> None:
        self._integrations: dict[str, IntegrationHealth] = {}

    def record(
        self,
        integration: str,
        success: bool,
        duration_ms: float,
        error: str | None = None,
        is_timeout: bool = False,
    ) -> None:
        """Record a tool call outcome for an integration."""
        if integration not in self._integrations:
            self._integrations[integration] = IntegrationHealth(name=integration)

        health = self._integrations[integration]
        health.total_duration_ms += duration_ms
        now = time.time()

        if success:
            health.success_count += 1
            health.last_success_at = now
        elif is_timeout:
            health.timeout_count += 1
            health.last_failure_at = now
            health.last_error = error or "timeout"
        else:
            health.failure_count += 1
            health.last_failure_at = now
            health.last_error = error

    def get_status(self, integration: str) -> dict[str, Any]:
        """Get health status for a specific integration."""
        health = self._integrations.get(integration)
        if health is None:
            return IntegrationHealth(name=integration).to_dict()
        return health.to_dict()

    def get_all_status(self) -> list[dict[str, Any]]:
        """Get health status for all tracked integrations."""
        return [h.to_dict() for h in self._integrations.values()]

    def get_beliefs(self) -> list[dict[str, Any]]:
        """Generate BDI-compatible belief updates from health status.

        Returns a list of belief dicts that the BDI loop can feed into
        the belief system. Only generates beliefs for non-healthy integrations.
        """
        beliefs = []
        for health in self._integrations.values():
            if health.status == "down":
                beliefs.append(
                    {
                        "subject": health.name,
                        "predicate": "availability",
                        "belief_object": {
                            "status": "down",
                            "error": health.last_error,
                            "error_rate": health.error_rate,
                        },
                        "confidence": 0.95,
                        "source": "health_monitor",
                    }
                )
            elif health.status == "degraded":
                beliefs.append(
                    {
                        "subject": health.name,
                        "predicate": "availability",
                        "belief_object": {
                            "status": "degraded",
                            "error": health.last_error,
                            "avg_latency_ms": health.avg_latency_ms,
                        },
                        "confidence": 0.8,
                        "source": "health_monitor",
                    }
                )
        return beliefs

    def reset(self) -> None:
        """Reset all health stats."""
        self._integrations.clear()
