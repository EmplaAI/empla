"""Tests for LLM trust boundary validation.

The trust boundary is context-aware:
- Structured API data (CRM, calendar) → no restrictions beyond global deny
- Untrusted human content (email, messages) → taints context, activates role checks
"""

from uuid import UUID, uuid4

import pytest

from empla.core.tools.trust import (
    GLOBALLY_DENIED_TOOLS,
    TrustBoundary,
    TrustDecision,
)


@pytest.fixture
def employee_id() -> UUID:
    return uuid4()


@pytest.fixture
def boundary() -> TrustBoundary:
    return TrustBoundary()


class TestTrustDecision:
    def test_str_allow(self, employee_id: UUID) -> None:
        d = TrustDecision(
            allowed=True, tool_name="crm.create_deal", reason="OK", employee_id=employee_id
        )
        assert "ALLOW" in str(d)

    def test_str_deny(self, employee_id: UUID) -> None:
        d = TrustDecision(
            allowed=False, tool_name="admin.delete", reason="denied", employee_id=employee_id
        )
        assert "DENY" in str(d)

    def test_arguments_stored(self, employee_id: UUID) -> None:
        d = TrustDecision(
            allowed=True,
            tool_name="crm.create_deal",
            reason="OK",
            employee_id=employee_id,
            arguments={"name": "Acme"},
        )
        assert d.arguments == {"name": "Acme"}

    def test_tenant_id_stored(self, employee_id: UUID) -> None:
        tid = uuid4()
        d = TrustDecision(
            allowed=True, tool_name="crm.x", reason="OK", employee_id=employee_id, tenant_id=tid
        )
        assert d.tenant_id == tid


class TestGlobalDenyAlwaysOn:
    """Global deny list blocks destructive ops regardless of taint state."""

    def test_blocked_without_taint(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        """Destructive tools blocked even when context is clean."""
        for tool in GLOBALLY_DENIED_TOOLS:
            if not tool.endswith("."):
                decision = boundary.validate(tool, {}, employee_id)
                assert not decision.allowed, f"{tool} should be denied"

    def test_blocked_with_taint(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        """Destructive tools still blocked after taint."""
        boundary.validate("email.get_unread_emails", {}, employee_id)
        assert boundary.tainted
        decision = boundary.validate("hubspot.delete_all_deals", {}, employee_id)
        assert not decision.allowed

    def test_prefix_pattern_blocked(self, employee_id: UUID) -> None:
        """Prefix patterns (ending with .) block all matching tools."""
        boundary = TrustBoundary(globally_denied=frozenset({"dangerous."}))
        decision = boundary.validate("dangerous.action", {}, employee_id)
        assert not decision.allowed
        decision = boundary.validate("dangerous.other", {}, employee_id)
        assert not decision.allowed
        decision = boundary.validate("safe.action", {}, employee_id)
        assert decision.allowed


class TestStructuredDataPassesThrough:
    """CRM, calendar, and other structured-data tools need no trust check."""

    def test_crm_operations_always_allowed(
        self, boundary: TrustBoundary, employee_id: UUID
    ) -> None:
        safe_tools = [
            ("crm.get_pipeline_metrics", {}),
            ("crm.create_deal", {"name": "Acme", "value": 50000}),
            ("crm.get_deals", {"stage": "prospecting"}),
            ("crm.update_deal", {"id": "123", "stage": "negotiation"}),
            ("hubspot.get_contacts", {}),
            ("calendar.get_upcoming_events", {}),
            ("calendar.create_event", {"title": "Demo"}),
        ]
        for tool_name, args in safe_tools:
            decision = boundary.validate(tool_name, args, employee_id, employee_role="sales_ae")
            assert decision.allowed, f"{tool_name} should pass through"
        assert not boundary.tainted

    def test_role_restrictions_inactive_without_taint(
        self, boundary: TrustBoundary, employee_id: UUID
    ) -> None:
        decision = boundary.validate("admin.get_config", {}, employee_id, employee_role="sales_ae")
        assert decision.allowed


class TestTaintMechanism:
    """Reading untrusted content taints the context for the rest of the cycle."""

    def test_email_prefix_taints_context(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        """email. prefix matches any email tool name."""
        assert not boundary.tainted
        boundary.validate("email.get_unread_emails", {}, employee_id)
        assert boundary.tainted

    def test_gmail_prefix_taints_context(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        boundary.validate("gmail.get_email", {}, employee_id)
        assert boundary.tainted

    def test_slack_prefix_taints_context(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        boundary.validate("slack.read_messages", {}, employee_id)
        assert boundary.tainted

    def test_crm_does_not_taint(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        boundary.validate("crm.get_deals", {}, employee_id)
        assert not boundary.tainted

    def test_taint_persists_across_calls(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        boundary.validate("email.get_unread_emails", {}, employee_id)
        boundary.validate("crm.get_deals", {}, employee_id)
        assert boundary.tainted

    def test_reset_cycle_clears_taint(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        boundary.validate("email.get_unread_emails", {}, employee_id)
        assert boundary.tainted
        boundary.reset_cycle()
        assert not boundary.tainted

    def test_custom_high_risk_tools(self, employee_id: UUID) -> None:
        boundary = TrustBoundary(high_risk_tools=frozenset({"custom.risky_tool"}))
        boundary.validate("custom.risky_tool", {}, employee_id)
        assert boundary.tainted


class TestTaintActivatedRoleChecks:
    """After taint, role-specific restrictions kick in."""

    def test_sales_ae_blocked_admin_after_email(
        self, boundary: TrustBoundary, employee_id: UUID
    ) -> None:
        boundary.validate("email.get_unread_emails", {}, employee_id)
        decision = boundary.validate("admin.reset", {}, employee_id, employee_role="sales_ae")
        assert not decision.allowed
        assert "tainted" in decision.reason.lower()

    def test_sales_ae_blocked_system_after_email(
        self, boundary: TrustBoundary, employee_id: UUID
    ) -> None:
        boundary.validate("email.get_unread_emails", {}, employee_id)
        decision = boundary.validate("system.reboot", {}, employee_id, employee_role="sales_ae")
        assert not decision.allowed

    def test_sales_ae_crm_still_allowed_after_email(
        self, boundary: TrustBoundary, employee_id: UUID
    ) -> None:
        boundary.validate("email.get_unread_emails", {}, employee_id)
        decision = boundary.validate("crm.create_deal", {}, employee_id, employee_role="sales_ae")
        assert decision.allowed

    def test_no_role_no_role_restrictions(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        boundary.validate("email.get_unread_emails", {}, employee_id)
        decision = boundary.validate("admin.get_config", {}, employee_id, employee_role=None)
        assert decision.allowed


class TestRateLimit:
    def test_under_limit(self, employee_id: UUID) -> None:
        boundary = TrustBoundary(max_calls_per_cycle=3)
        for i in range(3):
            assert boundary.validate(f"tool.{i}", {}, employee_id).allowed

    def test_over_limit(self, employee_id: UUID) -> None:
        boundary = TrustBoundary(max_calls_per_cycle=3)
        for i in range(3):
            boundary.validate(f"tool.{i}", {}, employee_id)
        decision = boundary.validate("tool.4", {}, employee_id)
        assert not decision.allowed
        assert "limit exceeded" in decision.reason.lower()

    def test_denied_calls_count_toward_limit(self, employee_id: UUID) -> None:
        """Both allowed and denied attempts count toward the cycle limit."""
        boundary = TrustBoundary(max_calls_per_cycle=3)
        boundary.validate("tool.ok", {}, employee_id)  # allowed: count=1
        boundary.validate("hubspot.delete_all_deals", {}, employee_id)  # denied: count=2
        boundary.validate("tool.ok2", {}, employee_id)  # allowed: count=3
        decision = boundary.validate("tool.ok3", {}, employee_id)  # count=3, at limit
        assert not decision.allowed

    def test_reset_clears_counter(self, employee_id: UUID) -> None:
        boundary = TrustBoundary(max_calls_per_cycle=2)
        boundary.validate("tool.1", {}, employee_id)
        boundary.validate("tool.2", {}, employee_id)
        assert not boundary.validate("tool.3", {}, employee_id).allowed
        boundary.reset_cycle()
        assert boundary.validate("tool.3", {}, employee_id).allowed


class TestAuditLog:
    def test_records_all_decisions(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        boundary.validate("crm.get_deals", {}, employee_id)
        boundary.validate("hubspot.delete_all_deals", {}, employee_id)
        log = boundary.get_audit_log()
        assert len(log) == 2
        assert log[0].allowed
        assert not log[1].allowed

    def test_arguments_in_audit_log(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        boundary.validate("crm.create_deal", {"name": "Acme"}, employee_id)
        log = boundary.get_audit_log()
        assert log[0].arguments == {"name": "Acme"}

    def test_cycle_stats_include_taint(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        boundary.validate("email.get_unread_emails", {}, employee_id)
        stats = boundary.get_cycle_stats()
        assert stats["tainted"] is True
        assert stats["cycle_calls"] == 1

    def test_reset_cycle_clears_audit_log(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        boundary.validate("crm.get_deals", {}, employee_id)
        assert len(boundary.get_audit_log()) == 1
        boundary.reset_cycle()
        assert len(boundary.get_audit_log()) == 0


class TestPromptInjectionScenarios:
    """Realistic attack scenarios."""

    def test_email_says_delete_all(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        boundary.validate("email.get_unread_emails", {}, employee_id, employee_role="sales_ae")
        decision = boundary.validate(
            "hubspot.delete_all_deals", {}, employee_id, employee_role="sales_ae"
        )
        assert not decision.allowed

    def test_email_says_admin_access(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        boundary.validate("email.get_unread_emails", {}, employee_id, employee_role="sales_ae")
        decision = boundary.validate("admin.reset", {}, employee_id, employee_role="sales_ae")
        assert not decision.allowed

    def test_crm_data_cannot_trigger_injection(
        self, boundary: TrustBoundary, employee_id: UUID
    ) -> None:
        boundary.validate("crm.get_deals", {}, employee_id, employee_role="sales_ae")
        decision = boundary.validate("admin.get_config", {}, employee_id, employee_role="sales_ae")
        assert decision.allowed

    def test_safe_after_cycle_reset(self, boundary: TrustBoundary, employee_id: UUID) -> None:
        boundary.validate("email.get_unread_emails", {}, employee_id, employee_role="sales_ae")
        assert boundary.tainted
        boundary.reset_cycle()
        decision = boundary.validate("admin.get_config", {}, employee_id, employee_role="sales_ae")
        assert decision.allowed

    def test_runaway_loop_protection(self, employee_id: UUID) -> None:
        boundary = TrustBoundary(max_calls_per_cycle=10)
        for i in range(10):
            boundary.validate("crm.get_deals", {"page": i}, employee_id)
        decision = boundary.validate("crm.get_deals", {"page": 10}, employee_id)
        assert not decision.allowed
