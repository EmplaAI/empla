"""
empla.services.metrics - Cycle Metrics Recording

Records per-cycle performance metrics to the Metric table for dashboard
visibility. Wired into the BDI loop via _record_cycle_metrics().

Metrics recorded per cycle:
  cycle.duration_seconds    — histogram — wall-clock time for the cycle
  cycle.success             — gauge     — 1.0 if cycle succeeded, 0.0 if failed
  tool.calls_total          — counter   — tool calls this cycle (delta, not cumulative)
  tool.calls_failed         — counter   — failed tool calls this cycle (delta)
  tool.latency_sum_ms       — counter   — total tool latency this cycle (for weighted avg)
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.audit import Metric

logger = logging.getLogger(__name__)

# Previous cycle's cumulative tool stats, keyed by employee_id.
# Used to compute per-cycle deltas from the cumulative HealthMonitor counters.
_previous_tool_stats: dict[UUID, dict[str, float]] = {}


def _compute_tool_deltas(
    employee_id: UUID,
    tool_stats: list[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, float]]:
    """Compute per-cycle tool call deltas from cumulative HealthMonitor stats.

    Returns (deltas, new_snapshot). The caller must persist new_snapshot
    to _previous_tool_stats only after successful DB flush.
    """
    current_total = sum(s.get("total_calls", 0) for s in tool_stats)
    current_failed = sum(s.get("failure_count", 0) + s.get("timeout_count", 0) for s in tool_stats)
    current_latency_sum = sum(
        s.get("avg_latency_ms", 0) * s.get("total_calls", 0) for s in tool_stats
    )

    prev = _previous_tool_stats.get(employee_id, {})
    prev_total = prev.get("total", 0)
    prev_failed = prev.get("failed", 0)
    prev_latency_sum = prev.get("latency_sum", 0)

    delta_total = max(0, current_total - prev_total)
    delta_failed = max(0, current_failed - prev_failed)
    delta_latency_sum = max(0, current_latency_sum - prev_latency_sum)

    new_snapshot = {
        "total": current_total,
        "failed": current_failed,
        "latency_sum": current_latency_sum,
    }

    deltas = {
        "total": float(delta_total),
        "failed": float(delta_failed),
        "latency_sum": round(delta_latency_sum, 1),
    }

    return deltas, new_snapshot


async def record_cycle_metrics(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    employee_id: UUID,
    cycle_count: int,
    duration_seconds: float,
    success: bool,
    tool_stats: list[dict[str, Any]] | None = None,
) -> dict[str, float] | None:
    """Record metrics for a completed BDI cycle.

    Creates multiple Metric rows — one per metric name — so the dashboard
    can query and aggregate by metric_name + time range.

    Args:
        db: Async database session (caller commits).
        tenant_id: Tenant UUID.
        employee_id: Employee UUID.
        cycle_count: The cycle number (for tags).
        duration_seconds: Wall-clock cycle duration.
        success: Whether the cycle completed without error.
        tool_stats: Optional list of dicts from IntegrationHealthMonitor.get_all_status().

    Returns:
        New tool stats snapshot to persist in _previous_tool_stats (caller
        should assign only after successful commit), or None if no tool stats.
    """
    metrics = [
        Metric(
            tenant_id=tenant_id,
            employee_id=employee_id,
            metric_name="cycle.duration_seconds",
            metric_type="histogram",
            value=round(duration_seconds, 3),
            tags={"cycle": cycle_count},
        ),
        Metric(
            tenant_id=tenant_id,
            employee_id=employee_id,
            metric_name="cycle.success",
            metric_type="gauge",
            value=1.0 if success else 0.0,
            tags={"cycle": cycle_count},
        ),
    ]

    # Tool call stats — compute per-cycle deltas from cumulative counters
    new_snapshot = None
    if tool_stats:
        deltas, new_snapshot = _compute_tool_deltas(employee_id, tool_stats)
        metrics.extend(
            [
                Metric(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    metric_name="tool.calls_total",
                    metric_type="counter",
                    value=deltas["total"],
                    tags={"cycle": cycle_count},
                ),
                Metric(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    metric_name="tool.calls_failed",
                    metric_type="counter",
                    value=deltas["failed"],
                    tags={"cycle": cycle_count},
                ),
                Metric(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    metric_name="tool.latency_sum_ms",
                    metric_type="counter",
                    value=deltas["latency_sum"],
                    tags={"cycle": cycle_count},
                ),
            ]
        )

    for m in metrics:
        db.add(m)

    try:
        await db.flush()
    except Exception:
        logger.warning(
            "Failed to flush cycle metrics, rolling back",
            exc_info=True,
            extra={"employee_id": str(employee_id), "cycle": cycle_count},
        )
        try:
            await db.rollback()
        except Exception:
            logger.debug("Rollback after metrics flush failure also failed", exc_info=True)
        return None

    # Return snapshot for caller to persist after commit
    return new_snapshot
