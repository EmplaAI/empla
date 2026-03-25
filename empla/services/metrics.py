"""
empla.services.metrics - Cycle Metrics Recording

Records per-cycle performance metrics to the Metric table for dashboard
visibility. Wired into the BDI loop via HOOK_CYCLE_END.

Metrics recorded per cycle:
  cycle.duration_seconds    — histogram — wall-clock time for the cycle
  cycle.success             — gauge     — 1.0 if cycle succeeded, 0.0 if failed
  tool.calls_total          — counter   — total tool calls in this cycle
  tool.calls_failed         — counter   — failed tool calls in this cycle
  tool.avg_latency_ms       — gauge     — average tool call latency
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from empla.models.audit import Metric

logger = logging.getLogger(__name__)


async def record_cycle_metrics(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    employee_id: UUID,
    cycle_count: int,
    duration_seconds: float,
    success: bool,
    tool_stats: dict[str, Any] | None = None,
) -> None:
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
        tool_stats: Optional dict from IntegrationHealthMonitor.get_all_status().
    """
    base_tags = {"cycle": cycle_count}

    metrics = [
        Metric(
            tenant_id=tenant_id,
            employee_id=employee_id,
            metric_name="cycle.duration_seconds",
            metric_type="histogram",
            value=round(duration_seconds, 3),
            tags=base_tags,
        ),
        Metric(
            tenant_id=tenant_id,
            employee_id=employee_id,
            metric_name="cycle.success",
            metric_type="gauge",
            value=1.0 if success else 0.0,
            tags=base_tags,
        ),
    ]

    # Tool call stats from health monitor
    if tool_stats:
        total_calls = sum(s.get("total_calls", 0) for s in tool_stats)
        failed_calls = sum(
            s.get("failure_count", 0) + s.get("timeout_count", 0) for s in tool_stats
        )
        avg_latency = 0.0
        if total_calls > 0:
            total_duration = sum(
                s.get("avg_latency_ms", 0) * s.get("total_calls", 0) for s in tool_stats
            )
            avg_latency = total_duration / total_calls

        metrics.extend(
            [
                Metric(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    metric_name="tool.calls_total",
                    metric_type="counter",
                    value=float(total_calls),
                    tags=base_tags,
                ),
                Metric(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    metric_name="tool.calls_failed",
                    metric_type="counter",
                    value=float(failed_calls),
                    tags=base_tags,
                ),
                Metric(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    metric_name="tool.avg_latency_ms",
                    metric_type="gauge",
                    value=round(avg_latency, 1),
                    tags=base_tags,
                ),
            ]
        )

    for m in metrics:
        db.add(m)

    try:
        await db.flush()
    except Exception:
        logger.warning(
            "Failed to flush cycle metrics",
            exc_info=True,
            extra={"employee_id": str(employee_id), "cycle": cycle_count},
        )
