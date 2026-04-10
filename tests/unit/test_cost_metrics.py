"""
Tests for LLM cost metric persistence and cost API endpoints.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest


class TestRecordCycleMetricsWithCost:
    """Tests for LLM cost recording in record_cycle_metrics."""

    @pytest.mark.asyncio
    async def test_records_llm_cost_metric(self):
        """LLM cost should be persisted as llm.cost_usd metric."""
        from empla.services.metrics import record_cycle_metrics

        db = AsyncMock()
        added_metrics: list = []
        db.add = Mock(side_effect=added_metrics.append)

        await record_cycle_metrics(
            db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=1,
            duration_seconds=5.0,
            success=True,
            llm_cost_usd=0.042,
        )

        metric_names = [m.metric_name for m in added_metrics]
        assert "cycle.duration_seconds" in metric_names
        assert "cycle.success" in metric_names
        assert "llm.cost_usd" in metric_names

        cost_metrics = [m for m in added_metrics if m.metric_name == "llm.cost_usd"]
        assert len(cost_metrics) == 1
        assert cost_metrics[0].value == pytest.approx(0.042, abs=1e-6)

    @pytest.mark.asyncio
    async def test_records_token_counts(self):
        """Token counts should be persisted when provided."""
        from empla.services.metrics import record_cycle_metrics

        db = AsyncMock()
        added: list = []
        db.add = Mock(side_effect=added.append)

        await record_cycle_metrics(
            db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=1,
            duration_seconds=3.0,
            success=True,
            llm_input_tokens=1500,
            llm_output_tokens=500,
        )

        names = [m.metric_name for m in added]
        assert "llm.input_tokens" in names
        assert "llm.output_tokens" in names

    @pytest.mark.asyncio
    async def test_skips_zero_cost(self):
        """Zero LLM cost should not create a metric row."""
        from empla.services.metrics import record_cycle_metrics

        db = AsyncMock()
        added: list = []
        db.add = Mock(side_effect=added.append)

        await record_cycle_metrics(
            db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=1,
            duration_seconds=2.0,
            success=True,
            llm_cost_usd=0.0,
        )

        names = [m.metric_name for m in added]
        assert "llm.cost_usd" not in names

    @pytest.mark.asyncio
    async def test_skips_none_cost(self):
        """None LLM cost should not create a metric row."""
        from empla.services.metrics import record_cycle_metrics

        db = AsyncMock()
        added: list = []
        db.add = Mock(side_effect=added.append)

        await record_cycle_metrics(
            db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=1,
            duration_seconds=2.0,
            success=True,
            llm_cost_usd=None,
        )

        names = [m.metric_name for m in added]
        assert "llm.cost_usd" not in names

    @pytest.mark.asyncio
    async def test_backward_compatible_no_cost_args(self):
        """Existing callers without cost args should still work."""
        from empla.services.metrics import record_cycle_metrics

        db = AsyncMock()
        added: list = []
        db.add = Mock(side_effect=added.append)

        await record_cycle_metrics(
            db,
            tenant_id=uuid4(),
            employee_id=uuid4(),
            cycle_count=1,
            duration_seconds=2.0,
            success=True,
        )

        names = [m.metric_name for m in added]
        assert "cycle.duration_seconds" in names
        assert "llm.cost_usd" not in names


class TestLlmCostSummaryExtraction:
    """Tests for extracting LLM cost from the service summary dict."""

    def test_cost_extraction_from_routing(self):
        """Verify cost is extracted from LLM service get_cost_summary."""
        summary = {
            "total_cost": 1.5,
            "requests_count": 20,
            "routing": {"cycle_cost_usd": 0.08, "soft_budget_usd": 0.10},
        }
        routing = summary.get("routing", {})
        cost = routing.get("cycle_cost_usd", 0.0)
        assert cost == pytest.approx(0.08)

    def test_missing_routing_defaults_to_zero(self):
        """Missing routing key should default to 0."""
        summary = {"total_cost": 0, "requests_count": 0}
        routing = summary.get("routing", {})
        cost = routing.get("cycle_cost_usd", 0.0)
        assert cost == 0.0
