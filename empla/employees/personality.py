"""
empla.employees.personality - Employee Personality System

Personality traits that drive decision-making and behavior.
Based on the Big Five personality model with role-specific additions.

Example:
    >>> from empla.employees.personality import Personality, CommunicationStyle
    >>>
    >>> personality = Personality(
    ...     openness=0.7,
    ...     conscientiousness=0.8,
    ...     extraversion=0.9,
    ...     agreeableness=0.6,
    ...     neuroticism=0.3,
    ...     communication=CommunicationStyle(
    ...         tone="enthusiastic",
    ...         formality="professional_casual",
    ...         verbosity="balanced"
    ...     )
    ... )
"""

import copy
import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class Tone(str, Enum):
    """Communication tone."""

    PROFESSIONAL = "professional"
    ENTHUSIASTIC = "enthusiastic"
    SUPPORTIVE = "supportive"
    CASUAL = "casual"
    FORMAL = "formal"


class Formality(str, Enum):
    """Level of formality in communication."""

    FORMAL = "formal"
    PROFESSIONAL = "professional"
    PROFESSIONAL_CASUAL = "professional_casual"
    CASUAL = "casual"


class Verbosity(str, Enum):
    """Communication length preference."""

    CONCISE = "concise"
    BALANCED = "balanced"
    DETAILED = "detailed"


class CommunicationStyle(BaseModel):
    """How the employee communicates."""

    tone: Tone = Field(default=Tone.PROFESSIONAL, description="Overall tone")
    formality: Formality = Field(default=Formality.PROFESSIONAL, description="Formality level")
    verbosity: Verbosity = Field(default=Verbosity.BALANCED, description="Length preference")
    emoji_usage: bool = Field(default=False, description="Whether to use emojis")

    def to_prompt_context(self) -> str:
        """Convert to context for LLM prompts."""
        return (
            f"Communication style: {self.tone.value} tone, {self.formality.value} formality, "
            f"{self.verbosity.value} length. {'Use emojis sparingly.' if self.emoji_usage else 'No emojis.'}"
        )


class DecisionStyle(BaseModel):
    """How the employee makes decisions."""

    risk_tolerance: float = Field(
        default=0.5, ge=0.0, le=1.0, description="0=very conservative, 1=very aggressive"
    )
    decision_speed: float = Field(
        default=0.5, ge=0.0, le=1.0, description="0=very deliberate, 1=very quick"
    )
    data_vs_intuition: float = Field(
        default=0.5, ge=0.0, le=1.0, description="0=pure intuition, 1=pure data-driven"
    )
    collaborative: float = Field(
        default=0.5, ge=0.0, le=1.0, description="0=independent, 1=consensus-seeking"
    )

    def to_prompt_context(self) -> str:
        """Convert to context for LLM prompts."""
        risk = (
            "conservative"
            if self.risk_tolerance < 0.4
            else "moderate"
            if self.risk_tolerance < 0.7
            else "aggressive"
        )
        speed = (
            "deliberate"
            if self.decision_speed < 0.4
            else "balanced"
            if self.decision_speed < 0.7
            else "quick"
        )
        approach = (
            "intuition-driven"
            if self.data_vs_intuition < 0.4
            else "balanced"
            if self.data_vs_intuition < 0.7
            else "data-driven"
        )
        collab = (
            "independent"
            if self.collaborative < 0.4
            else "collaborative"
            if self.collaborative < 0.7
            else "highly collaborative"
        )

        return f"Decision style: {risk} risk tolerance, {speed} decisions, {approach} approach, {collab} style."


class Personality(BaseModel):
    """
    Complete employee personality profile.

    Based on Big Five personality model with professional additions.

    Attributes:
        openness: Creativity and innovation (0-1)
        conscientiousness: Organization and reliability (0-1)
        extraversion: Outgoingness and energy (0-1)
        agreeableness: Cooperation and warmth (0-1)
        neuroticism: Emotional reactivity (0-1, lower is calmer)
        communication: Communication style preferences
        decision_style: Decision-making preferences
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Big Five traits (0-1 scale)
    openness: float = Field(default=0.5, ge=0.0, le=1.0, description="Innovation vs tradition")
    conscientiousness: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Organized vs spontaneous"
    )
    extraversion: float = Field(default=0.5, ge=0.0, le=1.0, description="Outgoing vs reserved")
    agreeableness: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Cooperative vs competitive"
    )
    neuroticism: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Emotional reactivity (lower is calmer)"
    )

    # Professional traits
    communication: CommunicationStyle = Field(default_factory=CommunicationStyle)
    decision_style: DecisionStyle = Field(default_factory=DecisionStyle)

    # Work style
    proactivity: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Proactive vs reactive work style"
    )
    persistence: float = Field(
        default=0.7, ge=0.0, le=1.0, description="How persistent when facing obstacles"
    )
    attention_to_detail: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Detail-oriented vs big picture"
    )

    def to_system_prompt(self) -> str:
        """
        Convert personality to system prompt context.

        Returns:
            String describing personality for LLM context
        """
        traits = []

        # Big Five interpretation
        if self.openness > 0.7:
            traits.append("creative and innovative")
        elif self.openness < 0.3:
            traits.append("methodical and traditional")

        if self.conscientiousness > 0.7:
            traits.append("highly organized and detail-oriented")
        elif self.conscientiousness < 0.3:
            traits.append("flexible and spontaneous")

        if self.extraversion > 0.7:
            traits.append("outgoing and energetic")
        elif self.extraversion < 0.3:
            traits.append("thoughtful and reserved")

        if self.agreeableness > 0.7:
            traits.append("warm and collaborative")
        elif self.agreeableness < 0.3:
            traits.append("direct and competitive")

        if self.neuroticism < 0.3:
            traits.append("calm under pressure")
        elif self.neuroticism > 0.7:
            traits.append("emotionally engaged")

        # Work style
        if self.proactivity > 0.7:
            traits.append("highly proactive")
        if self.persistence > 0.7:
            traits.append("persistent when facing obstacles")

        personality_desc = ", ".join(traits) if traits else "balanced personality"

        return (
            f"Personality: {personality_desc}. "
            f"{self.communication.to_prompt_context()} "
            f"{self.decision_style.to_prompt_context()}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Personality":
        """Create a Personality from a dictionary.

        Handles preset resolution: if *data* contains only a ``preset``
        key, the matching pre-built template is returned.  Otherwise the
        dict is validated directly against the Personality schema.

        Args:
            data: Dictionary of personality fields, or ``{"preset": "<name>"}``
                to load a pre-built template.

        Returns:
            A Personality instance.

        Raises:
            TypeError: If *data* is not a dict or the preset value is not a string.
        """
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict for Personality.from_dict, got {type(data).__name__}")
        if set(data.keys()) == {"preset"}:
            preset_value = data["preset"]
            if not isinstance(preset_value, str):
                raise TypeError(f"Expected str for preset name, got {type(preset_value).__name__}")
            return cls.from_preset(preset_value)
        return cls.model_validate(data)

    @classmethod
    def from_preset(cls, preset_name: str) -> "Personality":
        """Return a deep copy of the pre-built Personality for a preset name.

        Args:
            preset_name: A role code (e.g. ``"sales_ae"``, ``"csm"``, ``"pm"``).
                Unknown names return default traits.

        Returns:
            A new Personality instance (deep-copied from the catalog template,
            or default-constructed for unknown presets).
        """
        from empla.employees.catalog import get_role

        role = get_role(preset_name)
        if role is None:
            logger.warning("Unknown personality preset %r, returning defaults", preset_name)
            return cls()
        return copy.deepcopy(role.personality)


# Backwards-compat aliases — prefer ROLE_CATALOG for new code.
# These are lazily resolved to avoid a circular import
# (config → personality → catalog → config).
_COMPAT_ALIASES: dict[str, str] = {
    "SALES_AE_PERSONALITY": "sales_ae",
    "CSM_PERSONALITY": "csm",
    "PM_PERSONALITY": "pm",
}


def __getattr__(name: str) -> Any:
    if name in _COMPAT_ALIASES:
        from empla.employees.catalog import ROLE_CATALOG

        role = ROLE_CATALOG.get(_COMPAT_ALIASES[name])
        if role is None:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        return copy.deepcopy(role.personality)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [  # noqa: F822 — lazy attrs via __getattr__
    "CSM_PERSONALITY",
    "PM_PERSONALITY",
    "SALES_AE_PERSONALITY",
    "CommunicationStyle",
    "DecisionStyle",
    "Formality",
    "Personality",
    "Tone",
    "Verbosity",
]
