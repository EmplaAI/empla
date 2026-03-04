"""Tests for empla.employees.catalog — Role Catalog (single source of truth)."""

import pytest

from empla.employees.catalog import (
    ROLE_CATALOG,
    RoleDefinition,
    get_role,
    get_role_description,
    get_role_title,
    list_roles,
)
from empla.employees.config import (
    CSM_DEFAULT_GOALS,
    PM_DEFAULT_GOALS,
    SALES_AE_DEFAULT_GOALS,
)
from empla.employees.identity import ROLE_DESCRIPTIONS, ROLE_TITLES
from empla.employees.personality import (
    CSM_PERSONALITY,
    PM_PERSONALITY,
    SALES_AE_PERSONALITY,
    Personality,
)


class TestRoleCatalogStructure:
    """ROLE_CATALOG has the expected shape."""

    def test_catalog_is_nonempty(self) -> None:
        assert len(ROLE_CATALOG) >= 5

    @pytest.mark.parametrize("code", ["sales_ae", "csm", "pm", "sdr", "recruiter"])
    def test_all_built_in_roles_present(self, code: str) -> None:
        assert code in ROLE_CATALOG

    def test_role_definition_is_frozen(self) -> None:
        role = ROLE_CATALOG["sales_ae"]
        with pytest.raises(Exception):
            role.code = "modified"  # type: ignore[misc]

    def test_each_role_has_required_fields(self) -> None:
        for code, role in ROLE_CATALOG.items():
            assert role.code == code
            assert role.title
            assert role.description
            assert role.short_description
            assert isinstance(role.personality, Personality)
            assert isinstance(role.default_goals, list)
            assert isinstance(role.default_capabilities, list)


class TestGetRole:
    """Tests for get_role()."""

    def test_known_role(self) -> None:
        role = get_role("sales_ae")
        assert role is not None
        assert role.code == "sales_ae"

    def test_unknown_role_returns_none(self) -> None:
        assert get_role("nonexistent") is None


class TestGetRoleTitle:
    """Tests for get_role_title()."""

    def test_known_role(self) -> None:
        assert get_role_title("sales_ae") == "Sales Account Executive"

    def test_unknown_role_fallback(self) -> None:
        assert get_role_title("data_scientist") == "Data Scientist"


class TestGetRoleDescription:
    """Tests for get_role_description()."""

    def test_known_role(self) -> None:
        desc = get_role_description("csm")
        assert "customer success" in desc.lower()

    def test_unknown_role_fallback(self) -> None:
        desc = get_role_description("data_scientist")
        assert desc == "You work as a Data Scientist."


class TestListRoles:
    """Tests for list_roles()."""

    def test_returns_all_roles(self) -> None:
        roles = list_roles()
        assert len(roles) == len(ROLE_CATALOG)
        codes = {r.code for r in roles}
        assert codes == set(ROLE_CATALOG.keys())

    def test_returns_role_definition_instances(self) -> None:
        for role in list_roles():
            assert isinstance(role, RoleDefinition)


class TestBackwardsCompat:
    """Backwards-compat aliases are derived from the catalog."""

    def test_role_titles_match_catalog(self) -> None:
        for code, role in ROLE_CATALOG.items():
            assert ROLE_TITLES[code] == role.title

    def test_role_descriptions_match_catalog(self) -> None:
        for code, role in ROLE_CATALOG.items():
            assert ROLE_DESCRIPTIONS[code] == role.description

    def test_sales_ae_personality_matches_catalog(self) -> None:
        assert ROLE_CATALOG["sales_ae"].personality == SALES_AE_PERSONALITY

    def test_csm_personality_matches_catalog(self) -> None:
        assert ROLE_CATALOG["csm"].personality == CSM_PERSONALITY

    def test_pm_personality_matches_catalog(self) -> None:
        assert ROLE_CATALOG["pm"].personality == PM_PERSONALITY

    def test_sales_ae_goals_match_catalog(self) -> None:
        assert list(ROLE_CATALOG["sales_ae"].default_goals) == SALES_AE_DEFAULT_GOALS

    def test_csm_goals_match_catalog(self) -> None:
        assert list(ROLE_CATALOG["csm"].default_goals) == CSM_DEFAULT_GOALS

    def test_pm_goals_match_catalog(self) -> None:
        assert list(ROLE_CATALOG["pm"].default_goals) == PM_DEFAULT_GOALS


class TestPersonalityFromPreset:
    """Personality.from_preset() uses the catalog."""

    def test_known_preset_returns_deep_copy(self) -> None:
        p1 = Personality.from_preset("sales_ae")
        p2 = Personality.from_preset("sales_ae")
        assert p1 == p2
        assert p1 is not p2  # deep copy

    def test_known_preset_matches_catalog(self) -> None:
        p = Personality.from_preset("csm")
        assert p == ROLE_CATALOG["csm"].personality

    def test_unknown_preset_returns_default(self) -> None:
        p = Personality.from_preset("nonexistent")
        assert p == Personality()

    def test_sdr_has_default_personality(self) -> None:
        """SDR exists in catalog but uses default personality."""
        p = Personality.from_preset("sdr")
        assert p == Personality()


class TestNewRoles:
    """New roles (sdr, recruiter) are in the catalog."""

    def test_sdr_in_catalog(self) -> None:
        role = get_role("sdr")
        assert role is not None
        assert role.title == "Sales Development Representative"
        assert role.default_goals == []
        assert role.default_capabilities == ["email"]

    def test_recruiter_in_catalog(self) -> None:
        role = get_role("recruiter")
        assert role is not None
        assert role.title == "Recruiter"
        assert role.default_goals == []
        assert role.default_capabilities == ["email"]
