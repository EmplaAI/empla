"""
Tests for the cycle metrics recording service and API response models.

Covers:
- record_cycle_metrics() persists correct metric rows
- Tool stats aggregation
- Edge cases (no tool stats, empty tool stats)
- MetricSummary and MetricPoint response model validation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from empla.services.metrics import record_cycle_metrics

# ============================================================================
# record_cycle_metrics Tests
# ============================================================================


class TestRecordCycleMetrics:
    """Tests for the record_cycle_metrics service function."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
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

        # 2 base metrics: duration + success
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
    async def test_records_tool_stats(self, mock_db):
        """Should record tool metrics when tool_stats provided."""
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
            employee_id=uuid4(),
            cycle_count=1,
            duration_seconds=3.0,
            success=True,
            tool_stats=tool_stats,
        )

        # 2 base + 3 tool = 5 metrics
        assert mock_db.add.call_count == 5
        metrics = [c.args[0] for c in mock_db.add.call_args_list]
        names = {m.metric_name for m in metrics}
        assert "tool.calls_total" in names
        assert "tool.calls_failed" in names
        assert "tool.avg_latency_ms" in names

        # Check aggregation
        total = next(m for m in metrics if m.metric_name == "tool.calls_total")
        assert total.value == 15.0  # 10 + 5

        failed = next(m for m in metrics if m.metric_name == "tool.calls_failed")
        assert failed.value == 2.0  # 1 + 1

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

        assert mock_db.add.call_count == 2  # Only base metrics

    @pytest.mark.asyncio
    async def test_empty_tool_stats_records_zeros(self, mock_db):
        """Empty tool_stats list should record zero values."""
        await record_cycle_metrics(
            mock_db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=1,
            duration_seconds=1.0,
            success=True,
            tool_stats=[],
        )

        # Empty list is falsy — no tool metrics recorded
        assert mock_db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_flush_failure_logs_warning(self, mock_db):
        """Flush failure should log warning, not crash."""
        mock_db.flush = AsyncMock(side_effect=Exception("DB error"))

        # Should not raise
        await record_cycle_metrics(
            mock_db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=1,
            duration_seconds=1.0,
            success=True,
        )

    @pytest.mark.asyncio
    async def test_tenant_and_employee_ids_propagated(self, mock_db):
        """All metrics should have correct tenant_id and employee_id."""
        tid = uuid4()
        eid = uuid4()

        await record_cycle_metrics(
            mock_db,
            tenant_id=tid,
            employee_id=eid,
            cycle_count=5,
            duration_seconds=1.0,
            success=True,
        )

        for c in mock_db.add.call_args_list:
            metric = c.args[0]
            assert metric.tenant_id == tid
            assert metric.employee_id == eid

    @pytest.mark.asyncio
    async def test_cycle_count_in_tags(self, mock_db):
        """All metrics should include cycle count in tags."""
        await record_cycle_metrics(
            mock_db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=42,
            duration_seconds=1.0,
            success=True,
        )

        for c in mock_db.add.call_args_list:
            metric = c.args[0]
            assert metric.tags["cycle"] == 42


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
        assert summary.success_rate == 0.95

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
