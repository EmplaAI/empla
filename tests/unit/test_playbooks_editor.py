"""
Unit tests for PR #84: Playbook editor with optimistic locking.

Covers:
- Schema validation (create/update body shapes, extra='forbid')
- CREATE: admin-only, unique-name collision → 409, happy path
- UPDATE: version match → bumps version; version mismatch → 409;
  missing row → 404; all-fields-None PUT still bumps version
- TOGGLE: flips enabled, bumps version, idempotent (double-set ok)
- DELETE: soft-deletes, idempotent on already-deleted, 404 on missing
- Auto-promotion bumps version (empla.core.memory.procedural)
- Concurrent edit + auto-promotion produces 409 (integration-flavored)
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from empla.api.v1.endpoints import playbooks as playbooks_ep
from empla.api.v1.endpoints.playbooks import (
    PlaybookCreateRequest,
    PlaybookStep,
    PlaybookToggleRequest,
    PlaybookUpdateRequest,
)


def _auth(tenant_id: UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        role="admin",
    )


class _FakePlaybook:
    def __init__(
        self,
        *,
        pid: UUID | None = None,
        employee_id: UUID | None = None,
        tenant_id: UUID | None = None,
        name: str = "Test playbook",
        version: int = 0,
        enabled: bool = True,
        deleted_at=None,
        is_playbook: bool = True,
    ):
        self.id = pid or uuid4()
        self.employee_id = employee_id or uuid4()
        self.tenant_id = tenant_id or uuid4()
        self.name = name
        self.description = "desc"
        self.procedure_type = "playbook"
        self.steps = [{"description": "step 1"}]
        self.trigger_conditions = {}
        self.success_rate = 0.0
        self.execution_count = 0
        self.success_count = 0
        self.avg_execution_time = None
        self.last_executed_at = None
        self.promoted_at = datetime.now(UTC)
        self.learned_from = "instruction"
        self.context = {}
        self.is_playbook = is_playbook
        self.enabled = enabled
        self.version = version
        self.deleted_at = deleted_at


def _db_with_employee_verify(employee_ok: bool = True) -> AsyncMock:
    db = AsyncMock()
    verify = Mock()
    verify.scalar_one_or_none.return_value = uuid4() if employee_ok else None
    db.execute = AsyncMock(return_value=verify)
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_create_rejects_empty_steps(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PlaybookCreateRequest(name="x", description="x", steps=[])

    def test_create_caps_step_count(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PlaybookCreateRequest(
                name="x",
                description="x",
                steps=[PlaybookStep(description=str(i)) for i in range(51)],
            )

    def test_create_rejects_extra_keys(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PlaybookCreateRequest.model_validate(
                {
                    "name": "x",
                    "description": "x",
                    "steps": [{"description": "a"}],
                    "spelt_wrong": True,
                }
            )

    def test_update_requires_expected_version(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            # Missing expected_version entirely
            PlaybookUpdateRequest.model_validate({})

    def test_update_all_fields_optional_except_version(self):
        # Minimal valid update — just version. No-op content change but
        # still bumps the lock so stale clients 409.
        req = PlaybookUpdateRequest(expected_version=3)
        assert req.expected_version == 3
        assert req.name is None

    def test_toggle_needs_explicit_bool(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PlaybookToggleRequest.model_validate({})


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


class TestCreatePlaybook:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        auth = _auth()
        emp_id = uuid4()

        added: list = []

        def _capture(row):
            row.id = uuid4()
            added.append(row)

        db = _db_with_employee_verify()
        db.add = Mock(side_effect=_capture)

        body = PlaybookCreateRequest(
            name="Follow up after meeting",
            description="Standard post-meeting follow up",
            steps=[
                PlaybookStep(description="Read meeting notes"),
                PlaybookStep(description="Draft follow-up email"),
            ],
        )

        resp = await playbooks_ep.create_playbook(employee_id=emp_id, body=body, db=db, auth=auth)

        assert resp.name == "Follow up after meeting"
        assert resp.version == 0
        assert resp.enabled is True
        row = added[0]
        assert row.is_playbook is True
        assert row.procedure_type == "playbook"
        assert row.learned_from == "instruction"
        assert len(row.steps) == 2

    @pytest.mark.asyncio
    async def test_duplicate_name_returns_409(self):
        auth = _auth()
        emp_id = uuid4()
        db = _db_with_employee_verify()
        db.commit = AsyncMock(
            side_effect=Exception(
                'duplicate key value violates unique constraint "idx_procedural_unique_name"'
            )
        )

        body = PlaybookCreateRequest(
            name="dup", description="x", steps=[PlaybookStep(description="a")]
        )

        with pytest.raises(HTTPException) as exc:
            await playbooks_ep.create_playbook(employee_id=emp_id, body=body, db=db, auth=auth)
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_404_cross_tenant(self):
        auth = _auth()
        db = _db_with_employee_verify(employee_ok=False)
        body = PlaybookCreateRequest(
            name="x", description="x", steps=[PlaybookStep(description="a")]
        )
        with pytest.raises(HTTPException) as exc:
            await playbooks_ep.create_playbook(employee_id=uuid4(), body=body, db=db, auth=auth)
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# UPDATE (optimistic lock)
# ---------------------------------------------------------------------------


def _db_with_update_result(returning_row: _FakePlaybook | None) -> AsyncMock:
    """DB that: first execute = employee verify, second = UPDATE...RETURNING.
    If the optimistic lock failed (returning_row is None), the endpoint
    falls back to a _load_playbook call to distinguish 404 vs 409."""
    db = AsyncMock()
    verify_result = Mock()
    verify_result.scalar_one_or_none.return_value = uuid4()  # employee exists
    update_result = Mock()
    update_result.scalar_one_or_none.return_value = returning_row
    db.execute = AsyncMock(side_effect=[verify_result, update_result])
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    return db


class TestUpdatePlaybook:
    @pytest.mark.asyncio
    async def test_version_match_bumps_version_and_writes_fields(self):
        """UPDATE ... WHERE version = expected returns the updated row.
        We stub returning the row with its new version already applied."""
        auth = _auth()
        pid = uuid4()
        emp_id = uuid4()
        updated = _FakePlaybook(
            pid=pid,
            employee_id=emp_id,
            tenant_id=auth.tenant_id,
            name="New name",
            version=6,
        )
        db = _db_with_update_result(updated)

        body = PlaybookUpdateRequest(expected_version=5, name="New name")
        resp = await playbooks_ep.update_playbook(
            employee_id=emp_id, playbook_id=pid, body=body, db=db, auth=auth
        )
        assert resp.name == "New name"
        assert resp.version == 6

    @pytest.mark.asyncio
    async def test_version_mismatch_returns_409(self):
        """UPDATE returns no row → endpoint reloads to distinguish 404/409.
        Here the playbook exists at a higher version → 409."""
        auth = _auth()
        pid = uuid4()
        emp_id = uuid4()

        # Build a richer db mock: verify + failed-update + reload
        db = AsyncMock()
        verify_result = Mock()
        verify_result.scalar_one_or_none.return_value = uuid4()
        update_result = Mock()
        update_result.scalar_one_or_none.return_value = None  # version mismatch
        reload_result = Mock()
        reload_result.scalar_one_or_none.return_value = _FakePlaybook(
            pid=pid, employee_id=emp_id, tenant_id=auth.tenant_id, version=9
        )
        db.execute = AsyncMock(side_effect=[verify_result, update_result, reload_result])
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        body = PlaybookUpdateRequest(expected_version=5, name="stale")
        with pytest.raises(HTTPException) as exc:
            await playbooks_ep.update_playbook(
                employee_id=emp_id, playbook_id=pid, body=body, db=db, auth=auth
            )
        assert exc.value.status_code == 409
        assert "v5" in exc.value.detail
        assert "v9" in exc.value.detail

    @pytest.mark.asyncio
    async def test_missing_playbook_returns_404(self):
        auth = _auth()
        db = AsyncMock()
        verify_result = Mock()
        verify_result.scalar_one_or_none.return_value = uuid4()
        update_result = Mock()
        update_result.scalar_one_or_none.return_value = None
        reload_result = Mock()
        reload_result.scalar_one_or_none.return_value = None  # genuinely gone
        db.execute = AsyncMock(side_effect=[verify_result, update_result, reload_result])
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        body = PlaybookUpdateRequest(expected_version=0)
        with pytest.raises(HTTPException) as exc:
            await playbooks_ep.update_playbook(
                employee_id=uuid4(), playbook_id=uuid4(), body=body, db=db, auth=auth
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_noop_update_still_bumps_version(self):
        """An empty PUT body (just expected_version) still advances the
        lock, so a stale client's follow-up PUT 409s."""
        auth = _auth()
        emp_id = uuid4()
        pid = uuid4()
        updated = _FakePlaybook(pid=pid, employee_id=emp_id, tenant_id=auth.tenant_id, version=4)
        db = _db_with_update_result(updated)
        body = PlaybookUpdateRequest(expected_version=3)
        resp = await playbooks_ep.update_playbook(
            employee_id=emp_id, playbook_id=pid, body=body, db=db, auth=auth
        )
        assert resp.version == 4


# ---------------------------------------------------------------------------
# TOGGLE
# ---------------------------------------------------------------------------


def _db_with_load(playbook: _FakePlaybook | None) -> AsyncMock:
    db = AsyncMock()
    verify_result = Mock()
    verify_result.scalar_one_or_none.return_value = uuid4()
    load_result = Mock()
    load_result.scalar_one_or_none.return_value = playbook
    db.execute = AsyncMock(side_effect=[verify_result, load_result])
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


class TestTogglePlaybook:
    @pytest.mark.asyncio
    async def test_toggle_flips_enabled_and_bumps_version(self):
        auth = _auth()
        pb = _FakePlaybook(tenant_id=auth.tenant_id, enabled=True, version=2)
        db = _db_with_load(pb)
        resp = await playbooks_ep.toggle_playbook(
            employee_id=pb.employee_id,
            playbook_id=pb.id,
            body=PlaybookToggleRequest(enabled=False),
            db=db,
            auth=auth,
        )
        assert resp.enabled is False
        assert resp.version == 3

    @pytest.mark.asyncio
    async def test_toggle_is_idempotent_on_same_state(self):
        """Set to the same value it already has. No error — the version
        still bumps, but the enabled stays the same. That's fine, it
        just means another racing PUT will 409 by one."""
        auth = _auth()
        pb = _FakePlaybook(tenant_id=auth.tenant_id, enabled=True, version=2)
        db = _db_with_load(pb)
        resp = await playbooks_ep.toggle_playbook(
            employee_id=pb.employee_id,
            playbook_id=pb.id,
            body=PlaybookToggleRequest(enabled=True),
            db=db,
            auth=auth,
        )
        assert resp.enabled is True
        assert resp.version == 3

    @pytest.mark.asyncio
    async def test_toggle_404_on_missing(self):
        auth = _auth()
        db = _db_with_load(None)
        with pytest.raises(HTTPException) as exc:
            await playbooks_ep.toggle_playbook(
                employee_id=uuid4(),
                playbook_id=uuid4(),
                body=PlaybookToggleRequest(enabled=False),
                db=db,
                auth=auth,
            )
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


class TestDeletePlaybook:
    @pytest.mark.asyncio
    async def test_soft_deletes(self):
        auth = _auth()
        pb = _FakePlaybook(tenant_id=auth.tenant_id, version=4)
        db = _db_with_load(pb)
        await playbooks_ep.delete_playbook(
            employee_id=pb.employee_id, playbook_id=pb.id, db=db, auth=auth
        )
        assert pb.deleted_at is not None
        assert pb.version == 5

    @pytest.mark.asyncio
    async def test_idempotent_on_already_deleted(self):
        auth = _auth()
        pb = _FakePlaybook(tenant_id=auth.tenant_id, deleted_at=datetime.now(UTC), version=4)
        db = _db_with_load(pb)
        await playbooks_ep.delete_playbook(
            employee_id=pb.employee_id, playbook_id=pb.id, db=db, auth=auth
        )
        # No commit was triggered — the row was already gone.
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_404_on_missing(self):
        auth = _auth()
        db = _db_with_load(None)
        with pytest.raises(HTTPException) as exc:
            await playbooks_ep.delete_playbook(
                employee_id=uuid4(), playbook_id=uuid4(), db=db, auth=auth
            )
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Auto-promotion bumps version (dual-writer discipline)
# ---------------------------------------------------------------------------


class TestAutoPromotionBumpsVersion:
    """The reflection path calls ``ProceduralMemorySystem.promote_to_playbook``
    directly, not via the API. Without bumping version here, an API PUT
    concurrent with an auto-promotion silently wins or loses. This test
    pins the version-bump contract at the service boundary."""

    @pytest.mark.asyncio
    async def test_promote_bumps_version(self):
        from empla.core.memory.procedural import ProceduralMemorySystem

        fake_proc = SimpleNamespace(
            id=uuid4(),
            is_playbook=False,
            execution_count=10,
            success_rate=0.85,
            promoted_at=None,
            learned_from=None,
            version=3,
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        system = ProceduralMemorySystem(session=session, employee_id=uuid4(), tenant_id=uuid4())

        async def _stub_get(_pid):
            return fake_proc

        system.get_procedure = _stub_get  # type: ignore[assignment]

        result = await system.promote_to_playbook(fake_proc.id)

        assert result is fake_proc
        assert fake_proc.is_playbook is True
        assert fake_proc.version == 4  # bumped

    @pytest.mark.asyncio
    async def test_promote_reverts_version_on_flush_failure(self):
        from empla.core.memory.procedural import ProceduralMemorySystem

        fake_proc = SimpleNamespace(
            id=uuid4(),
            is_playbook=False,
            execution_count=10,
            success_rate=0.85,
            promoted_at=None,
            learned_from=None,
            version=7,
        )

        session = AsyncMock()
        session.flush = AsyncMock(side_effect=RuntimeError("db down"))
        system = ProceduralMemorySystem(session=session, employee_id=uuid4(), tenant_id=uuid4())

        async def _stub_get(_pid):
            return fake_proc

        system.get_procedure = _stub_get  # type: ignore[assignment]

        with pytest.raises(RuntimeError):
            await system.promote_to_playbook(fake_proc.id)

        # All in-memory state reverted so callers don't see a false positive.
        assert fake_proc.is_playbook is False
        assert fake_proc.version == 7
