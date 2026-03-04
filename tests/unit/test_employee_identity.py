"""Tests for empla.employees.identity — EmployeeIdentity system."""

import pytest

from empla.employees.identity import (
    ROLE_DESCRIPTIONS,
    ROLE_TITLES,
    EmployeeIdentity,
)


class TestEmployeeIdentityBuild:
    """Tests for EmployeeIdentity.build() factory."""

    def test_build_sales_ae(self) -> None:
        identity = EmployeeIdentity.build(
            name="Jordan Chen",
            role="sales_ae",
            personality_prompt="outgoing and energetic, highly organized",
            goals=[
                {"description": "Maintain 3x pipeline coverage", "priority": 9},
                {"description": "Respond to leads within 4 hours", "priority": 8},
            ],
            capabilities=["email", "calendar", "crm"],
        )

        assert identity.name == "Jordan Chen"
        assert identity.role == "sales_ae"
        assert identity.role_title == "Sales Account Executive"
        assert identity.role_description == ROLE_DESCRIPTIONS["sales_ae"]
        assert identity.personality_prompt == "outgoing and energetic, highly organized"
        assert identity.capabilities == ["email", "calendar", "crm"]

    def test_build_unknown_role_fallback(self) -> None:
        identity = EmployeeIdentity.build(
            name="Alex Test",
            role="data_scientist",
        )

        assert identity.role_title == "Data Scientist"
        assert "data_scientist" not in ROLE_TITLES
        assert identity.role_description == "You work as a Data Scientist."

    def test_build_custom_role_description(self) -> None:
        custom_desc = "You analyze market trends and build forecasting models."
        identity = EmployeeIdentity.build(
            name="Taylor",
            role="sales_ae",
            role_description=custom_desc,
        )

        assert identity.role_description == custom_desc
        # Should NOT use the default sales_ae description
        assert identity.role_description != ROLE_DESCRIPTIONS["sales_ae"]

    def test_build_empty_goals(self) -> None:
        identity = EmployeeIdentity.build(
            name="Test",
            role="pm",
            goals=[],
        )

        assert identity.goals_summary == "No specific goals set."

    def test_build_none_goals(self) -> None:
        identity = EmployeeIdentity.build(
            name="Test",
            role="pm",
            goals=None,
        )

        assert identity.goals_summary == "No specific goals set."

    def test_build_default_personality(self) -> None:
        identity = EmployeeIdentity.build(
            name="Test",
            role="csm",
        )

        assert identity.personality_prompt == "balanced and professional"

    def test_build_whitespace_role_description_falls_back(self) -> None:
        identity = EmployeeIdentity.build(
            name="Test",
            role="sales_ae",
            role_description="   ",
        )

        assert identity.role_description == ROLE_DESCRIPTIONS["sales_ae"]

    def test_build_whitespace_personality_prompt_falls_back(self) -> None:
        identity = EmployeeIdentity.build(
            name="Test",
            role="csm",
            personality_prompt="   ",
        )

        assert identity.personality_prompt == "balanced and professional"


class TestEmployeeIdentityPrompt:
    """Tests for EmployeeIdentity.to_system_prompt()."""

    def test_contains_name_and_role(self) -> None:
        identity = EmployeeIdentity.build(
            name="Jordan Chen",
            role="sales_ae",
            personality_prompt="outgoing",
            goals=[{"description": "Maintain pipeline", "priority": 9}],
            capabilities=["email"],
        )
        prompt = identity.to_system_prompt()

        assert "Jordan Chen" in prompt
        assert "Sales Account Executive" in prompt

    def test_contains_goals(self) -> None:
        identity = EmployeeIdentity.build(
            name="Jordan",
            role="sales_ae",
            goals=[
                {"description": "Maintain 3x pipeline coverage", "priority": 9},
                {"description": "Respond to leads within 4 hours", "priority": 8},
            ],
        )
        prompt = identity.to_system_prompt()

        assert "[9/10] Maintain 3x pipeline coverage" in prompt
        assert "[8/10] Respond to leads within 4 hours" in prompt

    def test_contains_personality(self) -> None:
        identity = EmployeeIdentity.build(
            name="Jordan",
            role="sales_ae",
            personality_prompt="outgoing and energetic, highly organized",
        )
        prompt = identity.to_system_prompt()

        assert "outgoing and energetic" in prompt

    def test_contains_capabilities(self) -> None:
        identity = EmployeeIdentity.build(
            name="Test",
            role="csm",
            capabilities=["email", "calendar", "crm"],
        )
        prompt = identity.to_system_prompt()

        assert "email, calendar, crm" in prompt

    def test_no_capabilities(self) -> None:
        identity = EmployeeIdentity.build(
            name="Test",
            role="csm",
            capabilities=[],
        )
        prompt = identity.to_system_prompt()

        assert "Available capabilities: none" in prompt

    def test_no_goals_message(self) -> None:
        identity = EmployeeIdentity.build(
            name="Test",
            role="pm",
            goals=[],
        )
        prompt = identity.to_system_prompt()

        assert "No specific goals set." in prompt

    def test_contains_role_description(self) -> None:
        identity = EmployeeIdentity.build(
            name="Test",
            role="sales_ae",
        )
        prompt = identity.to_system_prompt()

        assert ROLE_DESCRIPTIONS["sales_ae"] in prompt


class TestRoleMappings:
    """Tests for ROLE_TITLES and ROLE_DESCRIPTIONS constants."""

    @pytest.mark.parametrize("role", ["sales_ae", "csm", "pm", "sdr", "recruiter"])
    def test_all_built_in_roles_have_title(self, role: str) -> None:
        assert role in ROLE_TITLES

    @pytest.mark.parametrize("role", ["sales_ae", "csm", "pm", "sdr", "recruiter"])
    def test_all_built_in_roles_have_description(self, role: str) -> None:
        assert role in ROLE_DESCRIPTIONS

    def test_titles_and_descriptions_same_keys(self) -> None:
        assert set(ROLE_TITLES.keys()) == set(ROLE_DESCRIPTIONS.keys())
