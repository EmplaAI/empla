"""
empla.api.v1.endpoints.metrics - Cycle Metrics API

Dashboard-facing endpoints for BDI loop performance metrics.
Reads from the Metric table populated by the loop's _record_cycle_metrics().
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from empla.api.deps import CurrentUser, DBSession
from empla.models.audit import Metric

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Response Models
# ============================================================================


class MetricPoint(BaseModel):
    """Single metric data point."""

    model_config = ConfigDict(from_attributes=True)

    metric_name: str
    value: float
    timestamp: datetime
    tags: dict[str, Any] = Field(default_factory=dict)


class MetricSummary(BaseModel):
    """Aggregated metrics for a time range."""

    employee_id: UUID
    hours: int
    cycle_count: int
    avg_duration_seconds: float
    max_duration_seconds: float
    success_rate: float
    total_tool_calls: int
    tool_failure_rate: float
    avg_tool_latency_ms: float


class MetricListResponse(BaseModel):
    """Paginated metric points."""

    items: list[MetricPoint]
    total: int
    page: int
    pages: int


class CostSummary(BaseModel):
    """LLM cost summary for a time range."""

    employee_id: UUID
    hours: int
    total_cost_usd: float
    avg_cost_per_cycle: float
    total_cycles: int
    total_input_tokens: int
    total_output_tokens: int


class CostHistoryPoint(BaseModel):
    """Single cost data point."""

    timestamp: datetime
    cost_usd: float
    cycle: int | None = None


class CostHistoryResponse(BaseModel):
    """Cost time-series data."""

    items: list[CostHistoryPoint]
    total: int


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/employees/{employee_id}/summary",
    response_model=MetricSummary,
)
async def get_metric_summary(
    employee_id: UUID,
    db: DBSession,
    auth: CurrentUser,
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> MetricSummary:
    """
    Get aggregated metrics for an employee over a time window.

    Args:
        employee_id: Employee UUID.
        db: Database session.
        auth: Authenticated user context.
        hours: Lookback window in hours (default 24, max 168/7 days).

    Returns:
        Aggregated cycle duration, success rate, tool stats.
    """
    since = datetime.now(UTC) - timedelta(hours=hours)

    # Cycle duration stats
    duration_query = select(
        func.count().label("cycle_count"),
        func.avg(Metric.value).label("avg_duration"),
        func.max(Metric.value).label("max_duration"),
    ).where(
        Metric.tenant_id == auth.tenant_id,
        Metric.employee_id == employee_id,
        Metric.metric_name == "cycle.duration_seconds",
        Metric.timestamp >= since,
        Metric.deleted_at.is_(None),
    )
    result = await db.execute(duration_query)
    row = result.one()
    cycle_count = row.cycle_count or 0
    avg_duration = float(row.avg_duration or 0)
    max_duration = float(row.max_duration or 0)

    # Success rate
    success_query = select(func.avg(Metric.value)).where(
        Metric.tenant_id == auth.tenant_id,
        Metric.employee_id == employee_id,
        Metric.metric_name == "cycle.success",
        Metric.timestamp >= since,
        Metric.deleted_at.is_(None),
    )
    success_result = await db.execute(success_query)
    success_scalar = success_result.scalar()
    success_rate = float(success_scalar) if success_scalar is not None else 0.0

    # Tool call totals
    tool_total_query = select(func.sum(Metric.value)).where(
        Metric.tenant_id == auth.tenant_id,
        Metric.employee_id == employee_id,
        Metric.metric_name == "tool.calls_total",
        Metric.timestamp >= since,
        Metric.deleted_at.is_(None),
    )
    tool_total = float((await db.execute(tool_total_query)).scalar() or 0)

    tool_failed_query = select(func.sum(Metric.value)).where(
        Metric.tenant_id == auth.tenant_id,
        Metric.employee_id == employee_id,
        Metric.metric_name == "tool.calls_failed",
        Metric.timestamp >= since,
        Metric.deleted_at.is_(None),
    )
    tool_failed = float((await db.execute(tool_failed_query)).scalar() or 0)

    tool_failure_rate = tool_failed / tool_total if tool_total > 0 else 0.0

    # Weighted avg tool latency: SUM(latency_sum) / SUM(calls_total)
    latency_sum_query = select(func.sum(Metric.value)).where(
        Metric.tenant_id == auth.tenant_id,
        Metric.employee_id == employee_id,
        Metric.metric_name == "tool.latency_sum_ms",
        Metric.timestamp >= since,
        Metric.deleted_at.is_(None),
    )
    latency_sum = float((await db.execute(latency_sum_query)).scalar() or 0)
    avg_latency = latency_sum / tool_total if tool_total > 0 else 0.0

    return MetricSummary(
        employee_id=employee_id,
        hours=hours,
        cycle_count=cycle_count,
        avg_duration_seconds=round(avg_duration, 3),
        max_duration_seconds=round(max_duration, 3),
        success_rate=round(success_rate, 4),
        total_tool_calls=int(tool_total),
        tool_failure_rate=round(tool_failure_rate, 4),
        avg_tool_latency_ms=round(avg_latency, 1),
    )


@router.get(
    "/employees/{employee_id}/history",
    response_model=MetricListResponse,
)
async def get_metric_history(
    employee_id: UUID,
    db: DBSession,
    auth: CurrentUser,
    metric_name: Annotated[str, Query()] = "cycle.duration_seconds",
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> MetricListResponse:
    """
    Get time-series metric data for an employee.

    Args:
        employee_id: Employee UUID.
        db: Database session.
        auth: Authenticated user context.
        metric_name: Which metric to query (e.g. "cycle.duration_seconds").
        hours: Lookback window in hours.
        page: Page number.
        page_size: Results per page.

    Returns:
        Paginated list of metric data points ordered by time (newest first).
    """
    since = datetime.now(UTC) - timedelta(hours=hours)

    base_filter = [
        Metric.tenant_id == auth.tenant_id,
        Metric.employee_id == employee_id,
        Metric.metric_name == metric_name,
        Metric.timestamp >= since,
        Metric.deleted_at.is_(None),
    ]

    # Count
    count_query = select(func.count()).where(*base_filter)
    total = (await db.execute(count_query)).scalar() or 0

    # Fetch page
    query = (
        select(Metric)
        .where(*base_filter)
        .order_by(Metric.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    items = [
        MetricPoint(
            metric_name=m.metric_name,
            value=m.value,
            timestamp=m.timestamp,
            tags=m.tags,
        )
        for m in result.scalars()
    ]

    pages = (total + page_size - 1) // page_size if total > 0 else 0

    return MetricListResponse(
        items=items,
        total=total,
        page=page,
        pages=pages,
    )


# ============================================================================
# Cost Endpoints
# ============================================================================


@router.get(
    "/employees/{employee_id}/costs",
    response_model=CostSummary,
)
async def get_cost_summary(
    employee_id: UUID,
    db: DBSession,
    auth: CurrentUser,
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> CostSummary:
    """Get aggregated LLM cost summary for an employee."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    base = [
        Metric.tenant_id == auth.tenant_id,
        Metric.employee_id == employee_id,
        Metric.timestamp >= since,
        Metric.deleted_at.is_(None),
    ]

    # Total cost
    cost_result = await db.execute(
        select(func.sum(Metric.value)).where(*base, Metric.metric_name == "llm.cost_usd")
    )
    total_cost = float(cost_result.scalar() or 0)

    # Total cycles (from cycle.duration_seconds count)
    cycle_result = await db.execute(
        select(func.count()).where(*base, Metric.metric_name == "cycle.duration_seconds")
    )
    total_cycles = int(cycle_result.scalar() or 0)

    # Token totals
    input_result = await db.execute(
        select(func.sum(Metric.value)).where(*base, Metric.metric_name == "llm.input_tokens")
    )
    total_input = int(input_result.scalar() or 0)

    output_result = await db.execute(
        select(func.sum(Metric.value)).where(*base, Metric.metric_name == "llm.output_tokens")
    )
    total_output = int(output_result.scalar() or 0)

    return CostSummary(
        employee_id=employee_id,
        hours=hours,
        total_cost_usd=round(total_cost, 4),
        avg_cost_per_cycle=round(total_cost / total_cycles, 6) if total_cycles > 0 else 0.0,
        total_cycles=total_cycles,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
    )


@router.get(
    "/employees/{employee_id}/costs/history",
    response_model=CostHistoryResponse,
)
async def get_cost_history(
    employee_id: UUID,
    db: DBSession,
    auth: CurrentUser,
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> CostHistoryResponse:
    """Get time-series LLM cost data for an employee."""
    since = datetime.now(UTC) - timedelta(hours=hours)

    query = (
        select(Metric)
        .where(
            Metric.tenant_id == auth.tenant_id,
            Metric.employee_id == employee_id,
            Metric.metric_name == "llm.cost_usd",
            Metric.timestamp >= since,
            Metric.deleted_at.is_(None),
        )
        .order_by(Metric.timestamp.desc())
        .limit(500)
    )
    result = await db.execute(query)
    items = [
        CostHistoryPoint(
            timestamp=m.timestamp,
            cost_usd=m.value,
            cycle=m.tags.get("cycle") if m.tags else None,
        )
        for m in result.scalars()
    ]

    return CostHistoryResponse(items=items, total=len(items))
