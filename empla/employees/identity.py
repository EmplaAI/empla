"""
empla.employees.identity - Employee Identity System

Builds rich identity context for LLM prompts so every call knows
who the employee is, what they care about, and what they can do.

Example:
    >>> from empla.employees.identity import EmployeeIdentity
    >>>
    >>> identity = EmployeeIdentity.build(
    ...     name="Jordan Chen",
    ...     role="sales_ae",
    ...     personality_prompt="outgoing and energetic, highly organized",
    ...     goals=[{"description": "Maintain 3x pipeline", "priority": 9}],
    ...     capabilities=["email", "calendar", "crm"],
    ... )
    >>> print(identity.to_system_prompt())
"""

from pydantic import BaseModel, Field

# Human-readable titles for built-in roles
ROLE_TITLES: dict[str, str] = {
    "sales_ae": "Sales Account Executive",
    "csm": "Customer Success Manager",
    "pm": "Product Manager",
    "sdr": "Sales Development Representative",
    "recruiter": "Recruiter",
}

# One-line descriptions for built-in roles
ROLE_DESCRIPTIONS: dict[str, str] = {
    "sales_ae": ("You build and manage sales pipeline, prospect new accounts, and close revenue."),
    "csm": ("You ensure customer success through onboarding, health monitoring, and retention."),
    "pm": ("You drive product strategy, prioritize features, and ship high-impact releases."),
    "sdr": ("You generate qualified leads through outbound prospecting and inbound qualification."),
    "recruiter": ("You source, screen, and hire top talent to build high-performing teams."),
}


class EmployeeIdentity(BaseModel):
    """Identity context rendered into every LLM call."""

    name: str
    role: str
    role_title: str
    role_description: str
    personality_prompt: str
    goals_summary: str
    capabilities: list[str] = Field(default_factory=list)

    def to_system_prompt(self) -> str:
        """Render ~150 tokens of identity context for an LLM system prompt."""
        caps = ", ".join(self.capabilities) if self.capabilities else "none"
        return (
            f"You are {self.name}, a {self.role_title}. "
            f"{self.role_description}\n\n"
            f"Personality: {self.personality_prompt}\n\n"
            f"Your current goals:\n{self.goals_summary}\n\n"
            f"Available capabilities: {caps}"
        )

    @classmethod
    def build(
        cls,
        *,
        name: str,
        role: str,
        role_description: str | None = None,
        personality_prompt: str = "",
        goals: list[dict[str, object]] | None = None,
        capabilities: list[str] | None = None,
    ) -> "EmployeeIdentity":
        """Factory that assembles identity from employee data.

        Args:
            name: Employee display name.
            role: Role code (e.g. "sales_ae").
            role_description: Custom description; falls back to ROLE_DESCRIPTIONS.
            personality_prompt: Pre-rendered personality string from Personality.to_system_prompt().
            goals: List of dicts with at least "description" and optionally "priority".
            capabilities: List of capability names.
        """
        role_title = ROLE_TITLES.get(role, role.replace("_", " ").title())

        stripped_desc = role_description.strip() if role_description else ""
        effective_description = stripped_desc or ROLE_DESCRIPTIONS.get(
            role, f"You work as a {role_title}."
        )

        goals_summary = cls._format_goals(goals)

        # Strip "Personality: " prefix if already present (Personality.to_system_prompt()
        # includes it, but EmployeeIdentity.to_system_prompt() adds its own header).
        stripped_personality = personality_prompt.strip() if personality_prompt else ""
        effective_personality = stripped_personality or "balanced and professional"
        if effective_personality.startswith("Personality: "):
            effective_personality = effective_personality[len("Personality: ") :]

        return cls(
            name=name,
            role=role,
            role_title=role_title,
            role_description=effective_description,
            personality_prompt=effective_personality,
            goals_summary=goals_summary,
            capabilities=capabilities or [],
        )

    @staticmethod
    def _format_goals(goals: list[dict[str, object]] | None) -> str:
        """Format goal dicts into a bullet-list string for LLM context.

        Args:
            goals: List of dicts, each with ``"description"`` (str) and
                optionally ``"priority"`` (int, 1-10). ``None`` or empty
                list yields a fallback message.

        Returns:
            Newline-separated string of ``- [priority/10] description``
            lines, or ``"No specific goals set."`` when empty.
        """
        if not goals:
            return "No specific goals set."
        lines = []
        for g in goals:
            desc = g.get("description", "Unknown goal")
            priority = g.get("priority", "?")
            lines.append(f"- [{priority}/10] {desc}")
        return "\n".join(lines)


__all__ = [
    "ROLE_DESCRIPTIONS",
    "ROLE_TITLES",
    "EmployeeIdentity",
]
