"""
Unit tests for SemanticMemorySystem covering untested methods.

Tests store, query, search, graph traversal, reinforcement, decay, and archival.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from empla.core.memory.semantic import SemanticMemorySystem
from empla.models.memory import SemanticMemory

# ============================================================================
# Helpers
# ============================================================================


def _make_semantic_memory(**overrides):
    """Create a mock SemanticMemory with sensible defaults."""
    defaults = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "employee_id": uuid4(),
        "fact_type": "entity",
        "subject": "Acme Corp",
        "predicate": "industry",
        "object": "manufacturing",
        "confidence": 0.9,
        "source": None,
        "verified": False,
        "source_id": None,
        "source_type": None,
        "access_count": 0,
        "last_accessed_at": None,
        "context": {},
        "embedding": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "deleted_at": None,
    }
    defaults.update(overrides)
    mem = MagicMock(spec=SemanticMemory)
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
def semantic(session, ids):
    return SemanticMemorySystem(session, ids["employee_id"], ids["tenant_id"])


# ============================================================================
# store_fact — new fact
# ============================================================================


@pytest.mark.asyncio
async def test_store_fact_new(semantic, session):
    """store_fact creates a new fact when none exists."""
    # get_fact returns None (no existing)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await semantic.store_fact(
        subject="Acme Corp",
        predicate="industry",
        fact_object="manufacturing",
        confidence=0.95,
    )

    assert isinstance(result, SemanticMemory)
    assert result.subject == "Acme Corp"
    assert result.predicate == "industry"
    assert result.object == "manufacturing"
    session.add.assert_called_once()
    assert session.flush.await_count >= 1


@pytest.mark.asyncio
async def test_store_fact_new_with_dict_object(semantic, session):
    """store_fact serializes dict objects to JSON."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await semantic.store_fact(
        subject="John",
        predicate="preferences",
        fact_object={"channel": "email", "time": "morning"},
    )

    assert isinstance(result, SemanticMemory)
    # dict gets serialized to JSON string
    assert '"channel"' in result.object


@pytest.mark.asyncio
async def test_store_fact_new_with_all_options(semantic, session):
    """store_fact handles all optional params for new fact."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    source_id = uuid4()
    result = await semantic.store_fact(
        subject="X",
        predicate="Y",
        fact_object="Z",
        confidence=0.7,
        fact_type="relationship",
        source="observation",
        verified=True,
        source_type="episodic",
        source_id=source_id,
        context={"note": "test"},
        embedding=[0.1, 0.2],
    )

    assert isinstance(result, SemanticMemory)


# ============================================================================
# store_fact — update existing
# ============================================================================


@pytest.mark.asyncio
async def test_store_fact_updates_existing(semantic, session):
    """store_fact updates existing fact when subject+predicate match."""
    existing = _make_semantic_memory(
        subject="Acme Corp",
        predicate="industry",
        object="tech",
        confidence=0.5,
        access_count=3,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    session.execute.return_value = mock_result

    result = await semantic.store_fact(
        subject="Acme Corp",
        predicate="industry",
        fact_object="manufacturing",
        confidence=0.95,
        source_type="extraction",
        source_id=uuid4(),
        context={"updated": True},
        embedding=[0.5, 0.6],
    )

    assert result is existing
    assert existing.object == "manufacturing"
    assert existing.confidence == 0.95
    # get_fact increments +1 (3->4), then store_fact increments +1 (4->5)
    assert existing.access_count == 5
    assert existing.source_type == "extraction"
    assert existing.context == {"updated": True}
    assert existing.embedding == [0.5, 0.6]


@pytest.mark.asyncio
async def test_store_fact_update_without_optional_fields(semantic, session):
    """store_fact update skips None optional fields."""
    existing = _make_semantic_memory(
        source_type="old_source",
        source_id=uuid4(),
        context={"old": True},
        embedding=[0.1],
        access_count=1,
    )
    original_source_type = existing.source_type
    original_source_id = existing.source_id
    original_context = existing.context
    original_embedding = existing.embedding

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    session.execute.return_value = mock_result

    await semantic.store_fact(
        subject="X",
        predicate="Y",
        fact_object="Z",
        confidence=0.8,
    )

    # Optional fields not provided should remain unchanged
    assert existing.source_type == original_source_type
    assert existing.source_id == original_source_id
    assert existing.context == original_context
    assert existing.embedding == original_embedding


# ============================================================================
# get_fact
# ============================================================================


@pytest.mark.asyncio
async def test_get_fact_found(semantic, session):
    """get_fact returns fact and updates access tracking."""
    fact = _make_semantic_memory(access_count=2)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fact
    session.execute.return_value = mock_result

    result = await semantic.get_fact("Acme Corp", "industry")
    assert result is fact
    assert fact.access_count == 3
    assert fact.last_accessed_at is not None
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_get_fact_not_found(semantic, session):
    """get_fact returns None when no match."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await semantic.get_fact("Unknown", "nothing")
    assert result is None


# ============================================================================
# query_facts
# ============================================================================


@pytest.mark.asyncio
async def test_query_facts_subject_only(semantic, session):
    """query_facts filters by subject."""
    fact1 = _make_semantic_memory(access_count=0)
    fact2 = _make_semantic_memory(access_count=1)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fact1, fact2]
    session.execute.return_value = mock_result

    results = await semantic.query_facts(subject="Acme Corp")
    assert len(results) == 2
    assert fact1.access_count == 1
    assert fact2.access_count == 2
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_query_facts_predicate_only(semantic, session):
    """query_facts filters by predicate."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await semantic.query_facts(predicate="industry")
    assert results == []


@pytest.mark.asyncio
async def test_query_facts_both_filters(semantic, session):
    """query_facts filters by both subject and predicate."""
    fact = _make_semantic_memory(access_count=0)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fact]
    session.execute.return_value = mock_result

    results = await semantic.query_facts(subject="Acme", predicate="industry")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_query_facts_no_filters(semantic, session):
    """query_facts returns all facts when no filters."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await semantic.query_facts()
    assert results == []


# ============================================================================
# search_similar_facts
# ============================================================================


@pytest.mark.asyncio
async def test_search_similar_facts(semantic, session):
    """search_similar_facts returns and tracks access."""
    fact = _make_semantic_memory(access_count=0)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fact]
    session.execute.return_value = mock_result

    results = await semantic.search_similar_facts(
        query_embedding=[0.1] * 10,
        limit=5,
        similarity_threshold=0.7,
    )

    assert len(results) == 1
    assert fact.access_count == 1
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_search_similar_facts_with_filters(semantic, session):
    """search_similar_facts applies subject and predicate filters."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await semantic.search_similar_facts(
        query_embedding=[0.1] * 10,
        subject="Acme",
        predicate="industry",
    )
    assert results == []


@pytest.mark.asyncio
async def test_search_similar_facts_empty(semantic, session):
    """search_similar_facts returns empty for no matches."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    results = await semantic.search_similar_facts(query_embedding=[0.0])
    assert results == []


# ============================================================================
# get_related_facts (graph traversal)
# ============================================================================


@pytest.mark.asyncio
async def test_get_related_facts_single_level(semantic, session):
    """get_related_facts traverses depth 0 only when max_depth=0."""
    fact = _make_semantic_memory(object="tech", access_count=0)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fact]
    session.execute.return_value = mock_result

    results = await semantic.get_related_facts("Acme Corp", max_depth=0)
    assert "0" in results
    assert len(results["0"]) == 1


@pytest.mark.asyncio
async def test_get_related_facts_multi_level(semantic, session):
    """get_related_facts traverses multiple depth levels."""
    # Depth 0: Acme -> tech
    fact0 = _make_semantic_memory(object="tech", access_count=0)
    # Depth 1: tech -> software
    fact1 = _make_semantic_memory(subject="tech", object="software", access_count=0)

    call_count = [0]

    def make_result(facts):
        mock_r = MagicMock()
        mock_r.scalars.return_value.all.return_value = facts
        return mock_r

    async def mock_execute(query):
        call_count[0] += 1
        if call_count[0] <= 2:
            # First two calls: depth 0 query_facts (get_fact + query)
            # Actually query_facts calls session.execute once
            return make_result([fact0])
        return make_result([fact1])

    session.execute.side_effect = mock_execute

    results = await semantic.get_related_facts("Acme Corp", max_depth=1)
    assert "0" in results


@pytest.mark.asyncio
async def test_get_related_facts_stops_when_no_new_entities(semantic, session):
    """get_related_facts stops early when no new entities found."""
    # Return facts with empty object (no traversal targets)
    fact = _make_semantic_memory(object="", access_count=0)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fact]
    session.execute.return_value = mock_result

    results = await semantic.get_related_facts("Acme Corp", max_depth=3)
    # Should stop after depth 0 since empty object won't be traversed
    assert "0" in results


# ============================================================================
# update_fact_confidence
# ============================================================================


@pytest.mark.asyncio
async def test_update_fact_confidence(semantic, session):
    """update_fact_confidence updates and clamps confidence."""
    fact = _make_semantic_memory(confidence=0.5, access_count=0)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fact
    session.execute.return_value = mock_result

    result = await semantic.update_fact_confidence("Acme", "industry", 0.9)
    assert result is fact
    assert fact.confidence == 0.9


@pytest.mark.asyncio
async def test_update_fact_confidence_clamps_high(semantic, session):
    """update_fact_confidence clamps to 1.0."""
    fact = _make_semantic_memory(confidence=0.5, access_count=0)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fact
    session.execute.return_value = mock_result

    await semantic.update_fact_confidence("X", "Y", 1.5)
    assert fact.confidence == 1.0


@pytest.mark.asyncio
async def test_update_fact_confidence_clamps_low(semantic, session):
    """update_fact_confidence clamps to 0.0."""
    fact = _make_semantic_memory(confidence=0.5, access_count=0)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fact
    session.execute.return_value = mock_result

    await semantic.update_fact_confidence("X", "Y", -0.5)
    assert fact.confidence == 0.0


@pytest.mark.asyncio
async def test_update_fact_confidence_not_found(semantic, session):
    """update_fact_confidence returns None when fact not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    result = await semantic.update_fact_confidence("X", "Y", 0.5)
    assert result is None


# ============================================================================
# decay_old_facts
# ============================================================================


@pytest.mark.asyncio
async def test_decay_old_facts(semantic, session):
    """decay reduces confidence of old rarely-accessed facts."""
    fact1 = _make_semantic_memory(confidence=0.8)
    fact2 = _make_semantic_memory(confidence=0.6)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fact1, fact2]
    session.execute.return_value = mock_result

    count = await semantic.decay_old_facts(min_days_old=180, confidence_decay=0.9)
    assert count == 2
    assert fact1.confidence == pytest.approx(0.72)
    assert fact2.confidence == pytest.approx(0.54)


@pytest.mark.asyncio
async def test_decay_old_facts_empty(semantic, session):
    """decay returns 0 when no facts qualify."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    count = await semantic.decay_old_facts()
    assert count == 0


# ============================================================================
# archive_low_confidence_facts
# ============================================================================


@pytest.mark.asyncio
async def test_archive_low_confidence_facts(semantic, session):
    """archive soft-deletes low-confidence old facts."""
    fact1 = _make_semantic_memory(confidence=0.1, deleted_at=None)
    fact2 = _make_semantic_memory(confidence=0.2, deleted_at=None)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fact1, fact2]
    session.execute.return_value = mock_result

    count = await semantic.archive_low_confidence_facts(max_confidence=0.3, min_days_old=90)
    assert count == 2
    assert fact1.deleted_at is not None
    assert fact2.deleted_at is not None


@pytest.mark.asyncio
async def test_archive_low_confidence_empty(semantic, session):
    """archive returns 0 when no facts qualify."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    count = await semantic.archive_low_confidence_facts()
    assert count == 0


# ============================================================================
# reinforce_frequently_accessed
# ============================================================================


@pytest.mark.asyncio
async def test_reinforce_frequently_accessed(semantic, session):
    """reinforce boosts confidence of frequently accessed facts."""
    fact1 = _make_semantic_memory(confidence=0.5, access_count=15)
    fact2 = _make_semantic_memory(confidence=0.9, access_count=12)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fact1, fact2]
    session.execute.return_value = mock_result

    count = await semantic.reinforce_frequently_accessed(min_access_count=10, confidence_boost=1.1)
    assert count == 2
    assert fact1.confidence == pytest.approx(0.55)
    assert fact2.confidence == pytest.approx(0.99)


@pytest.mark.asyncio
async def test_reinforce_caps_at_one(semantic, session):
    """reinforce caps confidence at 1.0."""
    fact = _make_semantic_memory(confidence=0.95, access_count=20)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fact]
    session.execute.return_value = mock_result

    await semantic.reinforce_frequently_accessed(confidence_boost=1.2)
    assert fact.confidence == 1.0


@pytest.mark.asyncio
async def test_reinforce_empty(semantic, session):
    """reinforce returns 0 when no facts qualify."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    count = await semantic.reinforce_frequently_accessed()
    assert count == 0


# ============================================================================
# get_entity_summary
# ============================================================================


@pytest.mark.asyncio
async def test_get_entity_summary(semantic, session):
    """get_entity_summary returns facts organized by predicate."""
    fact1 = _make_semantic_memory(predicate="industry", object="tech", access_count=0)
    fact2 = _make_semantic_memory(predicate="size", object="500", access_count=0)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fact1, fact2]
    session.execute.return_value = mock_result

    summary = await semantic.get_entity_summary("Acme Corp")
    assert summary["industry"] == "tech"
    assert summary["size"] == "500"


@pytest.mark.asyncio
async def test_get_entity_summary_empty(semantic, session):
    """get_entity_summary returns empty dict for unknown entity."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    summary = await semantic.get_entity_summary("Unknown")
    assert summary == {}
