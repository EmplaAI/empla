"""
Unit tests for ProceduralMemorySystem covering untested methods.

Tests record, find, search, reinforce, archive, and condition matching.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from empla.core.memory.procedural import ProceduralMemorySystem
from empla.models.memory import ProceduralMemory

# ============================================================================
# Helpers
# ============================================================================


def _make_procedural_memory(**overrides):
    """Create a mock ProceduralMemory with sensible defaults."""
    defaults = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "employee_id": uuid4(),
        "procedure_type": "workflow",
        "name": "Test procedure",
        "description": "",
        "steps": [{"action": "do_thing"}],
        "trigger_conditions": {},
        "context": {},
        "embedding": None,
        "execution_count": 1,
        "success_count": 1,
        "success_rate": 1.0,
        "avg_execution_time": None,
        "last_executed_at": datetime.now(UTC),
        "learned_from": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "deleted_at": None,
    }
    defaults.update(overrides)
    mem = MagicMock(spec=ProceduralMemory)
    for k, v in defaults.items():
        setattr(mem, k, v)
    return mem


@pytest.fixture
def session():
    s = AsyncMock()
    s.add = MagicMock()
    s.flush = AsyncMock()
    return s


@pytest.fixture
def ids():
    return {"employee_id": uuid4(), "tenant_id": uuid4()}


@pytest.fixture
def procedural(session, ids):
    return ProceduralMemorySystem(session, ids["employee_id"], ids["tenant_id"])


# ============================================================================
# record_procedure — new
# ============================================================================


@pytest.mark.asyncio
async def test_record_procedure_new(procedural, session):
    """record_procedure creates new procedure when none exists."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await procedural.record_procedure(
        procedure_type="workflow",
        name="Research competitor",
        steps=[{"action": "search"}],
        trigger_conditions={"task_type": "research"},
        outcome="completed",
        success=True,
        execution_time=120.0,
    )

    assert isinstance(result, ProceduralMemory)
    assert result.execution_count == 1
    assert result.success_count == 1
    assert result.success_rate == 1.0
    assert result.avg_execution_time == 120.0
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_record_procedure_new_failure(procedural, session):
    """record_procedure creates new procedure with failure."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await procedural.record_procedure(
        procedure_type="tactic",
        name="Cold call",
        steps=[{"action": "call"}],
        success=False,
    )

    assert result.success_count == 0
    assert result.success_rate == 0.0


@pytest.mark.asyncio
async def test_record_procedure_new_no_outcome(procedural, session):
    """record_procedure creates new procedure without outcome."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await procedural.record_procedure(
        procedure_type="workflow",
        name="Simple task",
        steps=[{"action": "do"}],
    )

    assert isinstance(result, ProceduralMemory)


@pytest.mark.asyncio
async def test_record_procedure_new_with_context(procedural, session):
    """record_procedure creates new procedure with context."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await procedural.record_procedure(
        procedure_type="workflow",
        name="Custom task",
        steps=[{"action": "do"}],
        context={"source": "learning"},
        embedding=[0.1, 0.2],
    )

    assert isinstance(result, ProceduralMemory)


# ============================================================================
# record_procedure — update existing
# ============================================================================


@pytest.mark.asyncio
async def test_record_procedure_updates_existing(procedural, session):
    """record_procedure updates existing on match."""
    existing = _make_procedural_memory(
        execution_count=5,
        success_count=4,
        success_rate=0.8,
        avg_execution_time=100.0,
        context={},
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    session.execute.return_value = mock_result

    result = await procedural.record_procedure(
        procedure_type="workflow",
        name="Test procedure",
        steps=[{"action": "updated"}],
        outcome="success",
        success=True,
        execution_time=80.0,
    )

    assert result is existing
    assert existing.execution_count == 6
    assert existing.success_count == 5
    assert existing.success_rate == pytest.approx(5 / 6)
    # Incremental average: (100*5 + 80) / 6 = 580/6 ~ 96.67
    assert existing.avg_execution_time == pytest.approx(580 / 6)
    assert existing.steps == [{"action": "updated"}]


@pytest.mark.asyncio
async def test_record_procedure_update_failure(procedural, session):
    """record_procedure updates existing with failure."""
    existing = _make_procedural_memory(
        execution_count=3,
        success_count=3,
        success_rate=1.0,
        context={},
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    session.execute.return_value = mock_result

    await procedural.record_procedure(
        procedure_type="workflow",
        name="Test",
        steps=[],
        success=False,
    )

    assert existing.execution_count == 4
    assert existing.success_count == 3
    assert existing.success_rate == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_record_procedure_update_first_execution_time(procedural, session):
    """record_procedure sets avg_execution_time when previously None."""
    existing = _make_procedural_memory(
        execution_count=1,
        success_count=1,
        avg_execution_time=None,
        context={},
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    session.execute.return_value = mock_result

    await procedural.record_procedure(
        procedure_type="workflow",
        name="Test",
        steps=[],
        execution_time=50.0,
    )

    assert existing.avg_execution_time == 50.0


@pytest.mark.asyncio
async def test_record_procedure_update_outcome_truncation(procedural, session):
    """record_procedure keeps only last 10 outcomes."""
    existing_outcomes = [
        {"outcome": f"o{i}", "success": True, "timestamp": "t", "execution_time": 1.0}
        for i in range(10)
    ]
    existing = _make_procedural_memory(
        execution_count=10,
        success_count=10,
        context={"outcomes": existing_outcomes},
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    session.execute.return_value = mock_result

    await procedural.record_procedure(
        procedure_type="workflow",
        name="Test",
        steps=[],
        outcome="new_outcome",
        success=True,
    )

    # Should keep last 10 (first one dropped, new one added)
    assert len(existing.context["outcomes"]) == 10
    assert existing.context["outcomes"][-1]["outcome"] == "new_outcome"


# ============================================================================
# get_procedure_by_name_and_conditions
# ============================================================================


@pytest.mark.asyncio
async def test_get_procedure_by_name_found(procedural, session):
    """get_procedure_by_name_and_conditions returns match."""
    proc = _make_procedural_memory(name="Research")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = proc
    session.execute.return_value = mock_result

    result = await procedural.get_procedure_by_name_and_conditions("Research")
    assert result is proc


@pytest.mark.asyncio
async def test_get_procedure_by_name_with_conditions(procedural, session):
    """get_procedure_by_name_and_conditions uses JSONB matching."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await procedural.get_procedure_by_name_and_conditions(
        "Research", {"task_type": "research"}
    )
    assert result is None


@pytest.mark.asyncio
async def test_get_procedure_by_name_not_found(procedural, session):
    """get_procedure_by_name_and_conditions returns None."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await procedural.get_procedure_by_name_and_conditions("Nonexistent")
    assert result is None


# ============================================================================
# _conditions_match_situation
# ============================================================================


def test_conditions_match_empty(procedural):
    """Empty conditions match any situation."""
    assert procedural._conditions_match_situation({}, {"anything": "goes"})


def test_conditions_match_exact(procedural):
    """Exact value matching works."""
    conditions = {"task_type": "research", "priority": "high"}
    situation = {"task_type": "research", "priority": "high", "extra": "ok"}
    assert procedural._conditions_match_situation(conditions, situation)


def test_conditions_no_match_missing_key(procedural):
    """Missing key in situation fails match."""
    conditions = {"task_type": "research"}
    situation = {"other_key": "value"}
    assert not procedural._conditions_match_situation(conditions, situation)


def test_conditions_no_match_wrong_value(procedural):
    """Wrong value fails match."""
    conditions = {"task_type": "research"}
    situation = {"task_type": "analysis"}
    assert not procedural._conditions_match_situation(conditions, situation)


def test_conditions_greater_than_operator(procedural):
    """Greater-than operator works."""
    conditions = {"lead_score": ">80"}
    assert procedural._conditions_match_situation(conditions, {"lead_score": 85})
    assert not procedural._conditions_match_situation(conditions, {"lead_score": 75})
    assert not procedural._conditions_match_situation(conditions, {"lead_score": 80})


def test_conditions_less_than_operator(procedural):
    """Less-than operator works."""
    conditions = {"risk": "<50"}
    assert procedural._conditions_match_situation(conditions, {"risk": 30})
    assert not procedural._conditions_match_situation(conditions, {"risk": 60})
    assert not procedural._conditions_match_situation(conditions, {"risk": 50})


def test_conditions_operator_with_non_numeric(procedural):
    """Operator with non-numeric situation value fails."""
    conditions = {"score": ">80"}
    assert not procedural._conditions_match_situation(conditions, {"score": "high"})


# ============================================================================
# find_procedures_for_situation
# ============================================================================


@pytest.mark.asyncio
async def test_find_procedures_matching(procedural, session):
    """find_procedures_for_situation returns matching procedures."""
    proc1 = _make_procedural_memory(
        trigger_conditions={"task_type": "research"},
        success_rate=0.9,
    )
    proc2 = _make_procedural_memory(
        trigger_conditions={"task_type": "other"},
        success_rate=0.8,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [proc1, proc2]
    session.execute.return_value = mock_result

    results = await procedural.find_procedures_for_situation(
        situation={"task_type": "research"},
        min_success_rate=0.5,
    )

    assert len(results) == 1
    assert results[0] is proc1


@pytest.mark.asyncio
async def test_find_procedures_with_type_filter(procedural, session):
    """find_procedures_for_situation applies type filter."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await procedural.find_procedures_for_situation(
        situation={},
        procedure_type="workflow",
    )
    assert results == []


@pytest.mark.asyncio
async def test_find_procedures_respects_limit(procedural, session):
    """find_procedures_for_situation stops at limit."""
    procs = [_make_procedural_memory(trigger_conditions={}) for _ in range(10)]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = procs
    session.execute.return_value = mock_result

    results = await procedural.find_procedures_for_situation(situation={}, limit=3)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_find_procedures_empty(procedural, session):
    """find_procedures_for_situation returns empty when no match."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await procedural.find_procedures_for_situation(situation={"x": "y"})
    assert results == []


# ============================================================================
# search_similar_procedures
# ============================================================================


@pytest.mark.asyncio
async def test_search_similar_procedures(procedural, session):
    """search_similar_procedures returns similar procedures."""
    proc = _make_procedural_memory()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [proc]
    session.execute.return_value = mock_result

    results = await procedural.search_similar_procedures(query_embedding=[0.1] * 10, limit=5)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_similar_with_type(procedural, session):
    """search_similar_procedures applies type filter."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await procedural.search_similar_procedures(
        query_embedding=[0.1], procedure_type="tactic"
    )
    assert results == []


# ============================================================================
# get_best_procedures
# ============================================================================


@pytest.mark.asyncio
async def test_get_best_procedures(procedural, session):
    """get_best_procedures returns top-performing procedures."""
    proc = _make_procedural_memory(success_rate=0.95, execution_count=10)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [proc]
    session.execute.return_value = mock_result

    results = await procedural.get_best_procedures(min_executions=5)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_get_best_procedures_with_type(procedural, session):
    """get_best_procedures applies type filter."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await procedural.get_best_procedures(procedure_type="workflow")
    assert results == []


@pytest.mark.asyncio
async def test_get_best_procedures_empty(procedural, session):
    """get_best_procedures returns empty when no procedures qualify."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await procedural.get_best_procedures(min_executions=100)
    assert results == []


# ============================================================================
# update_procedure_embedding
# ============================================================================


@pytest.mark.asyncio
async def test_update_procedure_embedding_found(procedural, session):
    """update_procedure_embedding updates embedding."""
    proc = _make_procedural_memory()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = proc
    session.execute.return_value = mock_result

    new_emb = [0.5, 0.6, 0.7]
    result = await procedural.update_procedure_embedding(proc.id, new_emb)
    assert result is proc
    assert proc.embedding == new_emb
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_update_procedure_embedding_not_found(procedural, session):
    """update_procedure_embedding returns None when not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await procedural.update_procedure_embedding(uuid4(), [0.1])
    assert result is None


# ============================================================================
# archive_poor_procedures
# ============================================================================


@pytest.mark.asyncio
async def test_archive_poor_procedures(procedural, session):
    """archive soft-deletes poorly performing procedures."""
    proc1 = _make_procedural_memory(success_rate=0.1, deleted_at=None)
    proc2 = _make_procedural_memory(success_rate=0.2, deleted_at=None)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [proc1, proc2]
    session.execute.return_value = mock_result

    count = await procedural.archive_poor_procedures(max_success_rate=0.3, min_executions=5)
    assert count == 2
    assert proc1.deleted_at is not None
    assert proc2.deleted_at is not None


@pytest.mark.asyncio
async def test_archive_poor_procedures_empty(procedural, session):
    """archive returns 0 when no procedures qualify."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    count = await procedural.archive_poor_procedures()
    assert count == 0


# ============================================================================
# reinforce_successful_procedures
# ============================================================================


@pytest.mark.asyncio
async def test_reinforce_successful_procedures(procedural, session):
    """reinforce marks successful procedures as proven."""
    proc = _make_procedural_memory(success_rate=0.9, execution_count=10, context={})

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [proc]
    session.execute.return_value = mock_result

    count = await procedural.reinforce_successful_procedures(min_success_rate=0.8, min_executions=5)
    assert count == 1
    assert proc.context["proven"] is True
    assert "reinforced_at" in proc.context
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_reinforce_preserves_existing_context(procedural, session):
    """reinforce preserves existing context keys."""
    proc = _make_procedural_memory(
        success_rate=0.9, execution_count=10, context={"existing_key": "value"}
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [proc]
    session.execute.return_value = mock_result

    await procedural.reinforce_successful_procedures()
    assert proc.context["existing_key"] == "value"
    assert proc.context["proven"] is True


@pytest.mark.asyncio
async def test_reinforce_empty(procedural, session):
    """reinforce returns 0 when no procedures qualify."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    count = await procedural.reinforce_successful_procedures()
    assert count == 0


# ============================================================================
# get_procedure
# ============================================================================


@pytest.mark.asyncio
async def test_get_procedure_found(procedural, session):
    """get_procedure returns procedure when found."""
    proc = _make_procedural_memory()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = proc
    session.execute.return_value = mock_result

    result = await procedural.get_procedure(proc.id)
    assert result is proc


@pytest.mark.asyncio
async def test_get_procedure_not_found(procedural, session):
    """get_procedure returns None when not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await procedural.get_procedure(uuid4())
    assert result is None


# ============================================================================
# get_procedures_by_type
# ============================================================================


@pytest.mark.asyncio
async def test_get_procedures_by_type(procedural, session):
    """get_procedures_by_type returns procedures of given type."""
    proc = _make_procedural_memory(procedure_type="tactic")
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [proc]
    session.execute.return_value = mock_result

    results = await procedural.get_procedures_by_type("tactic")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_get_procedures_by_type_empty(procedural, session):
    """get_procedures_by_type returns empty for nonexistent type."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await procedural.get_procedures_by_type("nonexistent")
    assert results == []
