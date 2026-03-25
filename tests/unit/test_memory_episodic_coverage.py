"""
Unit tests for EpisodicMemorySystem covering untested methods.

Tests record, recall, reinforcement, decay, and archival operations.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from empla.core.memory.episodic import EpisodicMemorySystem
from empla.models.memory import EpisodicMemory

# ============================================================================
# Fixtures
# ============================================================================


def _make_episodic_memory(**overrides):
    """Create a mock EpisodicMemory with sensible defaults."""
    defaults = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "employee_id": uuid4(),
        "episode_type": "interaction",
        "description": "Test episode",
        "content": {"key": "value"},
        "participants": ["user@example.com"],
        "location": "email",
        "embedding": None,
        "importance": 0.5,
        "recall_count": 0,
        "last_recalled_at": None,
        "occurred_at": datetime.now(UTC),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "deleted_at": None,
    }
    defaults.update(overrides)
    mem = MagicMock(spec=EpisodicMemory)
    for k, v in defaults.items():
        setattr(mem, k, v)
    return mem


@pytest.fixture
def session():
    """Mock async session."""
    s = AsyncMock()
    s.add = MagicMock()
    s.flush = AsyncMock()
    return s


@pytest.fixture
def ids():
    return {"employee_id": uuid4(), "tenant_id": uuid4()}


@pytest.fixture
def episodic(session, ids):
    return EpisodicMemorySystem(session, ids["employee_id"], ids["tenant_id"])


# ============================================================================
# record_episode
# ============================================================================


@pytest.mark.asyncio
async def test_record_episode_basic(episodic, session, ids):
    """record_episode creates and flushes an EpisodicMemory."""
    result = await episodic.record_episode(
        episode_type="interaction",
        description="Discussed pricing",
        content={"email": "hello"},
        participants=["ceo@acme.com"],
        location="email",
        importance=0.8,
    )

    assert isinstance(result, EpisodicMemory)
    assert result.employee_id == ids["employee_id"]
    assert result.tenant_id == ids["tenant_id"]
    assert result.episode_type == "interaction"
    assert result.description == "Discussed pricing"
    assert result.importance == 0.8
    assert result.participants == ["ceo@acme.com"]
    assert result.location == "email"
    session.add.assert_called_once_with(result)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_episode_defaults(episodic, session):
    """record_episode uses defaults for optional parameters."""
    result = await episodic.record_episode(
        episode_type="observation",
        description="Something happened",
        content={"data": 1},
    )

    assert result.participants == []
    assert result.location is None
    assert result.embedding is None
    assert result.importance == 0.5


@pytest.mark.asyncio
async def test_record_episode_with_embedding(episodic):
    """record_episode stores pre-computed embedding."""
    emb = [0.1] * 10
    result = await episodic.record_episode(
        episode_type="event",
        description="Meeting",
        content={},
        embedding=emb,
    )
    assert result.embedding == emb


# ============================================================================
# recall_similar
# ============================================================================


@pytest.mark.asyncio
async def test_recall_similar_returns_memories(episodic, session):
    """recall_similar returns memories and updates recall counts."""
    mem1 = _make_episodic_memory(recall_count=0)
    mem2 = _make_episodic_memory(recall_count=2)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mem1, mem2]
    session.execute.return_value = mock_result

    results = await episodic.recall_similar(
        query_embedding=[0.1] * 10,
        limit=5,
        similarity_threshold=0.7,
    )

    assert len(results) == 2
    assert mem1.recall_count == 1
    assert mem2.recall_count == 3
    assert mem1.last_recalled_at is not None
    assert mem2.last_recalled_at is not None
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_recall_similar_empty(episodic, session):
    """recall_similar returns empty list when no matches."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await episodic.recall_similar(query_embedding=[0.1] * 10)
    assert results == []


# ============================================================================
# recall_recent
# ============================================================================


@pytest.mark.asyncio
async def test_recall_recent_no_type_filter(episodic, session):
    """recall_recent returns recent memories without type filter."""
    mem = _make_episodic_memory()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mem]
    session.execute.return_value = mock_result

    results = await episodic.recall_recent(days=7, limit=50)
    assert len(results) == 1
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_recall_recent_with_type_filter(episodic, session):
    """recall_recent applies episode_type filter when provided."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await episodic.recall_recent(days=30, episode_type="feedback")
    assert results == []


@pytest.mark.asyncio
async def test_recall_recent_empty(episodic, session):
    """recall_recent returns empty list when no memories."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await episodic.recall_recent()
    assert results == []


# ============================================================================
# recall_with_participant
# ============================================================================


@pytest.mark.asyncio
async def test_recall_with_participant(episodic, session):
    """recall_with_participant returns matching memories."""
    mem = _make_episodic_memory(participants=["alice@co.com"])
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mem]
    session.execute.return_value = mock_result

    results = await episodic.recall_with_participant("alice@co.com", limit=10)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_recall_with_participant_empty(episodic, session):
    """recall_with_participant returns empty when no matches."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await episodic.recall_with_participant("nobody@co.com")
    assert results == []


# ============================================================================
# recall_by_type
# ============================================================================


@pytest.mark.asyncio
async def test_recall_by_type(episodic, session):
    """recall_by_type returns memories of specified type."""
    mem = _make_episodic_memory(episode_type="event")
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mem]
    session.execute.return_value = mock_result

    results = await episodic.recall_by_type("event", limit=20)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_recall_by_type_empty(episodic, session):
    """recall_by_type returns empty for nonexistent type."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await episodic.recall_by_type("nonexistent")
    assert results == []


# ============================================================================
# get_memory
# ============================================================================


@pytest.mark.asyncio
async def test_get_memory_found(episodic, session):
    """get_memory returns memory when found."""
    mem_id = uuid4()
    mem = _make_episodic_memory(id=mem_id)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mem
    session.execute.return_value = mock_result

    result = await episodic.get_memory(mem_id)
    assert result is mem


@pytest.mark.asyncio
async def test_get_memory_not_found(episodic, session):
    """get_memory returns None when not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await episodic.get_memory(uuid4())
    assert result is None


# ============================================================================
# update_importance
# ============================================================================


@pytest.mark.asyncio
async def test_update_importance_found(episodic, session):
    """update_importance updates and clamps importance."""
    mem = _make_episodic_memory(importance=0.5)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mem
    session.execute.return_value = mock_result

    result = await episodic.update_importance(mem.id, 0.9)
    assert result is mem
    assert mem.importance == 0.9


@pytest.mark.asyncio
async def test_update_importance_clamps_high(episodic, session):
    """update_importance clamps to 1.0."""
    mem = _make_episodic_memory(importance=0.5)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mem
    session.execute.return_value = mock_result

    await episodic.update_importance(mem.id, 1.5)
    assert mem.importance == 1.0


@pytest.mark.asyncio
async def test_update_importance_clamps_low(episodic, session):
    """update_importance clamps to 0.0."""
    mem = _make_episodic_memory(importance=0.5)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mem
    session.execute.return_value = mock_result

    await episodic.update_importance(mem.id, -0.5)
    assert mem.importance == 0.0


@pytest.mark.asyncio
async def test_update_importance_not_found(episodic, session):
    """update_importance returns None when memory not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await episodic.update_importance(uuid4(), 0.9)
    assert result is None


# ============================================================================
# consolidate_memories
# ============================================================================


@pytest.mark.asyncio
async def test_consolidate_memories(episodic, session):
    """consolidate_memories processes recent memories."""
    mem1 = _make_episodic_memory()
    mem2 = _make_episodic_memory()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mem1, mem2]
    session.execute.return_value = mock_result

    count = await episodic.consolidate_memories(days_back=30)
    # Current implementation is a placeholder that returns 0
    assert count == 0


@pytest.mark.asyncio
async def test_consolidate_memories_empty(episodic, session):
    """consolidate_memories handles empty results."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    count = await episodic.consolidate_memories()
    assert count == 0


# ============================================================================
# reinforce_frequently_recalled
# ============================================================================


@pytest.mark.asyncio
async def test_reinforce_frequently_recalled(episodic, session):
    """reinforce boosts importance of frequently recalled memories."""
    mem1 = _make_episodic_memory(importance=0.5, recall_count=10)
    mem2 = _make_episodic_memory(importance=0.9, recall_count=8)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mem1, mem2]
    session.execute.return_value = mock_result

    count = await episodic.reinforce_frequently_recalled(min_recall_count=5, importance_boost=1.1)

    assert count == 2
    assert mem1.importance == pytest.approx(0.55)
    assert mem2.importance == pytest.approx(0.99)
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_reinforce_caps_at_one(episodic, session):
    """reinforce caps importance at 1.0."""
    mem = _make_episodic_memory(importance=0.95, recall_count=10)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mem]
    session.execute.return_value = mock_result

    await episodic.reinforce_frequently_recalled(importance_boost=1.2)
    assert mem.importance == 1.0


@pytest.mark.asyncio
async def test_reinforce_no_qualifying_memories(episodic, session):
    """reinforce returns 0 when no memories qualify."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    count = await episodic.reinforce_frequently_recalled(min_recall_count=100)
    assert count == 0


# ============================================================================
# decay_rarely_recalled
# ============================================================================


@pytest.mark.asyncio
async def test_decay_rarely_recalled(episodic, session):
    """decay reduces importance of old unrecalled memories."""
    mem1 = _make_episodic_memory(importance=0.5, recall_count=0)
    mem2 = _make_episodic_memory(importance=0.8, recall_count=0)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mem1, mem2]
    session.execute.return_value = mock_result

    count = await episodic.decay_rarely_recalled(min_days_old=90, importance_decay=0.9)

    assert count == 2
    assert mem1.importance == pytest.approx(0.45)
    assert mem2.importance == pytest.approx(0.72)
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_decay_no_qualifying_memories(episodic, session):
    """decay returns 0 when no memories qualify."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    count = await episodic.decay_rarely_recalled()
    assert count == 0


# ============================================================================
# archive_low_importance
# ============================================================================


@pytest.mark.asyncio
async def test_archive_low_importance(episodic, session):
    """archive soft-deletes old low-importance memories."""
    mem1 = _make_episodic_memory(importance=0.1, deleted_at=None)
    mem2 = _make_episodic_memory(importance=0.2, deleted_at=None)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mem1, mem2]
    session.execute.return_value = mock_result

    count = await episodic.archive_low_importance(min_days_old=365, max_importance=0.3)

    assert count == 2
    assert mem1.deleted_at is not None
    assert mem2.deleted_at is not None
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_archive_no_qualifying_memories(episodic, session):
    """archive returns 0 when no memories qualify."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    count = await episodic.archive_low_importance()
    assert count == 0
