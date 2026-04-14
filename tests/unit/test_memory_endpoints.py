"""
Unit tests for empla.api.v1.endpoints.memory.

Scope:
- _pages() math (edge cases)
- _verify_employee 404 on missing / cross-tenant
- Each endpoint: happy path, filters, invalid-enum rejection
- Schemas omit the ``employee`` relationship (N+1 guard)

Uses direct function calls with mocked DBSession + CurrentUser. The BDI
pagination pattern is mirrored inline in each endpoint, so we exercise it
end-to-end without an ASGI client.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from empla.api.v1.endpoints import memory as memory_ep
from empla.api.v1.schemas.memory import (
    EpisodicMemoryResponse,
    ProceduralMemoryResponse,
    SemanticMemoryResponse,
    WorkingMemoryResponse,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth(tenant_id: UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        role="member",
    )


def _make_db(verify_hit: bool, count: int, rows: list) -> AsyncMock:
    """
    Build a mocked DBSession that answers three execute() calls in order:
    1. _verify_employee — returns either the employee id (hit) or None
    2. count() query
    3. row fetch

    Working-memory endpoint skips the count step, so we branch below.
    """
    db = AsyncMock()
    verify_result = Mock()
    verify_result.scalar_one_or_none.return_value = uuid4() if verify_hit else None

    count_result = Mock()
    count_result.scalar.return_value = count

    fetch_result = Mock()
    scalars = Mock()
    scalars.all.return_value = rows
    fetch_result.scalars.return_value = scalars

    db.execute = AsyncMock(side_effect=[verify_result, count_result, fetch_result])
    return db


def _make_db_no_count(verify_hit: bool, rows: list) -> AsyncMock:
    """Two-call version for the working-memory endpoint (no pagination)."""
    db = AsyncMock()
    verify_result = Mock()
    verify_result.scalar_one_or_none.return_value = uuid4() if verify_hit else None

    fetch_result = Mock()
    scalars = Mock()
    scalars.all.return_value = rows
    fetch_result.scalars.return_value = scalars

    db.execute = AsyncMock(side_effect=[verify_result, fetch_result])
    return db


def _ts() -> datetime:
    return datetime(2026, 4, 14, 12, 0, 0, tzinfo=UTC)


def _episodic_row(employee_id: UUID, tenant_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        employee_id=employee_id,
        tenant_id=tenant_id,
        episode_type="event",
        description="Employee started",
        content={"event": "employee_started"},
        participants=[],
        location=None,
        importance=0.5,
        recall_count=0,
        last_recalled_at=None,
        occurred_at=_ts(),
        created_at=_ts(),
        updated_at=_ts(),
    )


def _semantic_row(employee_id: UUID, tenant_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        employee_id=employee_id,
        tenant_id=tenant_id,
        fact_type="entity",
        subject="Acme Corp",
        predicate="is_a",
        object="customer",
        confidence=0.9,
        source="crm",
        verified=False,
        access_count=3,
        last_accessed_at=_ts(),
        context={},
        created_at=_ts(),
        updated_at=_ts(),
    )


def _procedural_row(employee_id: UUID, tenant_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        employee_id=employee_id,
        tenant_id=tenant_id,
        name="send_follow_up",
        description="Send follow-up email",
        procedure_type="workflow",
        steps=[{"action": "email.send"}],
        trigger_conditions={},
        success_rate=0.8,
        execution_count=10,
        success_count=8,
        avg_execution_time=1.2,
        last_executed_at=_ts(),
        is_playbook=True,
        promoted_at=_ts(),
        learned_from="autonomous_discovery",
        created_at=_ts(),
        updated_at=_ts(),
    )


def _working_row(employee_id: UUID, tenant_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        employee_id=employee_id,
        tenant_id=tenant_id,
        item_type="task",
        content={"task": "draft_email"},
        importance=0.7,
        expires_at=None,
        access_count=1,
        last_accessed_at=_ts(),
        created_at=_ts(),
        updated_at=_ts(),
    )


# ---------------------------------------------------------------------------
# _pages math
# ---------------------------------------------------------------------------


class TestPagesMath:
    def test_zero_total_is_one_page(self):
        assert memory_ep._pages(0, 50) == 1

    def test_exact_multiple(self):
        assert memory_ep._pages(100, 50) == 2

    def test_partial_last_page(self):
        assert memory_ep._pages(101, 50) == 3

    def test_tiny(self):
        assert memory_ep._pages(1, 50) == 1


# ---------------------------------------------------------------------------
# _verify_employee
# ---------------------------------------------------------------------------


class TestVerifyEmployee:
    @pytest.mark.asyncio
    async def test_missing_employee_raises_404(self):
        db = AsyncMock()
        result = Mock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        with pytest.raises(HTTPException) as exc:
            await memory_ep._verify_employee(db, uuid4(), uuid4())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_hit_does_not_raise(self):
        db = AsyncMock()
        result = Mock()
        result.scalar_one_or_none.return_value = uuid4()
        db.execute = AsyncMock(return_value=result)

        await memory_ep._verify_employee(db, uuid4(), uuid4())


# ---------------------------------------------------------------------------
# Episodic
# ---------------------------------------------------------------------------


class TestEpisodic:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        auth = _auth()
        employee_id = uuid4()
        rows = [_episodic_row(employee_id, auth.tenant_id) for _ in range(3)]
        db = _make_db(verify_hit=True, count=3, rows=rows)

        resp = await memory_ep.list_episodic_memory(
            db=db, auth=auth, employee_id=employee_id, page=1, page_size=50
        )

        assert resp.total == 3
        assert resp.pages == 1
        assert len(resp.items) == 3
        assert all(isinstance(item, EpisodicMemoryResponse) for item in resp.items)

    @pytest.mark.asyncio
    async def test_404_on_missing_employee(self):
        auth = _auth()
        db = _make_db(verify_hit=False, count=0, rows=[])

        with pytest.raises(HTTPException) as exc:
            await memory_ep.list_episodic_memory(
                db=db, auth=auth, employee_id=uuid4(), page=1, page_size=50
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_episode_type_rejected(self):
        auth = _auth()
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await memory_ep.list_episodic_memory(
                db=db,
                auth=auth,
                employee_id=uuid4(),
                page=1,
                page_size=50,
                episode_type="not_a_real_type",
            )
        assert exc.value.status_code == 400
        # DB should never be touched
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_episode_type_accepted(self):
        auth = _auth()
        employee_id = uuid4()
        db = _make_db(verify_hit=True, count=0, rows=[])

        resp = await memory_ep.list_episodic_memory(
            db=db,
            auth=auth,
            employee_id=employee_id,
            page=1,
            page_size=50,
            episode_type="interaction",
        )
        assert resp.total == 0

    @pytest.mark.asyncio
    async def test_pagination_math(self):
        auth = _auth()
        employee_id = uuid4()
        rows = [_episodic_row(employee_id, auth.tenant_id)]
        db = _make_db(verify_hit=True, count=237, rows=rows)

        resp = await memory_ep.list_episodic_memory(
            db=db, auth=auth, employee_id=employee_id, page=3, page_size=50
        )
        assert resp.page == 3
        assert resp.page_size == 50
        assert resp.total == 237
        assert resp.pages == 5


# ---------------------------------------------------------------------------
# Semantic
# ---------------------------------------------------------------------------


class TestSemantic:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        auth = _auth()
        employee_id = uuid4()
        rows = [_semantic_row(employee_id, auth.tenant_id)]
        db = _make_db(verify_hit=True, count=1, rows=rows)

        resp = await memory_ep.list_semantic_memory(
            db=db, auth=auth, employee_id=employee_id, page=1, page_size=50
        )
        assert resp.total == 1
        assert resp.items[0].subject == "Acme Corp"
        assert isinstance(resp.items[0], SemanticMemoryResponse)

    @pytest.mark.asyncio
    async def test_invalid_fact_type_rejected(self):
        with pytest.raises(HTTPException) as exc:
            await memory_ep.list_semantic_memory(
                db=AsyncMock(),
                auth=_auth(),
                employee_id=uuid4(),
                page=1,
                page_size=50,
                fact_type="bogus",
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_filters_accepted(self):
        auth = _auth()
        employee_id = uuid4()
        db = _make_db(verify_hit=True, count=0, rows=[])
        resp = await memory_ep.list_semantic_memory(
            db=db,
            auth=auth,
            employee_id=employee_id,
            page=1,
            page_size=50,
            fact_type="entity",
            subject="Acme",
            predicate="is_a",
            min_confidence=0.5,
        )
        assert resp.total == 0


# ---------------------------------------------------------------------------
# Procedural
# ---------------------------------------------------------------------------


class TestProcedural:
    @pytest.mark.asyncio
    async def test_happy_path_includes_playbook_flag(self):
        auth = _auth()
        employee_id = uuid4()
        rows = [_procedural_row(employee_id, auth.tenant_id)]
        db = _make_db(verify_hit=True, count=1, rows=rows)

        resp = await memory_ep.list_procedural_memory(
            db=db, auth=auth, employee_id=employee_id, page=1, page_size=50
        )
        assert resp.total == 1
        assert resp.items[0].is_playbook is True
        assert resp.items[0].success_rate == 0.8
        assert isinstance(resp.items[0], ProceduralMemoryResponse)

    @pytest.mark.asyncio
    async def test_invalid_procedure_type_rejected(self):
        with pytest.raises(HTTPException) as exc:
            await memory_ep.list_procedural_memory(
                db=AsyncMock(),
                auth=_auth(),
                employee_id=uuid4(),
                page=1,
                page_size=50,
                procedure_type="bogus",
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_is_playbook_filter_true(self):
        auth = _auth()
        employee_id = uuid4()
        db = _make_db(verify_hit=True, count=0, rows=[])
        resp = await memory_ep.list_procedural_memory(
            db=db,
            auth=auth,
            employee_id=employee_id,
            page=1,
            page_size=50,
            is_playbook=True,
            min_success_rate=0.7,
        )
        assert resp.total == 0


# ---------------------------------------------------------------------------
# Working
# ---------------------------------------------------------------------------


class TestWorking:
    @pytest.mark.asyncio
    async def test_happy_path_no_pagination(self):
        auth = _auth()
        employee_id = uuid4()
        rows = [_working_row(employee_id, auth.tenant_id) for _ in range(2)]
        db = _make_db_no_count(verify_hit=True, rows=rows)

        resp = await memory_ep.list_working_memory(db=db, auth=auth, employee_id=employee_id)
        assert resp.total == 2
        assert len(resp.items) == 2
        assert isinstance(resp.items[0], WorkingMemoryResponse)

    @pytest.mark.asyncio
    async def test_invalid_item_type_rejected(self):
        with pytest.raises(HTTPException) as exc:
            await memory_ep.list_working_memory(
                db=AsyncMock(), auth=_auth(), employee_id=uuid4(), item_type="bogus"
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_item_type_filter_accepted(self):
        auth = _auth()
        employee_id = uuid4()
        db = _make_db_no_count(verify_hit=True, rows=[])
        resp = await memory_ep.list_working_memory(
            db=db, auth=auth, employee_id=employee_id, item_type="task"
        )
        assert resp.total == 0

    @pytest.mark.asyncio
    async def test_404_on_missing_employee(self):
        auth = _auth()
        db = _make_db_no_count(verify_hit=False, rows=[])

        with pytest.raises(HTTPException) as exc:
            await memory_ep.list_working_memory(db=db, auth=auth, employee_id=uuid4())
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# N+1 guard: schemas must not expose `employee`
# ---------------------------------------------------------------------------


class TestSchemasDoNotExposeEmployee:
    """
    Memory models have a lazy ``employee`` relationship. If any response
    schema has an ``employee`` field, ``model_validate(row)`` would trigger
    a lazy-load at serialization time — MissingGreenlet in async, silent
    N+1 in sync. Enforce that no memory schema has that field.
    """

    def test_episodic_schema_has_no_employee_field(self):
        assert "employee" not in EpisodicMemoryResponse.model_fields

    def test_semantic_schema_has_no_employee_field(self):
        assert "employee" not in SemanticMemoryResponse.model_fields

    def test_procedural_schema_has_no_employee_field(self):
        assert "employee" not in ProceduralMemoryResponse.model_fields

    def test_working_schema_has_no_employee_field(self):
        assert "employee" not in WorkingMemoryResponse.model_fields
