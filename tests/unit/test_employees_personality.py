"""
Tests for empla.employees.personality module.

Tests personality traits, communication styles, and pre-built templates.
"""

import pytest
from pydantic import ValidationError

from empla.employees.personality import (
    CommunicationStyle,
    DecisionStyle,
    Formality,
    Personality,
    Tone,
    Verbosity,
    SALES_AE_PERSONALITY,
    CSM_PERSONALITY,
    PM_PERSONALITY,
)


class TestToneEnum:
    """Tests for Tone enum."""

    def test_tone_values(self):
        """Test all tone values exist."""
        assert Tone.PROFESSIONAL == "professional"
        assert Tone.ENTHUSIASTIC == "enthusiastic"
        assert Tone.SUPPORTIVE == "supportive"
        assert Tone.CASUAL == "casual"
        assert Tone.FORMAL == "formal"

    def test_tone_count(self):
        """Test expected number of tones."""
        assert len(Tone) == 5


class TestFormalityEnum:
    """Tests for Formality enum."""

    def test_formality_values(self):
        """Test all formality values exist."""
        assert Formality.FORMAL == "formal"
        assert Formality.PROFESSIONAL == "professional"
        assert Formality.PROFESSIONAL_CASUAL == "professional_casual"
        assert Formality.CASUAL == "casual"

    def test_formality_count(self):
        """Test expected number of formality levels."""
        assert len(Formality) == 4


class TestVerbosityEnum:
    """Tests for Verbosity enum."""

    def test_verbosity_values(self):
        """Test all verbosity values exist."""
        assert Verbosity.CONCISE == "concise"
        assert Verbosity.BALANCED == "balanced"
        assert Verbosity.DETAILED == "detailed"

    def test_verbosity_count(self):
        """Test expected number of verbosity levels."""
        assert len(Verbosity) == 3


class TestCommunicationStyle:
    """Tests for CommunicationStyle model."""

    def test_default_values(self):
        """Test default communication style values."""
        style = CommunicationStyle()
        assert style.tone == Tone.PROFESSIONAL
        assert style.formality == Formality.PROFESSIONAL
        assert style.verbosity == Verbosity.BALANCED
        assert style.emoji_usage is False

    def test_custom_values(self):
        """Test custom communication style values."""
        style = CommunicationStyle(
            tone=Tone.ENTHUSIASTIC,
            formality=Formality.CASUAL,
            verbosity=Verbosity.CONCISE,
            emoji_usage=True,
        )
        assert style.tone == Tone.ENTHUSIASTIC
        assert style.formality == Formality.CASUAL
        assert style.verbosity == Verbosity.CONCISE
        assert style.emoji_usage is True

    def test_to_prompt_context(self):
        """Test prompt context generation."""
        style = CommunicationStyle(
            tone=Tone.ENTHUSIASTIC,
            formality=Formality.PROFESSIONAL_CASUAL,
            verbosity=Verbosity.BALANCED,
            emoji_usage=False,
        )
        context = style.to_prompt_context()
        assert "enthusiastic" in context
        assert "professional_casual" in context
        assert "balanced" in context
        assert "No emojis" in context

    def test_to_prompt_context_with_emojis(self):
        """Test prompt context with emoji usage enabled."""
        style = CommunicationStyle(emoji_usage=True)
        context = style.to_prompt_context()
        assert "Use emojis sparingly" in context


class TestDecisionStyle:
    """Tests for DecisionStyle model."""

    def test_default_values(self):
        """Test default decision style values."""
        style = DecisionStyle()
        assert style.risk_tolerance == 0.5
        assert style.decision_speed == 0.5
        assert style.data_vs_intuition == 0.5
        assert style.collaborative == 0.5

    def test_custom_values(self):
        """Test custom decision style values."""
        style = DecisionStyle(
            risk_tolerance=0.8,
            decision_speed=0.9,
            data_vs_intuition=0.3,
            collaborative=0.2,
        )
        assert style.risk_tolerance == 0.8
        assert style.decision_speed == 0.9
        assert style.data_vs_intuition == 0.3
        assert style.collaborative == 0.2

    def test_validation_min_values(self):
        """Test validation rejects values below 0."""
        with pytest.raises(ValidationError):
            DecisionStyle(risk_tolerance=-0.1)

    def test_validation_max_values(self):
        """Test validation rejects values above 1."""
        with pytest.raises(ValidationError):
            DecisionStyle(risk_tolerance=1.1)

    def test_to_prompt_context_conservative(self):
        """Test prompt context for conservative decision maker."""
        style = DecisionStyle(risk_tolerance=0.2, decision_speed=0.3, data_vs_intuition=0.8)
        context = style.to_prompt_context()
        assert "conservative" in context
        assert "deliberate" in context
        assert "data-driven" in context

    def test_to_prompt_context_aggressive(self):
        """Test prompt context for aggressive decision maker."""
        style = DecisionStyle(risk_tolerance=0.9, decision_speed=0.8, data_vs_intuition=0.2)
        context = style.to_prompt_context()
        assert "aggressive" in context
        assert "quick" in context
        assert "intuition-driven" in context


class TestPersonality:
    """Tests for Personality model."""

    def test_default_values(self):
        """Test default personality values."""
        personality = Personality()
        # Big Five defaults
        assert personality.openness == 0.5
        assert personality.conscientiousness == 0.5
        assert personality.extraversion == 0.5
        assert personality.agreeableness == 0.5
        assert personality.neuroticism == 0.3
        # Work style defaults
        assert personality.proactivity == 0.7
        assert personality.persistence == 0.7
        assert personality.attention_to_detail == 0.5
        # Nested defaults
        assert isinstance(personality.communication, CommunicationStyle)
        assert isinstance(personality.decision_style, DecisionStyle)

    def test_custom_values(self):
        """Test custom personality values."""
        personality = Personality(
            openness=0.9,
            conscientiousness=0.8,
            extraversion=0.7,
            agreeableness=0.6,
            neuroticism=0.2,
            proactivity=0.95,
            persistence=0.85,
            attention_to_detail=0.75,
        )
        assert personality.openness == 0.9
        assert personality.conscientiousness == 0.8
        assert personality.extraversion == 0.7
        assert personality.agreeableness == 0.6
        assert personality.neuroticism == 0.2
        assert personality.proactivity == 0.95
        assert personality.persistence == 0.85
        assert personality.attention_to_detail == 0.75

    def test_validation_trait_range(self):
        """Test validation of trait ranges."""
        # Below minimum
        with pytest.raises(ValidationError):
            Personality(openness=-0.1)
        # Above maximum
        with pytest.raises(ValidationError):
            Personality(extraversion=1.5)

    def test_to_system_prompt_creative(self):
        """Test system prompt for creative personality."""
        personality = Personality(openness=0.9, proactivity=0.9)
        prompt = personality.to_system_prompt()
        assert "creative" in prompt or "innovative" in prompt
        assert "proactive" in prompt

    def test_to_system_prompt_organized(self):
        """Test system prompt for organized personality."""
        personality = Personality(conscientiousness=0.9)
        prompt = personality.to_system_prompt()
        assert "organized" in prompt or "detail-oriented" in prompt

    def test_to_system_prompt_outgoing(self):
        """Test system prompt for outgoing personality."""
        personality = Personality(extraversion=0.9)
        prompt = personality.to_system_prompt()
        assert "outgoing" in prompt or "energetic" in prompt

    def test_to_system_prompt_collaborative(self):
        """Test system prompt for collaborative personality."""
        personality = Personality(agreeableness=0.9)
        prompt = personality.to_system_prompt()
        assert "warm" in prompt or "collaborative" in prompt

    def test_to_system_prompt_calm(self):
        """Test system prompt for calm personality."""
        personality = Personality(neuroticism=0.1)
        prompt = personality.to_system_prompt()
        assert "calm" in prompt

    def test_to_dict(self):
        """Test conversion to dictionary."""
        personality = Personality(openness=0.8, extraversion=0.9)
        data = personality.to_dict()
        assert isinstance(data, dict)
        assert data["openness"] == 0.8
        assert data["extraversion"] == 0.9
        assert "communication" in data
        assert "decision_style" in data

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "openness": 0.7,
            "conscientiousness": 0.8,
            "extraversion": 0.6,
            "agreeableness": 0.5,
            "neuroticism": 0.3,
        }
        personality = Personality.from_dict(data)
        assert personality.openness == 0.7
        assert personality.conscientiousness == 0.8

    def test_round_trip_serialization(self):
        """Test serialization round-trip."""
        original = Personality(
            openness=0.8,
            communication=CommunicationStyle(tone=Tone.ENTHUSIASTIC),
            decision_style=DecisionStyle(risk_tolerance=0.7),
        )
        data = original.to_dict()
        restored = Personality.from_dict(data)
        assert restored.openness == original.openness
        assert restored.communication.tone == original.communication.tone
        assert restored.decision_style.risk_tolerance == original.decision_style.risk_tolerance


class TestPreBuiltPersonalities:
    """Tests for pre-built personality templates."""

    def test_sales_ae_personality_exists(self):
        """Test Sales AE personality template exists."""
        assert SALES_AE_PERSONALITY is not None
        assert isinstance(SALES_AE_PERSONALITY, Personality)

    def test_sales_ae_personality_traits(self):
        """Test Sales AE personality has expected traits."""
        p = SALES_AE_PERSONALITY
        # High extraversion for sales
        assert p.extraversion >= 0.8
        # High proactivity
        assert p.proactivity >= 0.8
        # Enthusiastic tone
        assert p.communication.tone == Tone.ENTHUSIASTIC
        # Higher risk tolerance
        assert p.decision_style.risk_tolerance >= 0.6

    def test_csm_personality_exists(self):
        """Test CSM personality template exists."""
        assert CSM_PERSONALITY is not None
        assert isinstance(CSM_PERSONALITY, Personality)

    def test_csm_personality_traits(self):
        """Test CSM personality has expected traits."""
        p = CSM_PERSONALITY
        # High agreeableness for customer success
        assert p.agreeableness >= 0.8
        # High conscientiousness for details
        assert p.conscientiousness >= 0.8
        # Supportive tone
        assert p.communication.tone == Tone.SUPPORTIVE
        # Lower risk tolerance (conservative)
        assert p.decision_style.risk_tolerance <= 0.5

    def test_pm_personality_exists(self):
        """Test PM personality template exists."""
        assert PM_PERSONALITY is not None
        assert isinstance(PM_PERSONALITY, Personality)

    def test_pm_personality_traits(self):
        """Test PM personality has expected traits."""
        p = PM_PERSONALITY
        # High openness for innovation
        assert p.openness >= 0.7
        # Data-driven decisions
        assert p.decision_style.data_vs_intuition >= 0.6
        # Professional tone
        assert p.communication.tone == Tone.PROFESSIONAL

    def test_personalities_are_distinct(self):
        """Test that role personalities are meaningfully different."""
        # Sales AE should be more extraverted than CSM
        assert SALES_AE_PERSONALITY.extraversion > CSM_PERSONALITY.extraversion
        # CSM should be more agreeable than Sales AE
        assert CSM_PERSONALITY.agreeableness > SALES_AE_PERSONALITY.agreeableness
        # PM should be more open than CSM
        assert PM_PERSONALITY.openness > CSM_PERSONALITY.openness
