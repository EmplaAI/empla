"""
Unit tests for PR #83: Tenant settings API.

Covers:
- GET returns defaults for a blank JSONB
- GET returns stored values when present
- PUT merges partial body, bumps version, triggers restart
- PUT validation rejects invalid cross-field combinations (daily > monthly,
  min_interval > max_interval, hard_stop < daily)
- Trust section is read-only (not in the update schema, so attempts to
  include it are silently dropped, but stored trust values round-trip)
- HubSpot _hubspot_init reads quarterly_target_usd from settings + fallback
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from empla.api.v1.endpoints import settings as settings_ep
from empla.api.v1.schemas.settings import (
    CostSettings,
    CycleSettings,
    LLMSettings,
    SalesSettings,
    TenantSettings,
    TenantSettingsUpdate,
)


def _auth(tenant_id: UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        role="admin",
    )


class _FakeTenant:
    def __init__(self, tenant_id: UUID, settings: dict | None = None):
        self.id = tenant_id
        self.deleted_at = None
        self.settings = settings or {}


def _db_with_tenant(tenant: _FakeTenant | None) -> AsyncMock:
    db = AsyncMock()
    result = Mock()
    result.scalar_one_or_none.return_value = tenant
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_defaults_are_reasonable(self):
        s = TenantSettings()
        assert s.version == 0
        assert s.llm.primary_model.startswith("claude-")
        assert s.cost.daily_budget_usd == 10.0
        assert s.cycle.min_interval_seconds == 30
        assert s.sales.quarterly_target_usd == 100_000.0

    def test_monthly_less_than_daily_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CostSettings(daily_budget_usd=50, monthly_budget_usd=25)

    def test_hard_stop_below_daily_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CostSettings(
                daily_budget_usd=50,
                monthly_budget_usd=500,
                hard_stop_budget_usd=25,
            )

    def test_hard_stop_optional(self):
        # None is allowed — the field is explicitly optional.
        c = CostSettings(daily_budget_usd=50, monthly_budget_usd=500)
        assert c.hard_stop_budget_usd is None

    def test_max_less_than_min_cycle_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CycleSettings(min_interval_seconds=100, max_interval_seconds=50)

    def test_update_schema_omits_trust(self):
        # PUT body schema doesn't expose the trust section — editing is 403
        # conceptually. Confirm the model's field list.
        assert "trust" not in TenantSettingsUpdate.model_fields

    def test_update_schema_rejects_unknown_keys(self):
        """A user POSTing ``trust`` or any unknown section must get 422, not
        a silent drop that lies to them."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TenantSettingsUpdate.model_validate({"trust": {"current_taint_rules": []}})
        with pytest.raises(ValidationError):
            TenantSettingsUpdate.model_validate({"spelt_wrong": {}})

    def test_cycle_min_floor_is_30_seconds(self):
        """5-second cycles would burn LLM budget too fast. Floor is 30s
        until cost hard-stop enforcement (PR #86)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CycleSettings(min_interval_seconds=5, max_interval_seconds=60)


# ---------------------------------------------------------------------------
# GET /settings
# ---------------------------------------------------------------------------


class TestGetSettings:
    @pytest.mark.asyncio
    async def test_returns_defaults_for_blank_tenant(self):
        auth = _auth()
        tenant = _FakeTenant(auth.tenant_id, settings={})
        db = _db_with_tenant(tenant)

        resp = await settings_ep.get_settings(db=db, auth=auth)

        assert resp.version == 0
        assert resp.llm.primary_model  # non-empty default
        assert resp.sales.quarterly_target_usd == 100_000.0

    @pytest.mark.asyncio
    async def test_returns_stored_values(self):
        auth = _auth()
        stored = TenantSettings(
            version=5,
            sales=SalesSettings(quarterly_target_usd=250_000.0),
            llm=LLMSettings(primary_model="claude-haiku-4-5"),
        ).model_dump(mode="json")
        tenant = _FakeTenant(auth.tenant_id, settings=stored)
        db = _db_with_tenant(tenant)

        resp = await settings_ep.get_settings(db=db, auth=auth)

        assert resp.version == 5
        assert resp.sales.quarterly_target_usd == 250_000.0
        assert resp.llm.primary_model == "claude-haiku-4-5"

    @pytest.mark.asyncio
    async def test_corrupt_jsonb_falls_back_to_defaults(self):
        auth = _auth()
        tenant = _FakeTenant(auth.tenant_id, settings={"llm": "not-a-dict"})
        db = _db_with_tenant(tenant)

        # Should NOT raise — corrupt settings must not take down the dashboard.
        resp = await settings_ep.get_settings(db=db, auth=auth)
        assert resp.version == 0  # default value from fallback path

    @pytest.mark.asyncio
    async def test_404_when_tenant_missing(self):
        auth = _auth()
        db = _db_with_tenant(None)

        with pytest.raises(HTTPException) as exc:
            await settings_ep.get_settings(db=db, auth=auth)
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# PUT /settings
# ---------------------------------------------------------------------------


class TestPutSettings:
    @pytest.mark.asyncio
    async def test_merges_partial_body_and_bumps_version(self, monkeypatch):
        auth = _auth()
        existing = TenantSettings(
            version=3,
            sales=SalesSettings(quarterly_target_usd=100_000.0),
        ).model_dump(mode="json")
        tenant = _FakeTenant(auth.tenant_id, settings=existing)
        db = _db_with_tenant(tenant)

        fake_manager = Mock()
        fake_manager.restart_all_for_tenant = AsyncMock(return_value=2)
        monkeypatch.setattr(settings_ep, "get_employee_manager", lambda: fake_manager)

        body = TenantSettingsUpdate(sales=SalesSettings(quarterly_target_usd=500_000.0))
        resp = await settings_ep.update_settings(db=db, auth=auth, body=body)

        assert resp.settings.version == 4  # bumped
        assert resp.settings.sales.quarterly_target_usd == 500_000.0
        # Unmodified sections keep their defaults / stored values.
        assert resp.settings.cost.daily_budget_usd == 10.0
        assert resp.restarting_employees == 2
        # Restart was triggered.
        fake_manager.restart_all_for_tenant.assert_awaited_once()
        # The JSONB blob was written.
        assert tenant.settings["version"] == 4
        assert tenant.settings["sales"]["quarterly_target_usd"] == 500_000.0

    @pytest.mark.asyncio
    async def test_restart_failure_does_not_fail_settings_write(self, monkeypatch):
        auth = _auth()
        tenant = _FakeTenant(auth.tenant_id, settings={})
        db = _db_with_tenant(tenant)

        fake_manager = Mock()
        fake_manager.restart_all_for_tenant = AsyncMock(
            side_effect=RuntimeError("manager unreachable")
        )
        monkeypatch.setattr(settings_ep, "get_employee_manager", lambda: fake_manager)

        body = TenantSettingsUpdate(
            cycle=CycleSettings(min_interval_seconds=60, max_interval_seconds=3600)
        )
        # Should NOT raise — settings save is the durable effect; restart is
        # best-effort. Runners pick up on their next manual restart.
        resp = await settings_ep.update_settings(db=db, auth=auth, body=body)

        assert resp.settings.cycle.min_interval_seconds == 60
        assert resp.restarting_employees == 0  # restart failed

    @pytest.mark.asyncio
    async def test_404_on_missing_tenant(self):
        auth = _auth()
        db = _db_with_tenant(None)

        with pytest.raises(HTTPException) as exc:
            await settings_ep.update_settings(db=db, auth=auth, body=TenantSettingsUpdate())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_expected_version_mismatch_returns_409(self, monkeypatch):
        """Concurrent save lost-update prevention."""
        auth = _auth()
        existing = TenantSettings(version=7).model_dump(mode="json")
        tenant = _FakeTenant(auth.tenant_id, settings=existing)
        db = _db_with_tenant(tenant)

        fake_manager = Mock()
        fake_manager.restart_all_for_tenant = AsyncMock(return_value=0)
        monkeypatch.setattr(settings_ep, "get_employee_manager", lambda: fake_manager)

        # Client thinks settings are at v5, but stored is v7 — reject.
        body = TenantSettingsUpdate(expected_version=5)
        with pytest.raises(HTTPException) as exc:
            await settings_ep.update_settings(db=db, auth=auth, body=body)
        assert exc.value.status_code == 409
        # Should NOT have triggered a restart on a rejected write.
        fake_manager.restart_all_for_tenant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_expected_version_match_succeeds(self, monkeypatch):
        auth = _auth()
        existing = TenantSettings(version=7).model_dump(mode="json")
        tenant = _FakeTenant(auth.tenant_id, settings=existing)
        db = _db_with_tenant(tenant)

        fake_manager = Mock()
        fake_manager.restart_all_for_tenant = AsyncMock(return_value=1)
        monkeypatch.setattr(settings_ep, "get_employee_manager", lambda: fake_manager)

        body = TenantSettingsUpdate(
            expected_version=7, sales=SalesSettings(quarterly_target_usd=250_000.0)
        )
        resp = await settings_ep.update_settings(db=db, auth=auth, body=body)
        assert resp.settings.version == 8
        assert resp.settings.sales.quarterly_target_usd == 250_000.0

    @pytest.mark.asyncio
    async def test_corrupt_jsonb_backed_up_on_put(self, monkeypatch):
        """First write after a corrupt read should snapshot the original
        under ``_corrupted_backup`` so operators can recover."""
        auth = _auth()
        # Schema-invalid: llm should be an object, not a string
        original = {"llm": "garbage", "version": 99}
        tenant = _FakeTenant(auth.tenant_id, settings=original)
        db = _db_with_tenant(tenant)

        fake_manager = Mock()
        fake_manager.restart_all_for_tenant = AsyncMock(return_value=0)
        monkeypatch.setattr(settings_ep, "get_employee_manager", lambda: fake_manager)

        await settings_ep.update_settings(db=db, auth=auth, body=TenantSettingsUpdate())
        # The overwrite carries the corrupt original under the backup key.
        assert tenant.settings["_corrupted_backup"] == original

    @pytest.mark.asyncio
    async def test_empty_body_still_bumps_version(self, monkeypatch):
        """An empty PUT body is a valid 'trigger a restart' signal on its own."""
        auth = _auth()
        tenant = _FakeTenant(auth.tenant_id, settings={"version": 1})
        db = _db_with_tenant(tenant)

        fake_manager = Mock()
        fake_manager.restart_all_for_tenant = AsyncMock(return_value=0)
        monkeypatch.setattr(settings_ep, "get_employee_manager", lambda: fake_manager)

        resp = await settings_ep.update_settings(db=db, auth=auth, body=TenantSettingsUpdate())
        assert resp.settings.version == 2


# ---------------------------------------------------------------------------
# HubSpot quarterly_target from settings
# ---------------------------------------------------------------------------


class TestHubSpotQuarterlyTargetFromSettings:
    """Replaces the hubspot/tools.py:150 hardcoded 100k."""

    @pytest.mark.asyncio
    async def test_init_reads_quarterly_target_from_tenant_settings(self):
        from empla.integrations.hubspot import tools as hs_tools

        tenant_settings = {
            "sales": {"quarterly_target_usd": 750_000.0},
        }
        await hs_tools._hubspot_init(
            access_token="test-token-1234567890",
            tenant_settings=tenant_settings,
        )
        try:
            assert hs_tools._quarterly_target == 750_000.0
        finally:
            await hs_tools._hubspot_shutdown()

    @pytest.mark.asyncio
    async def test_init_falls_back_when_setting_missing(self):
        from empla.integrations.hubspot import tools as hs_tools

        await hs_tools._hubspot_init(access_token="test-token-1234567890")
        try:
            assert hs_tools._quarterly_target == 100_000.0
        finally:
            await hs_tools._hubspot_shutdown()

    @pytest.mark.asyncio
    async def test_init_rejects_negative_target_and_falls_back(self):
        from empla.integrations.hubspot import tools as hs_tools

        await hs_tools._hubspot_init(
            access_token="test-token-1234567890",
            tenant_settings={"sales": {"quarterly_target_usd": -5.0}},
        )
        try:
            # Negative values are rejected by the isinstance+ge check
            assert hs_tools._quarterly_target == 100_000.0
        finally:
            await hs_tools._hubspot_shutdown()
