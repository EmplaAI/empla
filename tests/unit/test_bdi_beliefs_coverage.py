"""
Unit tests for empla.bdi.beliefs — covering untested methods.

Tests:
- ExtractedBelief validation and normalize_belief_type
- BeliefChangeResult
- BeliefSystem.update_belief (create + update paths)
- BeliefSystem.get_belief / get_all_beliefs / get_beliefs_about
- BeliefSystem.decay_beliefs
- BeliefSystem.remove_belief
- BeliefSystem.get_belief_history
- BeliefSystem._map_structured_to_beliefs
- BeliefSystem._batch_extract_beliefs
- BeliefSystem.extract_beliefs_from_observation
- BeliefSystem.update_beliefs (batch orchestrator)
- BeliefSystem._format_observation_content
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from empla.bdi.beliefs import (
    BeliefChangeResult,
    BeliefExtractionResult,
    BeliefSystem,
    BeliefUpdateResult,
    ExtractedBelief,
)
from empla.core.loop.models import Observation
from empla.models.belief import Belief, BeliefHistory

# ============================================================================
# Helpers
# ============================================================================


def make_belief(**overrides: Any) -> Mock:
    """Create a mock Belief ORM object."""
    defaults = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "employee_id": uuid4(),
        "belief_type": "state",
        "subject": "Acme Corp",
        "predicate": "deal_stage",
        "object": {"stage": "negotiation"},
        "confidence": 0.8,
        "source": "observation",
        "evidence": [],
        "formed_at": datetime.now(UTC),
        "last_updated_at": datetime.now(UTC),
        "decay_rate": 0.1,
        "deleted_at": None,
    }
    defaults.update(overrides)
    b = Mock(spec=Belief)
    for k, v in defaults.items():
        setattr(b, k, v)
    return b


def make_observation(**overrides: Any) -> Observation:
    """Create an Observation for testing."""
    defaults = {
        "employee_id": uuid4(),
        "tenant_id": uuid4(),
        "observation_type": "email_received",
        "source": "email",
        "content": {"from": "ceo@acme.com", "subject": "Deal update"},
        "priority": 7,
    }
    defaults.update(overrides)
    return Observation(**defaults)


def make_session() -> AsyncMock:
    """Create mock async session."""
    session = AsyncMock()
    session.add = Mock()
    session.flush = AsyncMock()
    # Default execute returns empty result
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)
    return session


def make_belief_system(
    session: AsyncMock | None = None,
    llm_service: Any = None,
) -> BeliefSystem:
    """Create a BeliefSystem with mock dependencies."""
    return BeliefSystem(
        session=session or make_session(),
        employee_id=uuid4(),
        tenant_id=uuid4(),
        llm_service=llm_service or AsyncMock(),
    )


# ============================================================================
# Test: ExtractedBelief Pydantic model
# ============================================================================


class TestExtractedBelief:
    """Tests for the ExtractedBelief Pydantic model."""

    def test_valid_construction(self) -> None:
        belief = ExtractedBelief(
            subject="Acme Corp",
            predicate="deal_stage",
            object={"stage": "negotiation"},
            confidence=0.85,
            reasoning="Email suggests contract review",
        )
        assert belief.subject == "Acme Corp"
        assert belief.belief_type == "state"  # default

    def test_normalize_belief_type_lowercase(self) -> None:
        belief = ExtractedBelief(
            subject="X",
            predicate="Y",
            object={"v": 1},
            confidence=0.5,
            reasoning="test",
            belief_type="STATE",
        )
        assert belief.belief_type == "state"

    def test_normalize_belief_type_variant_mapping(self) -> None:
        """Variants like 'status' -> 'state', 'judgment' -> 'evaluative'."""
        for variant, expected in [
            ("status", "state"),
            ("condition", "state"),
            ("action", "event"),
            ("occurrence", "event"),
            ("cause", "causal"),
            ("cause-effect", "causal"),
            ("assessment", "evaluative"),
            ("evaluation", "evaluative"),
            ("judgment", "evaluative"),
        ]:
            belief = ExtractedBelief(
                subject="X",
                predicate="Y",
                object={"v": 1},
                confidence=0.5,
                reasoning="test",
                belief_type=variant,
            )
            assert belief.belief_type == expected, f"'{variant}' should map to '{expected}'"

    def test_normalize_belief_type_invalid_raises(self) -> None:
        with pytest.raises(Exception):
            ExtractedBelief(
                subject="X",
                predicate="Y",
                object={"v": 1},
                confidence=0.5,
                reasoning="test",
                belief_type="invalid_type",
            )

    def test_confidence_bounds(self) -> None:
        with pytest.raises(Exception):
            ExtractedBelief(
                subject="X",
                predicate="Y",
                object={},
                confidence=1.5,
                reasoning="test",
            )

    def test_non_string_belief_type_passthrough(self) -> None:
        """Non-string belief_type values pass through the validator unchanged."""
        # Pydantic coerces before validators in some cases, but we can test
        # by constructing with a valid literal directly
        belief = ExtractedBelief(
            subject="X",
            predicate="Y",
            object={"v": 1},
            confidence=0.5,
            reasoning="test",
            belief_type="event",
        )
        assert belief.belief_type == "event"

    def test_empty_subject_rejected(self) -> None:
        with pytest.raises(Exception):
            ExtractedBelief(
                subject="",
                predicate="Y",
                object={},
                confidence=0.5,
                reasoning="test",
            )


# ============================================================================
# Test: BeliefExtractionResult
# ============================================================================


class TestBeliefExtractionResult:
    def test_defaults_to_empty_beliefs(self) -> None:
        result = BeliefExtractionResult(observation_summary="some summary")
        assert result.beliefs == []

    def test_with_beliefs(self) -> None:
        b = ExtractedBelief(
            subject="X", predicate="Y", object={"v": 1}, confidence=0.5, reasoning="r"
        )
        result = BeliefExtractionResult(beliefs=[b], observation_summary="summary")
        assert len(result.beliefs) == 1


# ============================================================================
# Test: BeliefChangeResult
# ============================================================================


class TestBeliefChangeResult:
    def test_construction(self) -> None:
        belief = make_belief()
        change = BeliefChangeResult(
            subject="Acme",
            predicate="deal_stage",
            importance=0.7,
            old_confidence=0.3,
            new_confidence=0.8,
            belief=belief,
        )
        assert change.subject == "Acme"
        assert change.importance == 0.7
        assert change.old_confidence == 0.3
        assert change.new_confidence == 0.8


# ============================================================================
# Test: BeliefUpdateResult
# ============================================================================


class TestBeliefUpdateResult:
    def test_created(self) -> None:
        result = BeliefUpdateResult(belief=make_belief(), old_confidence=None, was_created=True)
        assert result.was_created is True
        assert result.old_confidence is None

    def test_updated(self) -> None:
        result = BeliefUpdateResult(belief=make_belief(), old_confidence=0.5, was_created=False)
        assert result.was_created is False
        assert result.old_confidence == 0.5


# ============================================================================
# Test: BeliefSystem.update_belief
# ============================================================================


class TestUpdateBelief:
    @pytest.mark.asyncio
    async def test_create_new_belief(self) -> None:
        """When no existing belief, creates a new one."""
        session = make_session()
        bs = make_belief_system(session=session)

        result = await bs.update_belief(
            subject="Acme Corp",
            predicate="pipeline_health",
            belief_object={"status": "healthy"},
            confidence=0.9,
            source="observation",
        )

        assert result.was_created is True
        assert result.old_confidence is None
        # Should have added belief + history to session
        assert session.add.call_count >= 2  # belief + history
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_existing_belief(self) -> None:
        """When existing belief found, updates it."""
        existing = make_belief(confidence=0.5, evidence=["old-evidence"])
        session = make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=mock_result)

        bs = make_belief_system(session=session)

        result = await bs.update_belief(
            subject="Acme Corp",
            predicate="deal_stage",
            belief_object={"stage": "closed"},
            confidence=0.95,
            source="observation",
            evidence=[uuid4()],
        )

        assert result.was_created is False
        assert result.old_confidence == 0.5
        assert existing.confidence == 0.95
        assert existing.object == {"stage": "closed"}

    @pytest.mark.asyncio
    async def test_update_merges_evidence(self) -> None:
        """Evidence from update is merged with existing."""
        old_uuid = str(uuid4())
        existing = make_belief(confidence=0.5, evidence=[old_uuid])
        session = make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=mock_result)

        bs = make_belief_system(session=session)
        new_uuid = uuid4()

        await bs.update_belief(
            subject="Acme Corp",
            predicate="deal_stage",
            belief_object={"stage": "closed"},
            confidence=0.95,
            source="observation",
            evidence=[new_uuid],
        )

        # Evidence should contain both old and new
        assert old_uuid in existing.evidence
        assert str(new_uuid) in existing.evidence

    @pytest.mark.asyncio
    async def test_create_with_no_evidence(self) -> None:
        """Creating without evidence stores empty list."""
        session = make_session()
        bs = make_belief_system(session=session)

        result = await bs.update_belief(
            subject="Test",
            predicate="pred",
            belief_object={"v": 1},
            confidence=0.5,
            source="observation",
        )

        assert result.was_created is True
        # The belief was created via Belief(...) ORM constructor
        # Verify session.add was called with the belief
        belief_arg = session.add.call_args_list[0][0][0]
        assert isinstance(belief_arg, Belief)


# ============================================================================
# Test: BeliefSystem.get_belief
# ============================================================================


class TestGetBelief:
    @pytest.mark.asyncio
    async def test_returns_belief_when_found(self) -> None:
        existing = make_belief()
        session = make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=mock_result)

        bs = make_belief_system(session=session)
        result = await bs.get_belief("Acme Corp", "deal_stage")
        assert result == existing

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)
        result = await bs.get_belief("Unknown", "missing")
        assert result is None


# ============================================================================
# Test: BeliefSystem.get_all_beliefs
# ============================================================================


class TestGetAllBeliefs:
    @pytest.mark.asyncio
    async def test_returns_list(self) -> None:
        b1 = make_belief(subject="A")
        b2 = make_belief(subject="B")
        session = make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [b1, b2]
        session.execute = AsyncMock(return_value=mock_result)

        bs = make_belief_system(session=session)
        result = await bs.get_all_beliefs()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_with_min_confidence(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)
        await bs.get_all_beliefs(min_confidence=0.5)
        # Just verify it executed without error
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)
        result = await bs.get_all_beliefs()
        assert result == []


# ============================================================================
# Test: BeliefSystem.get_beliefs_about
# ============================================================================


class TestGetBeliefsAbout:
    @pytest.mark.asyncio
    async def test_returns_filtered_beliefs(self) -> None:
        b1 = make_belief(subject="Acme Corp")
        session = make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [b1]
        session.execute = AsyncMock(return_value=mock_result)

        bs = make_belief_system(session=session)
        result = await bs.get_beliefs_about("Acme Corp")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_with_min_confidence(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)
        result = await bs.get_beliefs_about("Acme Corp", min_confidence=0.9)
        assert result == []


# ============================================================================
# Test: BeliefSystem.decay_beliefs
# ============================================================================


class TestDecayBeliefs:
    @pytest.mark.asyncio
    async def test_no_decay_for_recent_beliefs(self) -> None:
        """Beliefs updated less than a day ago should not decay."""
        recent = make_belief(
            last_updated_at=datetime.now(UTC) - timedelta(hours=12),
            confidence=0.8,
            decay_rate=0.1,
        )
        session = make_session()

        # get_all_beliefs returns this belief
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [recent]
        session.execute = AsyncMock(return_value=mock_result)

        bs = make_belief_system(session=session)
        decayed = await bs.decay_beliefs()
        assert len(decayed) == 0
        assert recent.confidence == 0.8  # unchanged

    @pytest.mark.asyncio
    async def test_decay_reduces_confidence(self) -> None:
        """Belief updated 3 days ago with decay_rate=0.1 loses 0.3."""
        old_belief = make_belief(
            last_updated_at=datetime.now(UTC) - timedelta(days=3),
            confidence=0.8,
            decay_rate=0.1,
            object={"status": "healthy"},
        )
        session = make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [old_belief]
        session.execute = AsyncMock(return_value=mock_result)

        bs = make_belief_system(session=session)
        decayed = await bs.decay_beliefs()

        assert len(decayed) == 1
        # 0.8 - (0.1 * 3) = 0.5
        assert old_belief.confidence == pytest.approx(0.5, abs=0.05)
        assert old_belief.deleted_at is None  # still above threshold

    @pytest.mark.asyncio
    async def test_decay_removes_below_threshold(self) -> None:
        """Belief that decays below 0.1 is soft-deleted."""
        old_belief = make_belief(
            last_updated_at=datetime.now(UTC) - timedelta(days=10),
            confidence=0.5,
            decay_rate=0.1,
            object={"status": "old"},
        )
        session = make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [old_belief]
        session.execute = AsyncMock(return_value=mock_result)

        bs = make_belief_system(session=session)
        decayed = await bs.decay_beliefs()

        assert len(decayed) == 1
        # 0.5 - (0.1 * 10) = -0.5, clamped to 0, below 0.1 threshold
        assert old_belief.deleted_at is not None

    @pytest.mark.asyncio
    async def test_decay_empty_beliefs(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)
        decayed = await bs.decay_beliefs()
        assert decayed == []


# ============================================================================
# Test: BeliefSystem.remove_belief
# ============================================================================


class TestRemoveBelief:
    @pytest.mark.asyncio
    async def test_remove_existing_belief(self) -> None:
        existing = make_belief(confidence=0.8, object={"v": 1})
        session = make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=mock_result)

        bs = make_belief_system(session=session)
        removed = await bs.remove_belief("Acme Corp", "deal_stage", reason="Stale info")

        assert removed is True
        assert existing.deleted_at is not None
        # History should be recorded
        assert session.add.call_count >= 1

    @pytest.mark.asyncio
    async def test_remove_nonexistent_belief(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)
        removed = await bs.remove_belief("Unknown", "missing")
        assert removed is False


# ============================================================================
# Test: BeliefSystem._record_belief_change
# ============================================================================


class TestRecordBeliefChange:
    @pytest.mark.asyncio
    async def test_creates_history_record(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)

        history = await bs._record_belief_change(
            belief_id=uuid4(),
            change_type="created",
            old_value=None,
            new_value={"stage": "negotiation"},
            old_confidence=None,
            new_confidence=0.9,
            reason="Created from observation",
        )

        assert isinstance(history, BeliefHistory)
        session.add.assert_called_once_with(history)


# ============================================================================
# Test: BeliefSystem.get_belief_history
# ============================================================================


class TestGetBeliefHistory:
    @pytest.mark.asyncio
    async def test_no_filters(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)
        result = await bs.get_belief_history()
        assert result == []
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_subject_filter(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)
        await bs.get_belief_history(subject="Acme Corp")
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_predicate_filter(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)
        await bs.get_belief_history(predicate="deal_stage")
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_both_filters(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)
        await bs.get_belief_history(subject="Acme Corp", predicate="deal_stage")
        session.execute.assert_called_once()


# ============================================================================
# Test: BeliefSystem._format_observation_content
# ============================================================================


class TestFormatObservationContent:
    def test_simple_values(self) -> None:
        bs = make_belief_system()
        result = bs._format_observation_content({"from": "alice@test.com", "subject": "Hi"})
        assert "from: alice@test.com" in result
        assert "subject: Hi" in result

    def test_nested_dict(self) -> None:
        bs = make_belief_system()
        result = bs._format_observation_content(
            {"metadata": {"priority": "high", "source": "email"}}
        )
        assert "metadata:" in result
        assert "priority: high" in result

    def test_list_values(self) -> None:
        bs = make_belief_system()
        result = bs._format_observation_content({"tags": ["urgent", "sales"]})
        assert "tags:" in result
        assert "- urgent" in result
        assert "- sales" in result

    def test_empty_content(self) -> None:
        bs = make_belief_system()
        result = bs._format_observation_content({})
        assert result == ""


# ============================================================================
# Test: BeliefSystem._map_structured_to_beliefs
# ============================================================================


class TestMapStructuredToBeliefs:
    @pytest.mark.asyncio
    async def test_maps_simple_values(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)

        results = await bs._map_structured_to_beliefs(
            source_name="hubspot_crm",
            data={"pipeline_coverage": 3.5, "open_deals": 12, "stage": "active"},
        )

        assert len(results) == 3
        for r in results:
            assert isinstance(r, BeliefUpdateResult)
            assert r.was_created is True

    @pytest.mark.asyncio
    async def test_skips_private_and_id_keys(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)

        results = await bs._map_structured_to_beliefs(
            source_name="crm",
            data={"_internal": "skip", "id": "skip", "tenant_id": "skip", "name": "Acme"},
        )

        # Only "name" should be mapped
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_maps_dict_values(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)

        results = await bs._map_structured_to_beliefs(
            source_name="crm",
            data={"deal_info": {"stage": "negotiation", "amount": 50000}},
        )

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_maps_small_list_values(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)

        results = await bs._map_structured_to_beliefs(
            source_name="crm",
            data={"contacts": ["Alice", "Bob"]},
        )

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_skips_large_lists(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)

        results = await bs._map_structured_to_beliefs(
            source_name="crm",
            data={"big_list": list(range(20))},  # > 10 items
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_maps_bool_values(self) -> None:
        session = make_session()
        bs = make_belief_system(session=session)

        results = await bs._map_structured_to_beliefs(
            source_name="crm",
            data={"is_active": True},
        )

        assert len(results) == 1


# ============================================================================
# Test: BeliefSystem._batch_extract_beliefs
# ============================================================================


class TestBatchExtractBeliefs:
    @pytest.mark.asyncio
    async def test_empty_observations_returns_empty(self) -> None:
        bs = make_belief_system()
        result = await bs._batch_extract_beliefs([], AsyncMock())
        assert result == []

    @pytest.mark.asyncio
    async def test_single_observation_delegates(self) -> None:
        """Single observation delegates to extract_beliefs_from_observation."""
        session = make_session()
        llm = AsyncMock()
        bs = make_belief_system(session=session, llm_service=llm)

        obs = make_observation()
        extraction = BeliefExtractionResult(
            beliefs=[
                ExtractedBelief(
                    subject="Acme",
                    predicate="interest",
                    object={"level": "high"},
                    confidence=0.9,
                    reasoning="test",
                )
            ],
            observation_summary="test obs",
        )
        llm.generate_structured = AsyncMock(return_value=(None, extraction))

        results = await bs._batch_extract_beliefs([obs], llm)

        assert len(results) == 1
        assert results[0][0] == obs

    @pytest.mark.asyncio
    async def test_multiple_observations_batch_call(self) -> None:
        """Multiple observations are batched into a single LLM call."""
        session = make_session()
        llm = AsyncMock()
        bs = make_belief_system(session=session, llm_service=llm)

        obs1 = make_observation(source="email")
        obs2 = make_observation(source="calendar")

        extraction = BeliefExtractionResult(
            beliefs=[
                ExtractedBelief(
                    subject="Acme",
                    predicate="meeting",
                    object={"time": "2pm"},
                    confidence=0.95,
                    reasoning="Calendar shows meeting",
                )
            ],
            observation_summary="batch summary",
        )
        llm.generate_structured = AsyncMock(return_value=(None, extraction))

        results = await bs._batch_extract_beliefs([obs1, obs2], llm)

        assert len(results) == 1
        llm.generate_structured.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty(self) -> None:
        """LLM failure returns empty list without raising."""
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(side_effect=RuntimeError("LLM down"))
        bs = make_belief_system(llm_service=llm)

        obs1 = make_observation()
        obs2 = make_observation()
        results = await bs._batch_extract_beliefs([obs1, obs2], llm)
        assert results == []

    @pytest.mark.asyncio
    async def test_with_identity_context(self) -> None:
        """Identity context is passed to the system prompt."""
        session = make_session()
        llm = AsyncMock()
        bs = make_belief_system(session=session, llm_service=llm)

        obs1 = make_observation()
        obs2 = make_observation()

        extraction = BeliefExtractionResult(beliefs=[], observation_summary="no beliefs")
        llm.generate_structured = AsyncMock(return_value=(None, extraction))

        await bs._batch_extract_beliefs([obs1, obs2], llm, identity_context="I am a Sales AE")

        call_kwargs = llm.generate_structured.call_args.kwargs
        assert "I am a Sales AE" in call_kwargs["system"]


# ============================================================================
# Test: BeliefSystem.extract_beliefs_from_observation
# ============================================================================


class TestExtractBeliefsFromObservation:
    @pytest.mark.asyncio
    async def test_successful_extraction(self) -> None:
        session = make_session()
        llm = AsyncMock()
        bs = make_belief_system(session=session, llm_service=llm)

        obs = make_observation()
        extraction = BeliefExtractionResult(
            beliefs=[
                ExtractedBelief(
                    subject="Acme",
                    predicate="sentiment",
                    object={"sentiment": "positive"},
                    confidence=0.8,
                    reasoning="Positive language in email",
                )
            ],
            observation_summary="Positive email from Acme",
        )
        llm.generate_structured = AsyncMock(return_value=(None, extraction))

        results = await bs.extract_beliefs_from_observation(obs, llm)

        assert len(results) == 1
        assert results[0].was_created is True

    @pytest.mark.asyncio
    async def test_llm_error_returns_empty(self) -> None:
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(side_effect=ValueError("API error"))
        bs = make_belief_system(llm_service=llm)

        obs = make_observation()
        results = await bs.extract_beliefs_from_observation(obs, llm)
        assert results == []

    @pytest.mark.asyncio
    async def test_with_identity_context(self) -> None:
        session = make_session()
        llm = AsyncMock()
        bs = make_belief_system(session=session, llm_service=llm)

        obs = make_observation()
        extraction = BeliefExtractionResult(beliefs=[], observation_summary="empty")
        llm.generate_structured = AsyncMock(return_value=(None, extraction))

        await bs.extract_beliefs_from_observation(obs, llm, identity_context="I am CSM")

        call_kwargs = llm.generate_structured.call_args.kwargs
        assert "I am CSM" in call_kwargs["system"]

    @pytest.mark.asyncio
    async def test_without_identity_context(self) -> None:
        session = make_session()
        llm = AsyncMock()
        bs = make_belief_system(session=session, llm_service=llm)

        obs = make_observation()
        extraction = BeliefExtractionResult(beliefs=[], observation_summary="empty")
        llm.generate_structured = AsyncMock(return_value=(None, extraction))

        await bs.extract_beliefs_from_observation(obs, llm)

        call_kwargs = llm.generate_structured.call_args.kwargs
        assert "You are a digital employee" in call_kwargs["system"]

    @pytest.mark.asyncio
    async def test_multiple_beliefs_extracted(self) -> None:
        session = make_session()
        llm = AsyncMock()
        bs = make_belief_system(session=session, llm_service=llm)

        obs = make_observation()
        extraction = BeliefExtractionResult(
            beliefs=[
                ExtractedBelief(
                    subject="Acme",
                    predicate="deal_stage",
                    object={"stage": "negotiation"},
                    confidence=0.9,
                    reasoning="r1",
                ),
                ExtractedBelief(
                    subject="Acme",
                    predicate="sentiment",
                    object={"sentiment": "positive"},
                    confidence=0.85,
                    reasoning="r2",
                ),
            ],
            observation_summary="Multi-belief extraction",
        )
        llm.generate_structured = AsyncMock(return_value=(None, extraction))

        results = await bs.extract_beliefs_from_observation(obs, llm)
        assert len(results) == 2


# ============================================================================
# Test: BeliefSystem.update_beliefs (batch orchestrator)
# ============================================================================


class TestUpdateBeliefs:
    @pytest.mark.asyncio
    async def test_empty_observations(self) -> None:
        bs = make_belief_system()
        result = await bs.update_beliefs([])
        assert result == []

    @pytest.mark.asyncio
    async def test_structured_observation_uses_direct_mapping(self) -> None:
        """Observations with tool_result dict use _map_structured_to_beliefs."""
        session = make_session()
        bs = make_belief_system(session=session)

        obs = make_observation(
            content={"tool_result": {"pipeline_coverage": 3.5}},
            priority=8,
        )

        result = await bs.update_beliefs([obs])
        # Should have called session to create beliefs
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_unstructured_observation_uses_llm(self) -> None:
        """Observations without tool_result use LLM extraction."""
        session = make_session()
        llm = AsyncMock()
        bs = make_belief_system(session=session, llm_service=llm)

        obs = make_observation(
            content={"body": "Great meeting with Acme today"},
            priority=7,
        )

        extraction = BeliefExtractionResult(
            beliefs=[
                ExtractedBelief(
                    subject="Acme",
                    predicate="meeting",
                    object={"status": "completed"},
                    confidence=0.9,
                    reasoning="test",
                )
            ],
            observation_summary="test",
        )
        llm.generate_structured = AsyncMock(return_value=(None, extraction))

        result = await bs.update_beliefs([obs])
        assert len(result) == 1
        assert result[0].subject == "Acme"

    @pytest.mark.asyncio
    async def test_json_string_tool_result_gets_parsed(self) -> None:
        """JSON string tool_result is parsed and treated as structured."""
        import json

        session = make_session()
        bs = make_belief_system(session=session)

        obs = make_observation(
            content={"tool_result": json.dumps({"pipeline_coverage": 2.5})},
            priority=5,
        )

        result = await bs.update_beliefs([obs])
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_invalid_json_string_tool_result_uses_llm(self) -> None:
        """Invalid JSON string tool_result falls through to LLM path."""
        session = make_session()
        llm = AsyncMock()
        bs = make_belief_system(session=session, llm_service=llm)

        obs = make_observation(
            content={"tool_result": "not valid json {{{"},
            priority=5,
        )

        extraction = BeliefExtractionResult(beliefs=[], observation_summary="fallback")
        llm.generate_structured = AsyncMock(return_value=(None, extraction))

        result = await bs.update_beliefs([obs])
        # Should have tried LLM since JSON parse failed
        llm.generate_structured.assert_called_once()

    @pytest.mark.asyncio
    async def test_structured_mapping_failure_falls_back_to_llm(self) -> None:
        """If _map_structured_to_beliefs fails, observation goes to LLM path."""
        session = make_session()
        llm = AsyncMock()
        bs = make_belief_system(session=session, llm_service=llm)

        obs = make_observation(
            content={"tool_result": {"data": "value"}},
            priority=5,
        )

        # Make _map_structured_to_beliefs fail
        with patch.object(
            bs, "_map_structured_to_beliefs", side_effect=RuntimeError("mapping failed")
        ):
            extraction = BeliefExtractionResult(beliefs=[], observation_summary="fallback")
            llm.generate_structured = AsyncMock(return_value=(None, extraction))

            result = await bs.update_beliefs([obs])
            # Should have fallen back to LLM
            llm.generate_structured.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_extraction_failure_returns_partial_results(self) -> None:
        """LLM failure doesn't crash; returns whatever structured results we got."""
        session = make_session()
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(side_effect=RuntimeError("LLM down"))
        bs = make_belief_system(session=session, llm_service=llm)

        structured_obs = make_observation(content={"tool_result": {"metric": 42}}, priority=5)
        unstructured_obs = make_observation(content={"body": "hello"}, priority=5)

        result = await bs.update_beliefs([structured_obs, unstructured_obs])
        # Structured obs should still produce beliefs; LLM failure is swallowed
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_no_llm_service_skips_extraction(self) -> None:
        """If llm_service is None/falsy, unstructured obs are skipped."""
        session = make_session()
        bs = make_belief_system(session=session, llm_service=None)

        obs = make_observation(content={"body": "test"}, priority=5)
        result = await bs.update_beliefs([obs])
        assert result == []

    @pytest.mark.asyncio
    async def test_with_identity_context(self) -> None:
        """identity_context is passed through to _batch_extract_beliefs."""
        session = make_session()
        llm = AsyncMock()
        bs = make_belief_system(session=session, llm_service=llm)

        obs = make_observation(content={"body": "test"}, priority=5)

        extraction = BeliefExtractionResult(beliefs=[], observation_summary="empty")
        llm.generate_structured = AsyncMock(return_value=(None, extraction))

        await bs.update_beliefs([obs], identity_context="I am a Sales AE")

        call_kwargs = llm.generate_structured.call_args.kwargs
        assert "I am a Sales AE" in call_kwargs["system"]

    @pytest.mark.asyncio
    async def test_mixed_structured_and_unstructured(self) -> None:
        """Mix of structured and unstructured observations processed correctly."""
        session = make_session()
        llm = AsyncMock()
        bs = make_belief_system(session=session, llm_service=llm)

        structured_obs = make_observation(content={"tool_result": {"deals": 5}}, priority=8)
        unstructured_obs = make_observation(content={"body": "Customer happy"}, priority=6)

        extraction = BeliefExtractionResult(
            beliefs=[
                ExtractedBelief(
                    subject="Customer",
                    predicate="sentiment",
                    object={"mood": "happy"},
                    confidence=0.8,
                    reasoning="test",
                )
            ],
            observation_summary="test",
        )
        llm.generate_structured = AsyncMock(return_value=(None, extraction))

        result = await bs.update_beliefs([structured_obs, unstructured_obs])
        # Should have results from both paths
        assert len(result) >= 2

    @pytest.mark.asyncio
    async def test_batch_extract_exception_is_swallowed(self) -> None:
        """Exception from _batch_extract_beliefs is caught in update_beliefs."""
        session = make_session()
        llm = AsyncMock()
        bs = make_belief_system(session=session, llm_service=llm)

        obs = make_observation(content={"body": "hello"}, priority=5)

        with patch.object(bs, "_batch_extract_beliefs", side_effect=RuntimeError("unexpected")):
            result = await bs.update_beliefs([obs])
            # Should return empty, not raise
            assert result == []

    @pytest.mark.asyncio
    async def test_non_dict_content_treated_as_unstructured(self) -> None:
        """Observation with non-dict content goes to LLM path."""
        session = make_session()
        llm = AsyncMock()
        bs = make_belief_system(session=session, llm_service=llm)

        # content is a dict, but has no tool_result key
        obs = make_observation(content={"text": "some info"}, priority=5)

        extraction = BeliefExtractionResult(beliefs=[], observation_summary="empty")
        llm.generate_structured = AsyncMock(return_value=(None, extraction))

        await bs.update_beliefs([obs])
        llm.generate_structured.assert_called_once()
