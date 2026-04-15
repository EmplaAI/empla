"""
empla.api.v1.schemas.settings - Tenant Settings Schemas (PR #83)

Nested sections stored under the existing ``Tenant.settings`` JSONB column.
No new storage. Five sections:

- ``llm``            Model routing + provider allowlist
- ``cost``           Budgets + alert threshold + hard-stop (enforcement in PR #86)
- ``cycle``          BDI loop interval bounds + adaptive sensitivity
- ``trust``          READ-ONLY view of current taint rules + deny list
- ``notifications``  Inbox delivery preferences (read by PR #86's inbox feature)
- ``sales``          Quarterly target (kills ``hubspot/tools.py:150`` TODO)

Every write bumps ``settings.version`` so the frontend can warn on concurrent
edits. The full settings document round-trips as one Pydantic object.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------


class LLMSettings(BaseModel):
    """LLM model routing + provider allowlist."""

    primary_model: str = Field(
        default="claude-opus-4-6",
        max_length=100,
        description="Primary model for tool-calling and complex reasoning",
    )
    fallback_model: str = Field(
        default="claude-sonnet-4-6",
        max_length=100,
        description="Cheaper fallback for rate-limited or timed-out calls",
    )
    routing_rules: dict[str, str] = Field(
        default_factory=dict,
        description="TaskType → model override. Example: {'perception': 'claude-haiku-4-5'}.",
    )
    provider_allowlist: list[str] = Field(
        default_factory=lambda: ["anthropic", "openai", "vertex", "azure"],
        description="Permitted LLM providers for this tenant. Platform admin controlled.",
    )


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------


class CostSettings(BaseModel):
    """Daily/monthly budgets + alert threshold + hard-stop target.

    Note: hard-stop enforcement lands in PR #86 (bundled with the inbox so
    the user sees *why* the employee paused). The value is stored now so
    users can configure it early.
    """

    daily_budget_usd: float = Field(default=10.0, ge=0, le=1_000_000)
    monthly_budget_usd: float = Field(default=300.0, ge=0, le=10_000_000)
    alert_threshold_pct: int = Field(
        default=80, ge=1, le=99, description="Alert when spend reaches this % of budget"
    )
    hard_stop_budget_usd: float | None = Field(
        default=None,
        ge=0,
        le=1_000_000,
        description=(
            "Pause the employee when cumulative daily spend exceeds this. "
            "Enforcement deferred to PR #86."
        ),
    )

    @model_validator(mode="after")
    def _daily_le_monthly(self) -> CostSettings:
        if self.monthly_budget_usd < self.daily_budget_usd:
            raise ValueError("monthly_budget_usd must be >= daily_budget_usd")
        if (
            self.hard_stop_budget_usd is not None
            and self.hard_stop_budget_usd < self.daily_budget_usd
        ):
            raise ValueError("hard_stop_budget_usd must be >= daily_budget_usd")
        return self


# ---------------------------------------------------------------------------
# Cycle
# ---------------------------------------------------------------------------


class CycleSettings(BaseModel):
    """BDI loop cadence bounds + adaptive sensitivity."""

    min_interval_seconds: int = Field(default=30, ge=5, le=3600)
    max_interval_seconds: int = Field(default=1800, ge=30, le=86400)
    adaptive_sensitivity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="0 = fixed cadence; 1 = fully adaptive to opportunity signal.",
    )

    @model_validator(mode="after")
    def _min_le_max(self) -> CycleSettings:
        if self.max_interval_seconds < self.min_interval_seconds:
            raise ValueError("max_interval_seconds must be >= min_interval_seconds")
        return self


# ---------------------------------------------------------------------------
# Trust (read-only in PR #83)
# ---------------------------------------------------------------------------


class TrustRule(BaseModel):
    """One taint rule the runner currently enforces."""

    category: str
    pattern: str
    action: Literal["deny", "warn", "strip"]
    origin: Literal["platform", "tenant"]


class TrustSettings(BaseModel):
    """Read-only surface for current taint rules + global deny list.

    Editing taint rules is out of scope for PR #83 — the trust language
    isn't ready for user editing yet. The API will 403 any PUT against
    this section.
    """

    current_taint_rules: list[TrustRule] = Field(default_factory=list)
    global_deny_list: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class NotificationSettings(BaseModel):
    """Which inbox priorities the employee is allowed to post to.

    Read by PR #86's inbox feature. Stored now so the frontend toggle
    is durable.
    """

    inbox_urgent_enabled: bool = True
    inbox_normal_enabled: bool = True


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------


class SalesSettings(BaseModel):
    """Sales-specific knobs. Replaces ``hubspot/tools.py:150`` hardcoded 100k."""

    quarterly_target_usd: float = Field(
        default=100_000.0,
        ge=0,
        le=1_000_000_000,
        description="Per-quarter new-business target used by the HubSpot pipeline analysis.",
    )


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


class TenantSettings(BaseModel):
    """Full tenant settings document. Round-trips as a single Pydantic object."""

    version: int = Field(default=0, description="Monotonic counter bumped on every write.")
    llm: LLMSettings = Field(default_factory=LLMSettings)
    cost: CostSettings = Field(default_factory=CostSettings)
    cycle: CycleSettings = Field(default_factory=CycleSettings)
    trust: TrustSettings = Field(default_factory=TrustSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    sales: SalesSettings = Field(default_factory=SalesSettings)


class TenantSettingsUpdate(BaseModel):
    """PUT body. All editable sections are optional (trust is not included —
    edits are rejected at the API level)."""

    llm: LLMSettings | None = None
    cost: CostSettings | None = None
    cycle: CycleSettings | None = None
    notifications: NotificationSettings | None = None
    sales: SalesSettings | None = None


class TenantSettingsUpdateResponse(BaseModel):
    """Response from PUT. Reports the new version + how many runners were
    marked for restart so the UI can show a progress hint."""

    settings: TenantSettings
    restarting_employees: int = Field(
        description="Count of running employees marked status='restarting' for respawn."
    )
