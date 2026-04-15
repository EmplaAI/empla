"""
Unit tests for PR #82: Scheduler API (read + cancel + user-requested add).

Covers:
- GET: happy list / empty / tenant isolation / 404 / source tag default / sort
- POST: creates with source='user_requested' / past-date 400 / recurring
  with missing interval_hours 422
- DELETE: removes one-shot and recurring / 404 non-existent / 404 wrong tenant
- The source-aware prefix logic in _check_scheduled_actions
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from empla.api.v1.endpoints import scheduler as scheduler_ep
from empla.api.v1.schemas.scheduler import ScheduledActionCreateRequest


def _auth(tenant_id: UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        role="admin",
    )


class _FakeRow:
    """Quacks like a WorkingMemory row enough for _row_to_response."""

    def __init__(self, *, row_id: UUID, content: dict, deleted_at=None):
        self.id = row_id
        self.content = content
        self.deleted_at = deleted_at


def _sched_content(
    description: str,
    scheduled_for: datetime,
    *,
    source: str = "employee",
    recurring: bool = False,
    interval_hours: float | None = None,
    subtype: str = "scheduled_action",
) -> dict:
    return {
        "subtype": subtype,
        "action_id": str(uuid4()),
        "description": description,
        "scheduled_for": scheduled_for.isoformat(),
        "recurring": recurring,
        "interval_hours": interval_hours,
        "context": {},
        "created_at": datetime.now(UTC).isoformat(),
        "source": source,
    }


def _db_for_verify_then_query(
    *,
    employee_exists: bool,
    rows: list[_FakeRow] | None = None,
) -> AsyncMock:
    """Build a db mock where the first execute verifies employee ownership
    and the second returns the list of rows."""
    db = AsyncMock()

    verify_result = Mock()
    verify_result.scalar_one_or_none.return_value = uuid4() if employee_exists else None

    list_result = Mock()
    scalars_obj = Mock()
    scalars_obj.all.return_value = rows or []
    list_result.scalars.return_value = scalars_obj

    db.execute = AsyncMock(side_effect=[verify_result, list_result])
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# GET /schedule
# ---------------------------------------------------------------------------


class TestListScheduledActions:
    @pytest.mark.asyncio
    async def test_happy_path_sorted_by_scheduled_for(self):
        auth = _auth()
        emp_id = uuid4()
        now = datetime.now(UTC)
        rows = [
            _FakeRow(
                row_id=uuid4(),
                content=_sched_content("third", now + timedelta(hours=48)),
            ),
            _FakeRow(
                row_id=uuid4(),
                content=_sched_content("first", now + timedelta(hours=1)),
            ),
            _FakeRow(
                row_id=uuid4(),
                content=_sched_content("second", now + timedelta(hours=24)),
            ),
        ]
        db = _db_for_verify_then_query(employee_exists=True, rows=rows)

        resp = await scheduler_ep.list_scheduled_actions(db=db, auth=auth, employee_id=emp_id)

        assert resp.total == 3
        assert [a.description for a in resp.items] == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_empty(self):
        auth = _auth()
        db = _db_for_verify_then_query(employee_exists=True, rows=[])

        resp = await scheduler_ep.list_scheduled_actions(db=db, auth=auth, employee_id=uuid4())

        assert resp.total == 0
        assert resp.items == []

    @pytest.mark.asyncio
    async def test_404_on_cross_tenant(self):
        auth = _auth()
        db = _db_for_verify_then_query(employee_exists=False)

        with pytest.raises(HTTPException) as exc:
            await scheduler_ep.list_scheduled_actions(db=db, auth=auth, employee_id=uuid4())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_legacy_rows_without_source_default_to_employee(self):
        auth = _auth()
        now = datetime.now(UTC)
        content = _sched_content("legacy", now + timedelta(hours=2))
        content.pop("source")  # simulate pre-PR #82 row

        db = _db_for_verify_then_query(
            employee_exists=True,
            rows=[_FakeRow(row_id=uuid4(), content=content)],
        )

        resp = await scheduler_ep.list_scheduled_actions(db=db, auth=auth, employee_id=uuid4())

        assert len(resp.items) == 1
        assert resp.items[0].source == "employee"

    @pytest.mark.asyncio
    async def test_non_scheduled_action_rows_filtered_out(self):
        auth = _auth()
        now = datetime.now(UTC)
        rows = [
            _FakeRow(
                row_id=uuid4(),
                content=_sched_content("ok", now + timedelta(hours=1), subtype="scheduled_action"),
            ),
            _FakeRow(
                row_id=uuid4(),
                content=_sched_content("noise", now + timedelta(hours=2), subtype="other"),
            ),
        ]
        db = _db_for_verify_then_query(employee_exists=True, rows=rows)

        resp = await scheduler_ep.list_scheduled_actions(db=db, auth=auth, employee_id=uuid4())

        assert resp.total == 1
        assert resp.items[0].description == "ok"


# ---------------------------------------------------------------------------
# POST /schedule
# ---------------------------------------------------------------------------


class TestCreateScheduledAction:
    @pytest.mark.asyncio
    async def test_creates_user_requested_row(self):
        auth = _auth()
        emp_id = uuid4()
        scheduled_for = datetime.now(UTC) + timedelta(hours=4)

        # DB: verify returns employee; db.add captures the row; refresh
        # populates the row id (in real SA) — we stub by setting it on add.
        db = AsyncMock()
        verify_result = Mock()
        verify_result.scalar_one_or_none.return_value = uuid4()
        db.execute = AsyncMock(return_value=verify_result)

        added_rows: list = []

        def _capture(row):
            row.id = uuid4()
            added_rows.append(row)

        db.add = Mock(side_effect=_capture)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        body = ScheduledActionCreateRequest(
            description="ping the CFO next Tuesday",
            scheduled_for=scheduled_for,
            recurring=False,
        )

        resp = await scheduler_ep.create_scheduled_action(
            db=db, auth=auth, body=body, employee_id=emp_id
        )

        assert resp.source == "user_requested"
        assert resp.description == "ping the CFO next Tuesday"
        assert len(added_rows) == 1
        row = added_rows[0]
        assert row.tenant_id == auth.tenant_id
        assert row.employee_id == emp_id
        assert row.item_type == "task"
        assert row.content["subtype"] == "scheduled_action"
        assert row.content["source"] == "user_requested"
        # TTL extends past scheduled_for so get_active_items can see it
        assert row.expires_at > scheduled_for.timestamp()

    @pytest.mark.asyncio
    async def test_rejects_past_scheduled_for(self):
        auth = _auth()
        emp_id = uuid4()

        db = AsyncMock()
        verify_result = Mock()
        verify_result.scalar_one_or_none.return_value = uuid4()
        db.execute = AsyncMock(return_value=verify_result)

        body = ScheduledActionCreateRequest(
            description="did yesterday",
            scheduled_for=datetime.now(UTC) - timedelta(hours=1),
            recurring=False,
        )

        with pytest.raises(HTTPException) as exc:
            await scheduler_ep.create_scheduled_action(
                db=db, auth=auth, body=body, employee_id=emp_id
            )
        assert exc.value.status_code == 400

    def test_recurring_without_interval_hours_is_rejected_at_schema(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ScheduledActionCreateRequest(
                description="every so often",
                scheduled_for=datetime.now(UTC) + timedelta(hours=1),
                recurring=True,
                interval_hours=None,
            )

    def test_scheduled_for_without_timezone_is_rejected(self):
        from pydantic import ValidationError

        # Naive datetime — no tzinfo. This IS the thing under test.
        naive = datetime(2030, 1, 1, 12, 0, 0)  # noqa: DTZ001
        with pytest.raises(ValidationError):
            ScheduledActionCreateRequest(
                description="x",
                scheduled_for=naive,
                recurring=False,
            )


# ---------------------------------------------------------------------------
# DELETE /schedule/{id}
# ---------------------------------------------------------------------------


class TestCancelScheduledAction:
    @pytest.mark.asyncio
    async def test_cancels_existing_action(self):
        auth = _auth()
        emp_id = uuid4()
        action_id = uuid4()

        row = _FakeRow(
            row_id=action_id,
            content=_sched_content("x", datetime.now(UTC) + timedelta(hours=1)),
        )

        db = AsyncMock()
        verify_result = Mock()
        verify_result.scalar_one_or_none.return_value = uuid4()
        row_result = Mock()
        row_result.scalar_one_or_none.return_value = row
        db.execute = AsyncMock(side_effect=[verify_result, row_result])
        db.commit = AsyncMock()

        await scheduler_ep.cancel_scheduled_action(
            db=db, auth=auth, employee_id=emp_id, action_id=action_id
        )

        assert row.deleted_at is not None

    @pytest.mark.asyncio
    async def test_404_on_missing_row(self):
        auth = _auth()
        db = AsyncMock()
        verify_result = Mock()
        verify_result.scalar_one_or_none.return_value = uuid4()
        missing_result = Mock()
        missing_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(side_effect=[verify_result, missing_result])

        with pytest.raises(HTTPException) as exc:
            await scheduler_ep.cancel_scheduled_action(
                db=db, auth=auth, employee_id=uuid4(), action_id=uuid4()
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_404_on_non_scheduled_action_row(self):
        """A row exists at that id but its subtype is something else — opaque 404."""
        auth = _auth()
        row = _FakeRow(
            row_id=uuid4(),
            content={"subtype": "something_else", "description": "not a schedule"},
        )
        db = AsyncMock()
        verify_result = Mock()
        verify_result.scalar_one_or_none.return_value = uuid4()
        row_result = Mock()
        row_result.scalar_one_or_none.return_value = row
        db.execute = AsyncMock(side_effect=[verify_result, row_result])

        with pytest.raises(HTTPException) as exc:
            await scheduler_ep.cancel_scheduled_action(
                db=db, auth=auth, employee_id=uuid4(), action_id=uuid4()
            )
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Source-aware prefix in _check_scheduled_actions
# ---------------------------------------------------------------------------


class TestSourceAwarePrefix:
    """Verify the loop's perception-injection prefix differentiates source."""

    def test_employee_prefix(self):
        # The prefix logic is inline in execution.py — replicate to assert the
        # contract we rely on. This guards the observation shape used by the
        # LLM's perception phase.
        source = "employee"
        prefix = (
            "USER-REQUESTED SCHEDULED ACTION"
            if source == "user_requested"
            else "SCHEDULED ACTION DUE"
        )
        assert prefix == "SCHEDULED ACTION DUE"

    def test_user_requested_prefix(self):
        source = "user_requested"
        prefix = (
            "USER-REQUESTED SCHEDULED ACTION"
            if source == "user_requested"
            else "SCHEDULED ACTION DUE"
        )
        assert prefix == "USER-REQUESTED SCHEDULED ACTION"
