"""
Unit tests for WorkingMemory system covering untested methods.

Tests add, get, refresh, remove, clear, cleanup, capacity, and context summary.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from empla.core.memory.working import WorkingMemory
from empla.models.memory import WorkingMemory as WorkingMemoryModel

# ============================================================================
# Helpers
# ============================================================================


def _make_working_memory_item(**overrides):
    """Create a mock WorkingMemoryModel with sensible defaults."""
    defaults = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "employee_id": uuid4(),
        "item_type": "task",
        "content": {"task": "Test task"},
        "importance": 0.5,
        "expires_at": datetime.now(UTC).timestamp() + 3600,
        "source_id": None,
        "source_type": None,
        "access_count": 1,
        "last_accessed_at": datetime.now(UTC),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "deleted_at": None,
    }
    defaults.update(overrides)
    item = MagicMock(spec=WorkingMemoryModel)
    for k, v in defaults.items():
        setattr(item, k, v)
    return item


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
def working(session, ids):
    return WorkingMemory(session, ids["employee_id"], ids["tenant_id"])


@pytest.fixture
def working_small(session, ids):
    """Working memory with capacity 2 for testing eviction."""
    return WorkingMemory(session, ids["employee_id"], ids["tenant_id"], capacity=2)


def _setup_active_items(session, items):
    """Setup session.execute to return given items for get_active_items queries."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = items
    session.execute.return_value = mock_result


# ============================================================================
# add_item
# ============================================================================


@pytest.mark.asyncio
async def test_add_item_basic(working, session):
    """add_item creates and returns a WorkingMemoryModel."""
    # _enforce_capacity calls: get_active_items, cleanup_expired, get_active_items again
    # Each returns empty
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    result = await working.add_item(
        item_type="task",
        content={"task": "Do something"},
        importance=0.8,
        ttl_seconds=7200,
    )

    assert isinstance(result, WorkingMemoryModel)
    assert result.item_type == "task"
    assert result.importance == 0.8
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_add_item_default_ttl(working, session):
    """add_item uses DEFAULT_TTL_SECONDS when not specified."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    result = await working.add_item(
        item_type="observation",
        content={"data": 1},
    )

    assert result.expires_at is not None


@pytest.mark.asyncio
async def test_add_item_with_source(working, session):
    """add_item stores source tracking fields."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    source_id = uuid4()
    result = await working.add_item(
        item_type="context",
        content={"info": "data"},
        source_id=source_id,
        source_type="episodic",
    )

    assert result.source_id == source_id
    assert result.source_type == "episodic"


# ============================================================================
# get_active_items
# ============================================================================


@pytest.mark.asyncio
async def test_get_active_items(working, session):
    """get_active_items returns items and updates access tracking."""
    item1 = _make_working_memory_item(access_count=1)
    item2 = _make_working_memory_item(access_count=3)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [item1, item2]
    session.execute.return_value = mock_result

    results = await working.get_active_items()
    assert len(results) == 2
    assert item1.access_count == 2
    assert item2.access_count == 4
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_get_active_items_with_type(working, session):
    """get_active_items filters by item_type."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await working.get_active_items(item_type="goal")
    assert results == []


@pytest.mark.asyncio
async def test_get_active_items_empty(working, session):
    """get_active_items returns empty when no items."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await working.get_active_items()
    assert results == []


# ============================================================================
# get_item
# ============================================================================


@pytest.mark.asyncio
async def test_get_item_found(working, session):
    """get_item returns item and updates access tracking."""
    item = _make_working_memory_item(access_count=2)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    session.execute.return_value = mock_result

    result = await working.get_item(item.id)
    assert result is item
    assert item.access_count == 3
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_get_item_not_found(working, session):
    """get_item returns None when not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await working.get_item(uuid4())
    assert result is None


# ============================================================================
# refresh_item
# ============================================================================


@pytest.mark.asyncio
async def test_refresh_item(working, session):
    """refresh_item extends TTL and boosts importance."""
    item = _make_working_memory_item(importance=0.5, access_count=1)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    session.execute.return_value = mock_result

    result = await working.refresh_item(item.id, ttl_seconds=7200, importance_boost=0.2)

    assert result is item
    assert item.importance == pytest.approx(0.7)
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_refresh_item_caps_importance(working, session):
    """refresh_item caps importance at 1.0."""
    item = _make_working_memory_item(importance=0.9, access_count=1)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    session.execute.return_value = mock_result

    await working.refresh_item(item.id, importance_boost=0.5)
    assert item.importance == 1.0


@pytest.mark.asyncio
async def test_refresh_item_default_ttl(working, session):
    """refresh_item uses default TTL when not specified."""
    item = _make_working_memory_item(access_count=1)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    session.execute.return_value = mock_result

    result = await working.refresh_item(item.id)
    assert result is item


@pytest.mark.asyncio
async def test_refresh_item_no_boost(working, session):
    """refresh_item without importance_boost doesn't change importance."""
    item = _make_working_memory_item(importance=0.5, access_count=1)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    session.execute.return_value = mock_result

    await working.refresh_item(item.id, ttl_seconds=3600)
    # importance should stay at 0.5 (access_count update from get_item happens,
    # but importance is not boosted)
    # Note: get_item updates access_count, then refresh checks importance_boost is None
    assert item.importance == 0.5


@pytest.mark.asyncio
async def test_refresh_item_not_found(working, session):
    """refresh_item returns None when item not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await working.refresh_item(uuid4())
    assert result is None


# ============================================================================
# remove_item
# ============================================================================


@pytest.mark.asyncio
async def test_remove_item_found(working, session):
    """remove_item soft-deletes and returns True."""
    item = _make_working_memory_item(access_count=1, deleted_at=None)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    session.execute.return_value = mock_result

    result = await working.remove_item(item.id)
    assert result is True
    assert item.deleted_at is not None
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_remove_item_not_found(working, session):
    """remove_item returns False when not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await working.remove_item(uuid4())
    assert result is False


# ============================================================================
# clear_by_type
# ============================================================================


@pytest.mark.asyncio
async def test_clear_by_type(working, session):
    """clear_by_type soft-deletes all items of given type."""
    item1 = _make_working_memory_item(item_type="task", access_count=1, deleted_at=None)
    item2 = _make_working_memory_item(item_type="task", access_count=1, deleted_at=None)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [item1, item2]
    session.execute.return_value = mock_result

    count = await working.clear_by_type("task")
    assert count == 2
    assert item1.deleted_at is not None
    assert item2.deleted_at is not None


@pytest.mark.asyncio
async def test_clear_by_type_empty(working, session):
    """clear_by_type returns 0 when no items of type."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    count = await working.clear_by_type("nonexistent")
    assert count == 0


# ============================================================================
# clear_all
# ============================================================================


@pytest.mark.asyncio
async def test_clear_all(working, session):
    """clear_all soft-deletes all active items."""
    item1 = _make_working_memory_item(access_count=1, deleted_at=None)
    item2 = _make_working_memory_item(access_count=1, deleted_at=None)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [item1, item2]
    session.execute.return_value = mock_result

    count = await working.clear_all()
    assert count == 2
    assert item1.deleted_at is not None
    assert item2.deleted_at is not None


@pytest.mark.asyncio
async def test_clear_all_empty(working, session):
    """clear_all returns 0 when no active items."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    count = await working.clear_all()
    assert count == 0


# ============================================================================
# cleanup_expired
# ============================================================================


@pytest.mark.asyncio
async def test_cleanup_expired(working, session):
    """cleanup_expired soft-deletes expired items."""
    expired1 = _make_working_memory_item(
        expires_at=datetime.now(UTC).timestamp() - 100, deleted_at=None
    )
    expired2 = _make_working_memory_item(
        expires_at=datetime.now(UTC).timestamp() - 200, deleted_at=None
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [expired1, expired2]
    session.execute.return_value = mock_result

    count = await working.cleanup_expired()
    assert count == 2
    assert expired1.deleted_at is not None
    assert expired2.deleted_at is not None
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_cleanup_expired_none(working, session):
    """cleanup_expired returns 0 when nothing expired."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    count = await working.cleanup_expired()
    assert count == 0


# ============================================================================
# _enforce_capacity
# ============================================================================


@pytest.mark.asyncio
async def test_enforce_capacity_under(working_small, session):
    """_enforce_capacity does nothing when under capacity."""
    # get_active_items returns 1 item (under capacity of 2)
    item = _make_working_memory_item(access_count=1)

    call_count = [0]

    def make_scalars_result(items):
        mock_r = MagicMock()
        mock_r.scalars.return_value.all.return_value = items
        return mock_r

    async def mock_execute(query):
        call_count[0] += 1
        if call_count[0] <= 1:
            return make_scalars_result([item])
        if call_count[0] == 2:
            # cleanup_expired
            return make_scalars_result([])
        # re-fetch after cleanup
        return make_scalars_result([item])

    session.execute.side_effect = mock_execute

    await working_small._enforce_capacity()
    # Should not have set deleted_at on any item
    assert item.deleted_at is None


@pytest.mark.asyncio
async def test_enforce_capacity_at_capacity_evicts(working_small, session):
    """_enforce_capacity evicts least important when at capacity."""
    item_high = _make_working_memory_item(importance=0.9, access_count=1, deleted_at=None)
    item_low = _make_working_memory_item(importance=0.1, access_count=1, deleted_at=None)

    call_count = [0]

    def make_scalars_result(items):
        mock_r = MagicMock()
        mock_r.scalars.return_value.all.return_value = items
        return mock_r

    async def mock_execute(query):
        call_count[0] += 1
        if call_count[0] == 1:
            # First get_active_items
            return make_scalars_result([item_high, item_low])
        if call_count[0] == 2:
            # cleanup_expired
            return make_scalars_result([])
        # Second get_active_items (after cleanup) - still 2 items
        return make_scalars_result([item_high, item_low])

    session.execute.side_effect = mock_execute

    await working_small._enforce_capacity()
    # Least important (last in sorted list) should be evicted
    assert item_low.deleted_at is not None


# ============================================================================
# get_context_summary
# ============================================================================


@pytest.mark.asyncio
async def test_get_context_summary(working, session):
    """get_context_summary returns structured summary."""
    item1 = _make_working_memory_item(
        item_type="task",
        content={"task": "Research"},
        importance=0.8,
        access_count=1,
        created_at=datetime.now(UTC),
    )
    item2 = _make_working_memory_item(
        item_type="goal",
        content={"goal": "Close deals"},
        importance=0.9,
        access_count=1,
        created_at=datetime.now(UTC),
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [item1, item2]
    session.execute.return_value = mock_result

    summary = await working.get_context_summary()
    assert summary["total_items"] == 2
    assert summary["capacity_used"] == "2/7"
    assert summary["at_capacity"] is False
    assert "active_tasks" in summary
    assert "active_goals" in summary


@pytest.mark.asyncio
async def test_get_context_summary_empty(working, session):
    """get_context_summary handles empty working memory."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    summary = await working.get_context_summary()
    assert summary["total_items"] == 0
    assert summary["at_capacity"] is False


@pytest.mark.asyncio
async def test_get_context_summary_at_capacity(working_small, session):
    """get_context_summary reports at_capacity correctly."""
    items = [
        _make_working_memory_item(item_type="task", access_count=1, created_at=datetime.now(UTC))
        for _ in range(2)
    ]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = items
    session.execute.return_value = mock_result

    summary = await working_small.get_context_summary()
    assert summary["at_capacity"] is True
    assert summary["capacity_used"] == "2/2"


# ============================================================================
# update_importance
# ============================================================================


@pytest.mark.asyncio
async def test_update_importance(working, session):
    """update_importance updates and clamps importance."""
    item = _make_working_memory_item(importance=0.5, access_count=1)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    session.execute.return_value = mock_result

    result = await working.update_importance(item.id, 0.9)
    assert result is item
    assert item.importance == 0.9


@pytest.mark.asyncio
async def test_update_importance_clamps_high(working, session):
    """update_importance clamps to 1.0."""
    item = _make_working_memory_item(importance=0.5, access_count=1)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    session.execute.return_value = mock_result

    await working.update_importance(item.id, 1.5)
    assert item.importance == 1.0


@pytest.mark.asyncio
async def test_update_importance_clamps_low(working, session):
    """update_importance clamps to 0.0."""
    item = _make_working_memory_item(importance=0.5, access_count=1)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    session.execute.return_value = mock_result

    await working.update_importance(item.id, -0.5)
    assert item.importance == 0.0


@pytest.mark.asyncio
async def test_update_importance_not_found(working, session):
    """update_importance returns None when not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await working.update_importance(uuid4(), 0.9)
    assert result is None


# ============================================================================
# get_most_important
# ============================================================================


@pytest.mark.asyncio
async def test_get_most_important(working, session):
    """get_most_important returns top N items."""
    items = [
        _make_working_memory_item(importance=0.9, access_count=1),
        _make_working_memory_item(importance=0.7, access_count=1),
        _make_working_memory_item(importance=0.5, access_count=1),
    ]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = items
    session.execute.return_value = mock_result

    results = await working.get_most_important(limit=2)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_get_most_important_fewer_than_limit(working, session):
    """get_most_important returns all when fewer than limit."""
    items = [_make_working_memory_item(access_count=1)]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = items
    session.execute.return_value = mock_result

    results = await working.get_most_important(limit=5)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_get_most_important_empty(working, session):
    """get_most_important returns empty when no items."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await working.get_most_important()
    assert results == []
