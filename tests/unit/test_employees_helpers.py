"""
Tests for PM / SDR / Recruiter role-specific helper methods.

These helpers are currently stubs with TODOs for structured-output parsing.
Tests codify the documented contract (ValueError guards, LLM-failure
fallbacks, return shapes) so the stubs can be safely replaced with real
implementations without silently changing caller behavior.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from empla.employees import SDR, EmployeeConfig, ProductManager, Recruiter
from empla.employees.exceptions import LLMGenerationError


def _stub_llm(content: str = "LLM output here"):
    llm = Mock()
    response = Mock()
    response.content = content
    llm.generate = AsyncMock(return_value=response)
    return llm


# ---------------------------------------------------------------------------
# ProductManager.prioritize_backlog
# ---------------------------------------------------------------------------


class TestPrioritizeBacklog:
    def _emp(self) -> ProductManager:
        return ProductManager(EmployeeConfig(name="T", role="pm", email="t@t.com"))

    @pytest.mark.asyncio
    async def test_empty_is_noop(self):
        emp = self._emp()
        emp._llm = _stub_llm()
        assert await emp.prioritize_backlog([]) == []
        emp._llm.generate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_success_returns_list(self):
        emp = self._emp()
        emp._llm = _stub_llm()
        items = [{"title": "A"}, {"title": "B"}]
        result = await emp.prioritize_backlog(items)
        assert result == items
        emp._llm.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_failure_returns_original(self):
        emp = self._emp()
        emp._llm = Mock()
        emp._llm.generate = AsyncMock(side_effect=RuntimeError("boom"))
        items = [{"title": "A"}]
        assert await emp.prioritize_backlog(items) == items


# ---------------------------------------------------------------------------
# ProductManager.draft_release_notes
# ---------------------------------------------------------------------------


class TestDraftReleaseNotes:
    def _emp(self) -> ProductManager:
        return ProductManager(EmployeeConfig(name="T", role="pm", email="t@t.com"))

    @pytest.mark.asyncio
    async def test_rejects_empty_features(self):
        emp = self._emp()
        with pytest.raises(ValueError, match="features"):
            await emp.draft_release_notes([], "v1.0")

    @pytest.mark.asyncio
    async def test_rejects_empty_version(self):
        emp = self._emp()
        with pytest.raises(ValueError, match="version"):
            await emp.draft_release_notes(["f1"], "   ")

    @pytest.mark.asyncio
    async def test_rejects_long_version(self):
        emp = self._emp()
        with pytest.raises(ValueError, match="too long"):
            await emp.draft_release_notes(["f1"], "x" * 51)

    @pytest.mark.asyncio
    async def test_success_returns_content(self):
        emp = self._emp()
        emp._llm = _stub_llm("## Release 1.0\n- feature")
        result = await emp.draft_release_notes(["f1", "f2"], "v1.0")
        assert "Release" in result

    @pytest.mark.asyncio
    async def test_llm_failure_wraps_in_llm_generation_error(self):
        emp = self._emp()
        emp._llm = Mock()
        emp._llm.generate = AsyncMock(side_effect=RuntimeError("x"))
        with pytest.raises(LLMGenerationError):
            await emp.draft_release_notes(["f1"], "v1.0")


# ---------------------------------------------------------------------------
# SDR.qualify_lead
# ---------------------------------------------------------------------------


class TestQualifyLead:
    def _emp(self) -> SDR:
        return SDR(EmployeeConfig(name="T", role="sdr", email="t@t.com"))

    @pytest.mark.asyncio
    async def test_rejects_empty_lead(self):
        emp = self._emp()
        with pytest.raises(ValueError, match="lead"):
            await emp.qualify_lead({})

    @pytest.mark.asyncio
    async def test_success_returns_expected_shape(self):
        emp = self._emp()
        emp._llm = _stub_llm("qualified")
        result = await emp.qualify_lead({"name": "Acme"})
        # Stub contract: always returns these three keys
        assert set(result.keys()) >= {"qualified", "score", "reasoning"}
        assert isinstance(result["qualified"], bool)
        assert isinstance(result["score"], int)

    @pytest.mark.asyncio
    async def test_llm_failure_returns_error_shape(self):
        emp = self._emp()
        emp._llm = Mock()
        emp._llm.generate = AsyncMock(side_effect=RuntimeError("x"))
        result = await emp.qualify_lead({"name": "Acme"})
        assert result["qualified"] is False
        assert result["score"] == 0
        assert "qualification_error" in result["reasoning"]


# ---------------------------------------------------------------------------
# SDR.draft_prospect_email
# ---------------------------------------------------------------------------


class TestDraftProspectEmail:
    def _emp(self) -> SDR:
        return SDR(EmployeeConfig(name="T", role="sdr", email="t@t.com"))

    @pytest.mark.asyncio
    async def test_rejects_empty_prospect(self):
        emp = self._emp()
        with pytest.raises(ValueError, match="prospect_name"):
            await emp.draft_prospect_email("   ", "Acme")

    @pytest.mark.asyncio
    async def test_rejects_empty_company(self):
        emp = self._emp()
        with pytest.raises(ValueError, match="company"):
            await emp.draft_prospect_email("Jane", "")

    @pytest.mark.asyncio
    async def test_rejects_long_prospect(self):
        emp = self._emp()
        with pytest.raises(ValueError, match="too long"):
            await emp.draft_prospect_email("x" * 101, "Acme")

    @pytest.mark.asyncio
    async def test_rejects_long_company(self):
        emp = self._emp()
        with pytest.raises(ValueError, match="too long"):
            await emp.draft_prospect_email("Jane", "x" * 101)

    @pytest.mark.asyncio
    async def test_success_returns_content(self):
        emp = self._emp()
        emp._llm = _stub_llm("Hi Jane,")
        result = await emp.draft_prospect_email("Jane", "Acme", context={"industry": "saas"})
        assert "Hi" in result

    @pytest.mark.asyncio
    async def test_llm_failure_wraps_error(self):
        emp = self._emp()
        emp._llm = Mock()
        emp._llm.generate = AsyncMock(side_effect=RuntimeError("x"))
        with pytest.raises(LLMGenerationError):
            await emp.draft_prospect_email("Jane", "Acme")


# ---------------------------------------------------------------------------
# Recruiter.screen_candidate
# ---------------------------------------------------------------------------


class TestScreenCandidate:
    def _emp(self) -> Recruiter:
        return Recruiter(EmployeeConfig(name="T", role="recruiter", email="t@t.com"))

    @pytest.mark.asyncio
    async def test_rejects_empty_candidate(self):
        emp = self._emp()
        with pytest.raises(ValueError, match="candidate"):
            await emp.screen_candidate({}, "Senior Engineer")

    @pytest.mark.asyncio
    async def test_rejects_empty_role_description(self):
        emp = self._emp()
        with pytest.raises(ValueError, match="role_description"):
            await emp.screen_candidate({"name": "Alex"}, "   ")

    @pytest.mark.asyncio
    async def test_success_returns_expected_shape(self):
        emp = self._emp()
        emp._llm = _stub_llm("Strong fit")
        result = await emp.screen_candidate({"name": "Alex"}, "Senior Engineer")
        assert set(result.keys()) >= {"fit", "score", "notes"}
        assert result["fit"] in ("strong", "possible", "weak")

    @pytest.mark.asyncio
    async def test_llm_failure_returns_weak_fit(self):
        emp = self._emp()
        emp._llm = Mock()
        emp._llm.generate = AsyncMock(side_effect=RuntimeError("x"))
        result = await emp.screen_candidate({"name": "Alex"}, "Senior Engineer")
        assert result["fit"] == "weak"
        assert result["score"] == 0
        assert "screening_error" in result["notes"]


# ---------------------------------------------------------------------------
# Recruiter.draft_outreach_message
# ---------------------------------------------------------------------------


class TestDraftOutreachMessage:
    def _emp(self) -> Recruiter:
        return Recruiter(EmployeeConfig(name="T", role="recruiter", email="t@t.com"))

    @pytest.mark.asyncio
    async def test_rejects_empty_candidate_name(self):
        emp = self._emp()
        with pytest.raises(ValueError, match="candidate_name"):
            await emp.draft_outreach_message("   ", "Senior Engineer")

    @pytest.mark.asyncio
    async def test_rejects_empty_role_title(self):
        emp = self._emp()
        with pytest.raises(ValueError, match="role_title"):
            await emp.draft_outreach_message("Alex", "")

    @pytest.mark.asyncio
    async def test_rejects_long_candidate_name(self):
        emp = self._emp()
        with pytest.raises(ValueError, match="too long"):
            await emp.draft_outreach_message("x" * 101, "Senior Engineer")

    @pytest.mark.asyncio
    async def test_rejects_long_role_title(self):
        emp = self._emp()
        with pytest.raises(ValueError, match="too long"):
            await emp.draft_outreach_message("Alex", "x" * 101)

    @pytest.mark.asyncio
    async def test_success_returns_content(self):
        emp = self._emp()
        emp._llm = _stub_llm("Hi Alex,")
        result = await emp.draft_outreach_message("Alex", "Senior Engineer", context={"hook": "x"})
        assert "Hi" in result

    @pytest.mark.asyncio
    async def test_llm_failure_wraps_error(self):
        emp = self._emp()
        emp._llm = Mock()
        emp._llm.generate = AsyncMock(side_effect=RuntimeError("x"))
        with pytest.raises(LLMGenerationError):
            await emp.draft_outreach_message("Alex", "Senior Engineer")
