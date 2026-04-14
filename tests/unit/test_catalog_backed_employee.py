"""
Tests for empla.employees.catalog_backed.CatalogBackedEmployee.

Covers:
- role_code resolution (valid, missing, unknown)
- default_* properties return fresh copies from the catalog
- on_start records role belief + startup episode
- on_start raises EmployeeStartupError on belief failure
- on_stop records shutdown episode
- on_start/on_stop are non-fatal on episode failure
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from empla.employees import EmployeeConfig
from empla.employees.catalog_backed import CatalogBackedEmployee
from empla.employees.exceptions import EmployeeStartupError


class _CatalogPM(CatalogBackedEmployee):
    """Minimal concrete subclass backed by the 'pm' catalog entry."""

    role_code = "pm"


class _NoRoleCode(CatalogBackedEmployee):
    """Subclass that forgets to set role_code — triggers runtime error."""


class _UnknownRoleCode(CatalogBackedEmployee):
    role_code = "does_not_exist"


def _make(cls=_CatalogPM):
    return cls(EmployeeConfig(name="T", role="pm", email="t@t.com"))


# ---------------------------------------------------------------------------
# role_code resolution
# ---------------------------------------------------------------------------


class TestRoleResolution:
    def test_empty_role_code_raises(self):
        emp = _NoRoleCode(EmployeeConfig(name="T", role="pm", email="t@t.com"))
        with pytest.raises(RuntimeError, match="role_code"):
            _ = emp.default_personality

    def test_unknown_role_code_raises(self):
        emp = _UnknownRoleCode(EmployeeConfig(name="T", role="pm", email="t@t.com"))
        with pytest.raises(RuntimeError, match="does_not_exist"):
            _ = emp.default_goals


# ---------------------------------------------------------------------------
# default_* properties return fresh instances from the catalog
# ---------------------------------------------------------------------------


class TestDefaultsFromCatalog:
    def test_default_personality_is_fresh_instance(self):
        emp = _make()
        a = emp.default_personality
        b = emp.default_personality
        # Separate instances (Personality is frozen, so we can't mutate — but
        # identity separation proves we're not handing out the shared catalog
        # object that other employees might try to copy from).
        assert a is not b
        assert a == b

    def test_default_goals_returns_fresh_list(self):
        emp = _make()
        a = emp.default_goals
        b = emp.default_goals
        assert a is not b
        a.clear()
        assert len(emp.default_goals) > 0

    def test_default_capabilities_returns_fresh_list(self):
        emp = _make()
        a = emp.default_capabilities
        b = emp.default_capabilities
        assert a is not b
        a.clear()
        assert len(emp.default_capabilities) > 0


# ---------------------------------------------------------------------------
# on_start
# ---------------------------------------------------------------------------


class TestOnStart:
    @pytest.mark.asyncio
    async def test_records_role_belief_with_catalog_focus(self):
        emp = _make()
        emp._beliefs = Mock()
        emp._beliefs.update_belief = AsyncMock()
        emp._memory = Mock()
        emp._memory.episodic = Mock()
        emp._memory.episodic.record_episode = AsyncMock()

        await emp.on_start()

        emp._beliefs.update_belief.assert_awaited_once()
        kwargs = emp._beliefs.update_belief.await_args.kwargs
        assert kwargs["subject"] == "self"
        assert kwargs["predicate"] == "role"
        assert kwargs["belief_object"]["type"] == "pm"
        # focus should come from the catalog's focus_keyword
        assert kwargs["belief_object"]["focus"] == "product_delivery"
        assert kwargs["confidence"] == 1.0
        assert kwargs["source"] == "prior"

    @pytest.mark.asyncio
    async def test_falls_back_to_role_code_when_focus_keyword_missing(self):
        """If a role has no focus_keyword, the role code is used instead."""

        class _NoFocus(CatalogBackedEmployee):
            role_code = "pm"

            @classmethod
            def _role(cls):
                role = super()._role()
                return role.model_copy(update={"focus_keyword": ""})

        emp = _NoFocus(EmployeeConfig(name="T", role="pm", email="t@t.com"))
        emp._beliefs = Mock()
        emp._beliefs.update_belief = AsyncMock()
        emp._memory = Mock()
        emp._memory.episodic = Mock()
        emp._memory.episodic.record_episode = AsyncMock()

        await emp.on_start()

        kwargs = emp._beliefs.update_belief.await_args.kwargs
        assert kwargs["belief_object"]["focus"] == "pm"

    @pytest.mark.asyncio
    async def test_records_startup_episode(self):
        emp = _make()
        emp._beliefs = Mock()
        emp._beliefs.update_belief = AsyncMock()
        emp._memory = Mock()
        emp._memory.episodic = Mock()
        emp._memory.episodic.record_episode = AsyncMock()

        await emp.on_start()

        emp._memory.episodic.record_episode.assert_awaited_once()
        kwargs = emp._memory.episodic.record_episode.await_args.kwargs
        assert kwargs["episode_type"] == "event"
        assert kwargs["content"]["event"] == "employee_started"
        assert kwargs["content"]["role"] == "pm"
        # Exact content: must reflect this employee's defaults, not sibling-role defaults.
        # Guards against the very bug CatalogBackedEmployee was refactored to prevent.
        assert kwargs["content"]["capabilities"] == emp.default_capabilities
        assert kwargs["content"]["goals"] == [g.description for g in emp.default_goals]

    @pytest.mark.asyncio
    async def test_belief_failure_raises_employee_startup_error(self):
        emp = _make()
        emp._beliefs = Mock()
        emp._beliefs.update_belief = AsyncMock(side_effect=RuntimeError("DB down"))
        emp._memory = Mock()
        emp._memory.episodic = Mock()
        emp._memory.episodic.record_episode = AsyncMock()

        with pytest.raises(EmployeeStartupError, match="Belief initialization failed"):
            await emp.on_start()

    @pytest.mark.asyncio
    async def test_episode_failure_is_non_fatal_on_start(self):
        emp = _make()
        emp._beliefs = Mock()
        emp._beliefs.update_belief = AsyncMock()
        emp._memory = Mock()
        emp._memory.episodic = Mock()
        emp._memory.episodic.record_episode = AsyncMock(side_effect=RuntimeError("episodic down"))

        # Should complete without raising
        await emp.on_start()

        # Belief must have been written before the episode failure (observable,
        # not just "did not raise"). Guards against a future refactor that
        # swallows belief errors along with episode errors.
        emp._beliefs.update_belief.assert_awaited_once()
        emp._memory.episodic.record_episode.assert_awaited_once()


# ---------------------------------------------------------------------------
# on_stop
# ---------------------------------------------------------------------------


class TestOnStop:
    @pytest.mark.asyncio
    async def test_records_shutdown_episode(self):
        emp = _make()
        emp._memory = Mock()
        emp._memory.episodic = Mock()
        emp._memory.episodic.record_episode = AsyncMock()

        await emp.on_stop()

        emp._memory.episodic.record_episode.assert_awaited_once()
        kwargs = emp._memory.episodic.record_episode.await_args.kwargs
        assert kwargs["content"]["event"] == "employee_stopped"

    @pytest.mark.asyncio
    async def test_no_memory_is_noop(self):
        emp = _make()
        emp._memory = None

        # Should not raise even though memory is None
        await emp.on_stop()

    @pytest.mark.asyncio
    async def test_episode_failure_is_non_fatal_on_stop(self):
        emp = _make()
        emp._memory = Mock()
        emp._memory.episodic = Mock()
        emp._memory.episodic.record_episode = AsyncMock(side_effect=RuntimeError("episodic down"))

        await emp.on_stop()
