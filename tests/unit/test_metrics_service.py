"""
Tests for the cycle metrics recording service and API response models.

Covers:
- record_cycle_metrics() persists correct metric rows
- Tool stats delta computation (not cumulative)
- Edge cases (no tool stats, empty tool stats, flush failure)
- MetricSummary and MetricPoint response model validation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from empla.services.metrics import _previous_tool_stats, record_cycle_metrics

# ============================================================================
# record_cycle_metrics Tests
# ============================================================================


class TestRecordCycleMetrics:
    """Tests for the record_cycle_metrics service function."""

    @pytest.fixture(autouse=True)
    def _clear_tool_stats_cache(self):
        """Clear the delta cache between tests."""
        _previous_tool_stats.clear()
        yield
        _previous_tool_stats.clear()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.rollback = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_records_base_metrics(self, mock_db):
        """Should record cycle.duration_seconds and cycle.success."""
        await record_cycle_metrics(
            mock_db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=1,
            duration_seconds=2.5,
            success=True,
        )

        assert mock_db.add.call_count == 2
        metrics = [c.args[0] for c in mock_db.add.call_args_list]
        names = {m.metric_name for m in metrics}
        assert "cycle.duration_seconds" in names
        assert "cycle.success" in names

    @pytest.mark.asyncio
    async def test_success_value(self, mock_db):
        """cycle.success should be 1.0 on success, 0.0 on failure."""
        await record_cycle_metrics(
            mock_db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=1,
            duration_seconds=1.0,
            success=True,
        )
        success_metric = next(
            c.args[0]
            for c in mock_db.add.call_args_list
            if c.args[0].metric_name == "cycle.success"
        )
        assert success_metric.value == 1.0

        mock_db.reset_mock()

        await record_cycle_metrics(
            mock_db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=2,
            duration_seconds=1.0,
            success=False,
        )
        fail_metric = next(
            c.args[0]
            for c in mock_db.add.call_args_list
            if c.args[0].metric_name == "cycle.success"
        )
        assert fail_metric.value == 0.0

    @pytest.mark.asyncio
    async def test_records_tool_stats_deltas(self, mock_db):
        """First cycle should record full counts as deltas (prev is 0)."""
        eid = uuid4()
        tool_stats = [
            {
                "name": "hubspot",
                "total_calls": 10,
                "success_count": 8,
                "failure_count": 1,
                "timeout_count": 1,
                "avg_latency_ms": 150.0,
            },
            {
                "name": "calendar",
                "total_calls": 5,
                "success_count": 5,
                "failure_count": 0,
                "timeout_count": 0,
                "avg_latency_ms": 80.0,
            },
        ]

        await record_cycle_metrics(
            mock_db,
            tenant_id=uuid4(),
            employee_id=eid,
            cycle_count=1,
            duration_seconds=3.0,
            success=True,
            tool_stats=tool_stats,
        )

        assert mock_db.add.call_count == 5  # 2 base + 3 tool
        metrics = [c.args[0] for c in mock_db.add.call_args_list]

        total = next(m for m in metrics if m.metric_name == "tool.calls_total")
        assert total.value == 15.0  # First cycle: full count is the delta

        failed = next(m for m in metrics if m.metric_name == "tool.calls_failed")
        assert failed.value == 2.0

    @pytest.mark.asyncio
    async def test_tool_stats_computes_deltas_across_cycles(self, mock_db):
        """Second cycle should record only the delta from first cycle."""
        eid = uuid4()
        tid = uuid4()

        # Cycle 1: cumulative = 10 calls
        await record_cycle_metrics(
            mock_db,
            tenant_id=tid,
            employee_id=eid,
            cycle_count=1,
            duration_seconds=1.0,
            success=True,
            tool_stats=[
                {"total_calls": 10, "failure_count": 1, "timeout_count": 0, "avg_latency_ms": 100.0}
            ],
        )

        mock_db.reset_mock()

        # Cycle 2: cumulative = 18 calls (delta should be 8)
        await record_cycle_metrics(
            mock_db,
            tenant_id=tid,
            employee_id=eid,
            cycle_count=2,
            duration_seconds=1.0,
            success=True,
            tool_stats=[
                {"total_calls": 18, "failure_count": 3, "timeout_count": 0, "avg_latency_ms": 120.0}
            ],
        )

        metrics = [c.args[0] for c in mock_db.add.call_args_list]
        total = next(m for m in metrics if m.metric_name == "tool.calls_total")
        assert total.value == 8.0  # 18 - 10

        failed = next(m for m in metrics if m.metric_name == "tool.calls_failed")
        assert failed.value == 2.0  # 3 - 1

    @pytest.mark.asyncio
    async def test_no_tool_stats_skips_tool_metrics(self, mock_db):
        """Without tool_stats, only base metrics are recorded."""
        await record_cycle_metrics(
            mock_db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=1,
            duration_seconds=1.0,
            success=True,
            tool_stats=None,
        )

        assert mock_db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_tool_stats_skips_tool_metrics(self, mock_db):
        """Empty tool_stats list should not record tool metrics."""
        await record_cycle_metrics(
            mock_db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=1,
            duration_seconds=1.0,
            success=True,
            tool_stats=[],
        )

        assert mock_db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_flush_failure_rolls_back(self, mock_db):
        """Flush failure should attempt rollback, not crash."""
        mock_db.flush = AsyncMock(side_effect=Exception("DB error"))

        await record_cycle_metrics(
            mock_db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=1,
            duration_seconds=1.0,
            success=True,
        )

        mock_db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_flush_failure_preserves_tool_stats_cache(self, mock_db):
        """On flush failure, _previous_tool_stats should NOT advance."""
        eid = uuid4()
        # Seed baseline
        _previous_tool_stats[eid] = {"total": 5, "failed": 1, "latency_sum": 500.0}
        original = _previous_tool_stats[eid].copy()

        mock_db.flush = AsyncMock(side_effect=Exception("DB error"))

        await record_cycle_metrics(
            mock_db,
            tenant_id=uuid4(),
            employee_id=eid,
            cycle_count=2,
            duration_seconds=1.0,
            success=True,
            tool_stats=[
                {"total_calls": 20, "failure_count": 3, "timeout_count": 0, "avg_latency_ms": 100.0}
            ],
        )

        # Cache should not have advanced
        assert _previous_tool_stats[eid] == original

    @pytest.mark.asyncio
    async def test_each_metric_gets_own_tags_dict(self, mock_db):
        """Each metric should have its own tags dict (no shared reference)."""
        await record_cycle_metrics(
            mock_db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=42,
            duration_seconds=1.0,
            success=True,
        )

        tag_ids = [id(c.args[0].tags) for c in mock_db.add.call_args_list]
        # All tag dicts should be different objects
        assert len(set(tag_ids)) == len(tag_ids)


# ============================================================================
# Response Model Tests
# ============================================================================


class TestMetricModels:
    """Tests for API response models."""

    def test_metric_summary_model(self):
        from empla.api.v1.endpoints.metrics import MetricSummary

        summary = MetricSummary(
            employee_id=uuid4(),
            hours=24,
            cycle_count=100,
            avg_duration_seconds=2.5,
            max_duration_seconds=8.3,
            success_rate=0.95,
            total_tool_calls=500,
            tool_failure_rate=0.02,
            avg_tool_latency_ms=120.5,
        )
        assert summary.cycle_count == 100

    def test_metric_point_model(self):
        from datetime import UTC, datetime

        from empla.api.v1.endpoints.metrics import MetricPoint

        point = MetricPoint(
            metric_name="cycle.duration_seconds",
            value=2.5,
            timestamp=datetime.now(UTC),
            tags={"cycle": 1},
        )
        assert point.value == 2.5
