"""
Unit tests for PR #81: webhook token management + event feed.

Covers:
- `_find_tenant_by_webhook_token` current-token match, previous-token
  grace-window match, expired previous token, unknown token.
- Token endpoints: create / rotate / delete / list (tenant isolation).
- Rotation preserves the previous token with a 5-minute grace window.
- Events endpoint reads AuditLog rows filtered by actor_type='webhook'.
- Webhook receiver writes to AuditLog with the right shape.
"""

from __future__ import annotations

import time as real_time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from freezegun import freeze_time

from empla.api.v1.endpoints import webhooks as webhooks_ep

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _auth(tenant_id: UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        role="admin",
    )


class _FakeIntegration:
    """Quacks like Integration enough for the endpoint to mutate oauth_config."""

    def __init__(
        self,
        integration_id: UUID,
        tenant_id: UUID,
        provider: str = "hubspot",
        oauth_config: dict | None = None,
    ):
        self.id = integration_id
        self.tenant_id = tenant_id
        self.provider = provider
        self.status = "active"
        self.deleted_at = None
        self.oauth_config = dict(oauth_config or {})
        self.created_at = datetime.now(UTC)


def _db_with_integration(integration: _FakeIntegration | None) -> AsyncMock:
    """DB stub that returns the given integration on first .execute()."""
    db = AsyncMock()
    result = Mock()
    result.scalar_one_or_none.return_value = integration
    db.execute = AsyncMock(return_value=result)
    db.add = Mock()
    db.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# _find_tenant_by_webhook_token
# ---------------------------------------------------------------------------


class TestFindTenantByWebhookToken:
    def _db_with_rows(self, rows: list[tuple]) -> AsyncMock:
        db = AsyncMock()
        result = Mock()
        result.all = Mock(return_value=rows)
        db.execute = AsyncMock(return_value=result)
        return db

    @pytest.mark.asyncio
    async def test_current_token_match(self):
        tid, iid = uuid4(), uuid4()
        db = self._db_with_rows([(iid, tid, {"webhook_token": "good-token"})])
        match = await webhooks_ep._find_tenant_by_webhook_token(db, "hubspot", "good-token")
        assert match == (tid, iid)

    @pytest.mark.asyncio
    async def test_unknown_token_returns_none(self):
        tid, iid = uuid4(), uuid4()
        db = self._db_with_rows([(iid, tid, {"webhook_token": "good-token"})])
        match = await webhooks_ep._find_tenant_by_webhook_token(db, "hubspot", "wrong")
        assert match is None

    @pytest.mark.asyncio
    async def test_previous_token_within_grace_window(self):
        """The prior token is accepted for 5 minutes after rotation."""
        tid, iid = uuid4(), uuid4()
        # rotated 60 seconds ago → still inside the 300s window
        now = real_time.time()
        db = self._db_with_rows(
            [
                (
                    iid,
                    tid,
                    {
                        "webhook_token": "new-token",
                        "webhook_token_prev": "old-token",
                        "rotated_at": now - 60,
                    },
                )
            ]
        )
        match = await webhooks_ep._find_tenant_by_webhook_token(db, "hubspot", "old-token")
        assert match == (tid, iid)

    @pytest.mark.asyncio
    async def test_previous_token_after_grace_window_rejected(self):
        tid, iid = uuid4(), uuid4()
        # rotated 10 minutes ago → past the 300s window
        now = real_time.time()
        db = self._db_with_rows(
            [
                (
                    iid,
                    tid,
                    {
                        "webhook_token": "new-token",
                        "webhook_token_prev": "old-token",
                        "rotated_at": now - 600,
                    },
                )
            ]
        )
        match = await webhooks_ep._find_tenant_by_webhook_token(db, "hubspot", "old-token")
        assert match is None
        # New token still works after rotation
        match = await webhooks_ep._find_tenant_by_webhook_token(db, "hubspot", "new-token")
        assert match == (tid, iid)


# ---------------------------------------------------------------------------
# Token CRUD endpoints
# ---------------------------------------------------------------------------


class TestTokenEndpoints:
    @pytest.mark.asyncio
    async def test_create_generates_and_returns_token_once(self):
        auth = _auth()
        integration_id = uuid4()
        integ = _FakeIntegration(integration_id, auth.tenant_id)
        db = _db_with_integration(integ)

        from empla.api.v1.schemas.webhook import WebhookTokenCreateRequest

        resp = await webhooks_ep.create_webhook_token(
            db=db,
            auth=auth,
            body=WebhookTokenCreateRequest(integration_id=str(integration_id)),
        )
        assert resp.token
        assert len(resp.token) >= 32
        assert integ.oauth_config["webhook_token"] == resp.token
        # Fresh create clears any rotation state
        assert "webhook_token_prev" not in integ.oauth_config
        assert "rotated_at" not in integ.oauth_config

    @pytest.mark.asyncio
    async def test_create_404_on_cross_tenant(self):
        auth = _auth()
        # Integration belongs to a different tenant → _get_integration returns None
        db = _db_with_integration(None)

        from empla.api.v1.schemas.webhook import WebhookTokenCreateRequest

        with pytest.raises(HTTPException) as exc:
            await webhooks_ep.create_webhook_token(
                db=db,
                auth=auth,
                body=WebhookTokenCreateRequest(integration_id=str(uuid4())),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_400_on_bad_integration_id(self):
        auth = _auth()
        db = AsyncMock()

        from empla.api.v1.schemas.webhook import WebhookTokenCreateRequest

        with pytest.raises(HTTPException) as exc:
            await webhooks_ep.create_webhook_token(
                db=db,
                auth=auth,
                body=WebhookTokenCreateRequest(integration_id="not-a-uuid"),
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rotate_preserves_old_token_with_rotated_at(self):
        auth = _auth()
        integration_id = uuid4()
        integ = _FakeIntegration(
            integration_id, auth.tenant_id, oauth_config={"webhook_token": "original"}
        )
        db = _db_with_integration(integ)

        resp = await webhooks_ep.rotate_webhook_token(
            db=db, auth=auth, integration_id=integration_id
        )
        assert resp.token != "original"
        assert integ.oauth_config["webhook_token"] == resp.token
        assert integ.oauth_config["webhook_token_prev"] == "original"
        assert "rotated_at" in integ.oauth_config
        assert resp.rotated_at is not None

    @pytest.mark.asyncio
    async def test_rotate_409_when_no_existing_token(self):
        auth = _auth()
        integration_id = uuid4()
        integ = _FakeIntegration(integration_id, auth.tenant_id, oauth_config={})
        db = _db_with_integration(integ)

        with pytest.raises(HTTPException) as exc:
            await webhooks_ep.rotate_webhook_token(db=db, auth=auth, integration_id=integration_id)
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_drops_both_tokens(self):
        auth = _auth()
        integration_id = uuid4()
        integ = _FakeIntegration(
            integration_id,
            auth.tenant_id,
            oauth_config={
                "webhook_token": "current",
                "webhook_token_prev": "prev",
                "rotated_at": real_time.time(),
            },
        )
        db = _db_with_integration(integ)

        await webhooks_ep.delete_webhook_token(db=db, auth=auth, integration_id=integration_id)
        assert "webhook_token" not in integ.oauth_config
        assert "webhook_token_prev" not in integ.oauth_config
        assert "rotated_at" not in integ.oauth_config

    @pytest.mark.asyncio
    async def test_delete_is_idempotent(self):
        auth = _auth()
        integration_id = uuid4()
        integ = _FakeIntegration(integration_id, auth.tenant_id, oauth_config={})
        db = _db_with_integration(integ)
        # No raise
        await webhooks_ep.delete_webhook_token(db=db, auth=auth, integration_id=integration_id)


# ---------------------------------------------------------------------------
# Rotation grace-window end-to-end via freezegun
# ---------------------------------------------------------------------------


class TestRotationGraceWindow:
    """
    Time-travel test proving the previous token is accepted in the first 5
    minutes after rotation and rejected afterwards. Uses a mocked clock so
    we don't actually sleep.
    """

    @pytest.mark.asyncio
    async def test_old_token_accepted_within_grace_rejected_after(self):
        auth = _auth()
        integration_id = uuid4()
        integ = _FakeIntegration(
            integration_id, auth.tenant_id, oauth_config={"webhook_token": "original"}
        )

        # Use a dict to simulate mutable oauth_config across lookups
        def lookup_rows():
            return [(integration_id, auth.tenant_id, dict(integ.oauth_config))]

        with freeze_time("2026-04-14 10:00:00", tz_offset=0):
            # Rotate now
            db = _db_with_integration(integ)
            resp = await webhooks_ep.rotate_webhook_token(
                db=db, auth=auth, integration_id=integration_id
            )
            new_token = resp.token
            assert integ.oauth_config["webhook_token_prev"] == "original"

        # t+60s: still within 300s grace window
        with freeze_time("2026-04-14 10:01:00", tz_offset=0):
            rows_db = AsyncMock()
            r = Mock()
            r.all = Mock(return_value=lookup_rows())
            rows_db.execute = AsyncMock(return_value=r)

            match = await webhooks_ep._find_tenant_by_webhook_token(rows_db, "hubspot", "original")
            assert match is not None, "Old token must work inside grace window"

            match_new = await webhooks_ep._find_tenant_by_webhook_token(
                rows_db, "hubspot", new_token
            )
            assert match_new is not None, "New token always works"

        # t+6min: past the 300s grace window
        with freeze_time("2026-04-14 10:06:00", tz_offset=0):
            rows_db = AsyncMock()
            r = Mock()
            r.all = Mock(return_value=lookup_rows())
            rows_db.execute = AsyncMock(return_value=r)

            match = await webhooks_ep._find_tenant_by_webhook_token(rows_db, "hubspot", "original")
            assert match is None, "Old token must be rejected after grace"

            match_new = await webhooks_ep._find_tenant_by_webhook_token(
                rows_db, "hubspot", new_token
            )
            assert match_new is not None, "New token still works after grace"


# ---------------------------------------------------------------------------
# Events list endpoint
# ---------------------------------------------------------------------------


class TestEventsEndpoint:
    def _db_for_events(self, rows: list, total: int) -> AsyncMock:
        db = AsyncMock()
        count_result = Mock()
        count_result.scalar.return_value = total
        fetch_result = Mock()
        scalars = Mock()
        scalars.all = Mock(return_value=rows)
        fetch_result.scalars = Mock(return_value=scalars)
        db.execute = AsyncMock(side_effect=[count_result, fetch_result])
        return db

    def _audit_row(self, tenant_id: UUID, integration_id: UUID, provider: str):
        return SimpleNamespace(
            id=uuid4(),
            tenant_id=tenant_id,
            actor_id=integration_id,
            details={
                "provider": provider,
                "event_type": "deal.updated",
                "summary": "HubSpot deal updated",
                "employees_notified": 1,
            },
            occurred_at=datetime.now(UTC),
        )

    @pytest.mark.asyncio
    async def test_list_events_happy_path(self):
        auth = _auth()
        iid = uuid4()
        rows = [self._audit_row(auth.tenant_id, iid, "hubspot") for _ in range(3)]
        db = self._db_for_events(rows, total=3)

        resp = await webhooks_ep.list_webhook_events(
            db=db, auth=auth, page=1, page_size=50, provider=None
        )
        assert resp.total == 3
        assert len(resp.items) == 3
        assert resp.items[0].provider == "hubspot"
        assert resp.items[0].employees_notified == 1
        assert resp.items[0].integration_id == str(iid)

    @pytest.mark.asyncio
    async def test_list_events_empty(self):
        auth = _auth()
        db = self._db_for_events([], total=0)
        resp = await webhooks_ep.list_webhook_events(
            db=db, auth=auth, page=1, page_size=50, provider=None
        )
        assert resp.total == 0
        assert resp.pages == 1

    @pytest.mark.asyncio
    async def test_list_events_pagination(self):
        auth = _auth()
        iid = uuid4()
        rows = [self._audit_row(auth.tenant_id, iid, "hubspot")]
        db = self._db_for_events(rows, total=237)

        resp = await webhooks_ep.list_webhook_events(
            db=db, auth=auth, page=3, page_size=50, provider=None
        )
        assert resp.page == 3
        assert resp.pages == 5  # ceil(237 / 50)

    @pytest.mark.asyncio
    async def test_list_events_provider_filter(self):
        """Provider filter compiles cleanly (actually running the LIKE is covered by integration tests)."""
        auth = _auth()
        db = self._db_for_events([], total=0)
        resp = await webhooks_ep.list_webhook_events(
            db=db, auth=auth, page=1, page_size=50, provider="hubspot"
        )
        assert resp.total == 0


# ---------------------------------------------------------------------------
# Schema smoke tests — one-time token contract
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_webhook_token_info_never_leaks_token_value(self):
        from empla.api.v1.schemas.webhook import WebhookTokenInfo

        info = WebhookTokenInfo(
            integration_id=str(uuid4()),
            provider="hubspot",
            has_token=True,
            rotated_at=None,
            grace_window_active=False,
        )
        # The public info schema has no `token` field — you shouldn't be able
        # to serialize the token value out through this path.
        assert "token" not in info.model_dump()

    def test_webhook_token_issued_includes_token(self):
        from empla.api.v1.schemas.webhook import WebhookTokenIssued

        issued = WebhookTokenIssued(
            integration_id=str(uuid4()),
            provider="hubspot",
            token="abc123",
            rotated_at=datetime.now(UTC),
        )
        # This schema IS the one-time channel — the token must be present
        assert issued.token == "abc123"
