"""
Unit tests for PR #85: Custom-role employee creation + LLM role builder.

Covers:
- ``GenericEmployee`` instantiates without abstract-method errors and
  delegates the three default_* properties to ``self.config``.
- ``get_employee_class('marketing_manager')`` returns ``GenericEmployee``;
  built-in roles still return their dedicated class.
- ``EmployeeCreate`` schema:
  - control chars stripped from role_description
  - role_description length cap (1000 chars)
  - GoalInput validation (priority bounds, max 20 goals)
- ``POST /employees`` handler:
  - role='custom' + missing role_description → 422
  - role='custom' + missing goals → 422
  - role='custom' + non-admin → 403
  - role='custom' + admin + valid body → persists role_description into
    Employee.config JSONB and creates EmployeeGoal rows
  - role='sales_ae' + member → still works (built-in path is unchanged)
- ``POST /employees/generate-role``:
  - admin-only via dependency
  - returns the LLM-parsed draft on happy path (with mocked LLM)
  - LLM ValidationError → 422
  - missing API key (LLMService init ValueError) → 503
  - GeneratedRoleDraft schema rejects out-of-range capability key
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from empla.api.v1.endpoints import employees as employees_ep
from empla.api.v1.endpoints import role_builder as role_builder_ep
from empla.api.v1.schemas.employee import (
    MAX_ROLE_DESCRIPTION_LEN,
    EmployeeCreate,
    GoalInput,
    _strip_control_chars,
)
from empla.api.v1.schemas.role_builder import (
    ALLOWED_CAPABILITIES,
    GeneratedRoleDraft,
    GenerateRoleRequest,
    PersonalitySliders,
)
from empla.employees.config import EmployeeConfig, GoalConfig
from empla.employees.generic import GenericEmployee
from empla.employees.personality import Personality
from empla.employees.registry import get_employee_class

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth(role: str = "admin", tenant_id: UUID | None = None) -> SimpleNamespace:
    """Mimic ``AuthContext`` with the new ``.role`` shortcut."""
    return SimpleNamespace(
        user_id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        role=role,
        user=SimpleNamespace(role=role),
    )


def _captured_db() -> tuple[AsyncMock, list]:
    """An AsyncMock session that records every ``db.add(...)`` call.

    Populates SQLAlchemy server-default columns (``id``, timestamps,
    ``performance_metrics``) on add so that ``EmployeeResponse.model_validate``
    later in the handler doesn't fail on unset NOT-NULL fields. Unit tests
    don't have a live DB to apply server defaults for us.
    """
    from datetime import UTC
    from datetime import datetime as _dt

    added: list = []
    db = AsyncMock()

    no_existing = Mock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=no_existing)

    def _add(obj):
        added.append(obj)
        if hasattr(obj, "id") and obj.id is None:
            obj.id = uuid4()
        # Apply server-default values that the DB would set.
        now = _dt.now(UTC)
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        if (
            hasattr(obj, "performance_metrics")
            and getattr(obj, "performance_metrics", None) is None
        ):
            obj.performance_metrics = {}

    db.add = Mock(side_effect=_add)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db, added


def _valid_custom_body(**overrides) -> EmployeeCreate:
    body = {
        "name": "Marketing Mike",
        "role": "custom",
        "email": "mike@example.com",
        "role_description": "You build and run lifecycle email campaigns end to end.",
        "goals": [
            {
                "description": "Maintain a healthy newsletter open rate above 25%.",
                "priority": 8,
                "target": {"metric": "open_rate", "value": 0.25},
                "goal_type": "maintain",
            }
        ],
    }
    body.update(overrides)
    return EmployeeCreate(**body)


# ---------------------------------------------------------------------------
# GenericEmployee
# ---------------------------------------------------------------------------


class TestGenericEmployee:
    def test_no_abstract_methods_remaining(self):
        # Python refuses to instantiate any subclass of an ABC that leaves
        # an @abstractmethod unoverridden. If GenericEmployee accidentally
        # drops one of the three overrides we need to know loudly.
        assert not GenericEmployee.__abstractmethods__, (
            "GenericEmployee left abstract methods unimplemented: "
            f"{GenericEmployee.__abstractmethods__}"
        )

    def test_instantiates_from_config(self):
        """A bare config with no explicit overrides should still work — the
        Employee row's persisted state is the source of truth."""
        config = EmployeeConfig(
            name="Test Employee",
            role="custom",
            email="test@example.com",
        )
        emp = GenericEmployee(config)
        assert isinstance(emp, GenericEmployee)
        # ``EmployeeConfig`` pre-populates ``capabilities=["email"]`` as a
        # fallback so a runtime never finds zero capabilities; default_goals
        # has no such default and stays empty until the API seeds them.
        assert emp.default_capabilities == ["email"]
        assert emp.default_goals == []
        assert isinstance(emp.default_personality, Personality)

    def test_reads_goals_from_config(self):
        goals = [
            GoalConfig(
                goal_type="achievement",
                description="Ship the launch",
                priority=9,
                target={"by": "Q3"},
            )
        ]
        config = EmployeeConfig(
            name="X",
            role="custom",
            email="x@example.com",
            goals=goals,
            capabilities=["email", "calendar"],
            personality=Personality(extraversion=0.9),
        )
        emp = GenericEmployee(config)
        assert emp.default_goals == goals
        assert emp.default_capabilities == ["email", "calendar"]
        assert emp.default_personality.extraversion == 0.9


# ---------------------------------------------------------------------------
# Registry fallback
# ---------------------------------------------------------------------------


class TestRegistryFallback:
    def test_unknown_role_returns_generic_employee(self):
        cls = get_employee_class("marketing_manager")
        assert cls is GenericEmployee

    def test_custom_role_returns_generic_employee(self):
        cls = get_employee_class("custom")
        assert cls is GenericEmployee

    def test_built_in_roles_return_dedicated_class(self):
        from empla.employees.csm import CustomerSuccessManager
        from empla.employees.sales_ae import SalesAE

        assert get_employee_class("sales_ae") is SalesAE
        assert get_employee_class("csm") is CustomerSuccessManager


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestEmployeeCreateSchema:
    def test_strips_control_chars_from_role_description(self):
        # \u202e is the right-to-left override — a real injection vector.
        body = EmployeeCreate(
            name="Test",
            role="custom",
            email="test@x.com",
            role_description="Manage \u202e\u200bemail\u0008 campaigns",
        )
        assert "\u202e" not in (body.role_description or "")
        assert "\u200b" not in (body.role_description or "")
        assert "\u0008" not in (body.role_description or "")
        assert (body.role_description or "").strip() == "Manage email campaigns"

    def test_role_description_length_cap(self):
        with pytest.raises(ValidationError):
            EmployeeCreate(
                name="Test",
                role="custom",
                email="test@x.com",
                role_description="x" * (MAX_ROLE_DESCRIPTION_LEN + 1),
            )

    def test_role_description_keeps_newlines(self):
        # Newlines/tabs ARE valid — multi-paragraph descriptions are normal.
        body = EmployeeCreate(
            name="Test",
            role="custom",
            email="test@x.com",
            role_description="Para 1.\n\nPara 2.\n\tIndented.",
        )
        assert "\n\n" in (body.role_description or "")
        assert "\t" in (body.role_description or "")

    def test_role_description_only_control_chars_returns_none(self):
        body = EmployeeCreate(
            name="Test",
            role="custom",
            email="test@x.com",
            role_description="\u202e\u200b\u0008",
        )
        assert body.role_description is None

    def test_goal_priority_bounds(self):
        with pytest.raises(ValidationError):
            GoalInput(description="x", priority=0)
        with pytest.raises(ValidationError):
            GoalInput(description="x", priority=11)

    def test_goals_max_length_enforced(self):
        with pytest.raises(ValidationError):
            EmployeeCreate(
                name="Test",
                role="custom",
                email="test@x.com",
                role_description="ok",
                goals=[{"description": f"goal {i}"} for i in range(21)],
            )


def test_strip_control_chars_unit():
    assert _strip_control_chars("hello") == "hello"
    assert _strip_control_chars("hello\u202eworld") == "helloworld"
    assert _strip_control_chars("multi\nline\tok") == "multi\nline\tok"
    assert _strip_control_chars("\ufeffBOMprefix") == "BOMprefix"


# ---------------------------------------------------------------------------
# POST /employees with role='custom'
# ---------------------------------------------------------------------------


class TestCreateCustomEmployee:
    @pytest.mark.asyncio
    async def test_missing_role_description_returns_422(self):
        db, _ = _captured_db()
        body = EmployeeCreate(
            name="Test",
            role="custom",
            email="x@example.com",
            goals=[GoalInput(description="g")],
        )
        with pytest.raises(HTTPException) as exc:
            await employees_ep.create_employee(db=db, auth=_auth(), data=body)
        assert exc.value.status_code == 422
        assert "role_description" in exc.value.detail

    @pytest.mark.asyncio
    async def test_missing_goals_returns_422(self):
        db, _ = _captured_db()
        body = EmployeeCreate(
            name="Test",
            role="custom",
            email="x@example.com",
            role_description="ok",
        )
        with pytest.raises(HTTPException) as exc:
            await employees_ep.create_employee(db=db, auth=_auth(), data=body)
        assert exc.value.status_code == 422
        assert "goals" in exc.value.detail

    @pytest.mark.asyncio
    async def test_member_cannot_create_custom_role_returns_403(self):
        db, _ = _captured_db()
        body = _valid_custom_body()
        with pytest.raises(HTTPException) as exc:
            await employees_ep.create_employee(db=db, auth=_auth(role="member"), data=body)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_member_can_create_built_in_role(self):
        db, added = _captured_db()
        body = EmployeeCreate(
            name="Jordan",
            role="sales_ae",
            email="jordan@example.com",
        )
        # Should succeed without raising — built-in path is unchanged.
        # The handler returns an EmployeeResponse-shaped object; we only care
        # that no admin/422 was raised.
        await employees_ep.create_employee(db=db, auth=_auth(role="member"), data=body)
        assert any(getattr(o, "role", None) == "sales_ae" for o in added)

    @pytest.mark.asyncio
    async def test_admin_creates_custom_persists_state(self):
        db, added = _captured_db()
        body = _valid_custom_body()
        await employees_ep.create_employee(db=db, auth=_auth(), data=body)

        employees = [o for o in added if getattr(o, "role", None) == "custom"]
        assert len(employees) == 1
        emp = employees[0]
        assert emp.config["role_description"].startswith("You build")
        # EmployeeGoal rows must be added too — exactly as many as the body.
        from empla.models.employee import EmployeeGoal

        goals = [o for o in added if isinstance(o, EmployeeGoal)]
        assert len(goals) == 1
        assert goals[0].description == body.goals[0].description
        assert goals[0].priority == body.goals[0].priority
        assert goals[0].goal_type == body.goals[0].goal_type

    @pytest.mark.asyncio
    async def test_member_supplying_empty_goals_list_still_403s(self):
        """CodeRabbit key-presence gate: `goals=[]` is falsy but the caller
        DID attempt to set the field. We treat 'tried to set' as the audit
        boundary, so a member submitting `role='sales_ae'` + `goals=[]`
        must 403 before the 422 'goals cannot be empty' branch fires."""
        db, _ = _captured_db()
        body = EmployeeCreate(
            name="Jordan",
            role="sales_ae",
            email="j@example.com",
            goals=[GoalInput(description="placeholder")],  # supplied, will be cleared next
        )
        # Re-hydrate with goals=[] to land in __pydantic_fields_set__ but empty.
        body_dict = body.model_dump()
        body_dict["goals"] = []
        body_empty_goals = EmployeeCreate(**body_dict)
        assert "goals" in body_empty_goals.model_fields_set

        with pytest.raises(HTTPException) as exc:
            await employees_ep.create_employee(
                db=db, auth=_auth(role="user"), data=body_empty_goals
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_member_supplying_empty_role_description_still_403s(self):
        """Same key-presence rule for role_description: a member setting it
        to '' (or any value stripped to '') tried to touch prompt state —
        gate before schema cleanup runs."""
        db, _ = _captured_db()
        body_dict = {
            "name": "Jordan",
            "role": "sales_ae",
            "email": "j2@example.com",
            "role_description": "   ",  # pure whitespace, cleaned to None
        }
        body = EmployeeCreate(**body_dict)
        # Validator strips to None, but the key is in the fields-set.
        assert body.role_description is None
        assert "role_description" in body.model_fields_set

        with pytest.raises(HTTPException) as exc:
            await employees_ep.create_employee(db=db, auth=_auth(role="user"), data=body)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_member_supplying_empty_config_role_description_still_403s(self):
        """A member sending `config={'role_description': ''}` blanks the
        runner's ROLE_CATALOG fallback — key presence is the check."""
        db, _ = _captured_db()
        body = EmployeeCreate(
            name="Jordan",
            role="sales_ae",
            email="j3@example.com",
            config={"role_description": ""},  # explicit empty
        )
        with pytest.raises(HTTPException) as exc:
            await employees_ep.create_employee(db=db, auth=_auth(role="user"), data=body)
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# GeneratedRoleDraft schema
# ---------------------------------------------------------------------------


class TestGeneratedRoleDraftSchema:
    def _valid(self, **overrides):
        base = {
            "name_suggestion": "Marketing Manager",
            "role_description": "You design and execute B2B marketing campaigns end to end.",
            "capabilities": ["email", "calendar"],
            "goals": [
                GoalInput(description="Hit MQL target this quarter", priority=9),
            ],
            "personality": PersonalitySliders(),
        }
        base.update(overrides)
        return base

    def test_happy(self):
        d = GeneratedRoleDraft(**self._valid())
        assert d.name_suggestion == "Marketing Manager"
        assert "email" in d.capabilities

    def test_unknown_capability_rejected(self):
        with pytest.raises(ValidationError):
            GeneratedRoleDraft(**self._valid(capabilities=["email", "make_coffee"]))

    def test_capabilities_must_be_in_allowlist(self):
        # Sanity check the allowlist itself didn't drift.
        assert {"email", "calendar", "crm", "search"} == ALLOWED_CAPABILITIES

    def test_capabilities_deduped(self):
        d = GeneratedRoleDraft(**self._valid(capabilities=["email", "email", "calendar"]))
        assert d.capabilities == ["email", "calendar"]

    def test_role_description_too_short_rejected(self):
        with pytest.raises(ValidationError):
            GeneratedRoleDraft(**self._valid(role_description="too short"))

    def test_role_description_too_long_rejected(self):
        with pytest.raises(ValidationError):
            GeneratedRoleDraft(**self._valid(role_description="x" * (MAX_ROLE_DESCRIPTION_LEN + 1)))

    def test_must_have_at_least_one_goal(self):
        with pytest.raises(ValidationError):
            GeneratedRoleDraft(**self._valid(goals=[]))


# ---------------------------------------------------------------------------
# POST /employees/generate-role
# ---------------------------------------------------------------------------


class TestGenerateRoleEndpoint:
    @pytest.mark.asyncio
    async def test_returns_draft_on_happy_path(self):
        valid_draft = GeneratedRoleDraft(
            name_suggestion="Marketing Manager",
            role_description="You design and execute B2B campaigns end to end.",
            capabilities=["email", "calendar"],
            goals=[GoalInput(description="Hit MQL target", priority=9)],
            personality=PersonalitySliders(),
        )
        mock_llm = AsyncMock()
        mock_llm.generate_structured = AsyncMock(return_value=(Mock(), valid_draft))

        with patch.object(role_builder_ep, "LLMService", return_value=mock_llm):
            result = await role_builder_ep.generate_role(
                body=GenerateRoleRequest(description="A marketing manager who runs campaigns."),
                auth=_auth(),
            )

        assert isinstance(result, GeneratedRoleDraft)
        assert result.name_suggestion == "Marketing Manager"
        # Make sure the LLM was actually called with our system prompt + user
        # description, not a placeholder.
        _args, kwargs = mock_llm.generate_structured.call_args
        assert "marketing manager" in kwargs["prompt"].lower()
        assert kwargs["response_format"] is GeneratedRoleDraft

    @pytest.mark.asyncio
    async def test_llm_validation_error_returns_422(self):
        mock_llm = AsyncMock()
        # Trigger a real ValidationError so the 422 branch fires.
        try:
            GeneratedRoleDraft(name_suggestion="X")  # type: ignore[call-arg]
        except ValidationError as e:
            ve = e
        mock_llm.generate_structured = AsyncMock(side_effect=ve)

        with patch.object(role_builder_ep, "LLMService", return_value=mock_llm):
            with pytest.raises(HTTPException) as exc:
                await role_builder_ep.generate_role(
                    body=GenerateRoleRequest(description="describe a role please"),
                    auth=_auth(),
                )
        assert exc.value.status_code == 422
        assert "malformed" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_503(self):
        # LLMService raises ValueError when the configured provider has no
        # API key. Endpoint must surface as 503, not 500.
        with patch.object(
            role_builder_ep,
            "LLMService",
            side_effect=ValueError("ANTHROPIC_API_KEY not set"),
        ):
            with pytest.raises(HTTPException) as exc:
                await role_builder_ep.generate_role(
                    body=GenerateRoleRequest(description="describe a role please"),
                    auth=_auth(),
                )
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_generic_llm_failure_returns_502(self):
        mock_llm = AsyncMock()
        mock_llm.generate_structured = AsyncMock(side_effect=RuntimeError("provider down"))
        with patch.object(role_builder_ep, "LLMService", return_value=mock_llm):
            with pytest.raises(HTTPException) as exc:
                await role_builder_ep.generate_role(
                    body=GenerateRoleRequest(description="describe a role please"),
                    auth=_auth(),
                )
        assert exc.value.status_code == 502

    @pytest.mark.asyncio
    async def test_request_validates_description_length(self):
        with pytest.raises(ValidationError):
            GenerateRoleRequest(description="too short")
        # Boundary: exactly 2000 chars must pass (max_length is inclusive).
        GenerateRoleRequest(description="x" * 2000)
        with pytest.raises(ValidationError):
            GenerateRoleRequest(description="x" * 2001)
