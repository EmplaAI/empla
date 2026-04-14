"""
Tests for empla.employees role implementations.

Tests SalesAE, CustomerSuccessManager, ProductManager, SDR, and Recruiter
employees.
"""

from empla.employees import (
    CSM,
    PM,
    SDR,
    CustomerSuccessManager,
    EmployeeConfig,
    ProductManager,
    Recruiter,
    SalesAE,
)
from empla.employees.catalog import get_role
from empla.employees.config import CSM_DEFAULT_GOALS, SALES_AE_DEFAULT_GOALS, GoalConfig
from empla.employees.personality import (
    CSM_PERSONALITY,
    SALES_AE_PERSONALITY,
    Formality,
    Personality,
    Tone,
    Verbosity,
)


class TestSalesAE:
    """Tests for SalesAE employee."""

    def test_creates_with_config(self):
        """Test SalesAE can be created with config."""
        config = EmployeeConfig(
            name="Jordan Chen",
            role="sales_ae",
            email="jordan@company.com",
        )
        employee = SalesAE(config)

        assert employee.name == "Jordan Chen"
        assert employee.role == "sales_ae"
        assert employee.email == "jordan@company.com"

    def test_default_personality(self):
        """Test SalesAE has correct default personality."""
        config = EmployeeConfig(
            name="Test",
            role="sales_ae",
            email="test@test.com",
        )
        employee = SalesAE(config)

        personality = employee.default_personality
        assert personality == SALES_AE_PERSONALITY
        assert personality.extraversion >= 0.8
        assert personality.communication.tone == Tone.ENTHUSIASTIC

    def test_default_goals(self):
        """Test SalesAE has correct default goals."""
        config = EmployeeConfig(
            name="Test",
            role="sales_ae",
            email="test@test.com",
        )
        employee = SalesAE(config)

        goals = employee.default_goals
        assert goals == SALES_AE_DEFAULT_GOALS
        assert len(goals) >= 1

        # Check for pipeline goal
        descriptions = [g.description.lower() for g in goals]
        assert any("pipeline" in d for d in descriptions)

    def test_default_capabilities(self):
        """Test SalesAE has correct default capabilities."""
        config = EmployeeConfig(
            name="Test",
            role="sales_ae",
            email="test@test.com",
        )
        employee = SalesAE(config)

        capabilities = employee.default_capabilities
        assert "email" in capabilities
        assert "calendar" in capabilities
        assert "crm" in capabilities

    def test_personality_override(self):
        """Test SalesAE allows personality override."""
        custom_personality = Personality(extraversion=0.5, agreeableness=0.9)
        config = EmployeeConfig(
            name="Test",
            role="sales_ae",
            email="test@test.com",
            personality=custom_personality,
        )
        employee = SalesAE(config)

        # Should use config personality, not default
        assert employee.personality.extraversion == 0.5
        assert employee.personality.agreeableness == 0.9

    def test_goals_override(self):
        """Test SalesAE allows goals override."""
        custom_goals = [
            GoalConfig(description="Custom goal", priority=10),
        ]
        config = EmployeeConfig(
            name="Test",
            role="sales_ae",
            email="test@test.com",
            goals=custom_goals,
        )
        employee = SalesAE(config)

        # Config goals should be used instead of default
        assert len(config.goals) == 1
        assert config.goals[0].description == "Custom goal"

    def test_capabilities_override(self):
        """Test SalesAE allows capabilities override."""
        config = EmployeeConfig(
            name="Test",
            role="sales_ae",
            email="test@test.com",
            capabilities=["email", "browser"],
        )
        employee = SalesAE(config)

        # Config capabilities should be used
        assert config.capabilities == ["email", "browser"]

    def test_is_subclass_of_digital_employee(self):
        """Test SalesAE is subclass of DigitalEmployee."""
        from empla.employees.base import DigitalEmployee

        config = EmployeeConfig(
            name="Test",
            role="sales_ae",
            email="test@test.com",
        )
        employee = SalesAE(config)

        assert isinstance(employee, DigitalEmployee)

    def test_repr(self):
        """Test SalesAE repr."""
        config = EmployeeConfig(
            name="Jordan Chen",
            role="sales_ae",
            email="jordan@test.com",
        )
        employee = SalesAE(config)
        repr_str = repr(employee)

        assert "SalesAE" in repr_str
        assert "Jordan Chen" in repr_str


class TestCustomerSuccessManager:
    """Tests for CustomerSuccessManager employee."""

    def test_creates_with_config(self):
        """Test CSM can be created with config."""
        config = EmployeeConfig(
            name="Sarah Mitchell",
            role="csm",
            email="sarah@company.com",
        )
        employee = CustomerSuccessManager(config)

        assert employee.name == "Sarah Mitchell"
        assert employee.role == "csm"
        assert employee.email == "sarah@company.com"

    def test_default_personality(self):
        """Test CSM has correct default personality."""
        config = EmployeeConfig(
            name="Test",
            role="csm",
            email="test@test.com",
        )
        employee = CustomerSuccessManager(config)

        personality = employee.default_personality
        assert personality == CSM_PERSONALITY
        assert personality.agreeableness >= 0.8
        assert personality.communication.tone == Tone.SUPPORTIVE

    def test_default_goals(self):
        """Test CSM has correct default goals."""
        config = EmployeeConfig(
            name="Test",
            role="csm",
            email="test@test.com",
        )
        employee = CustomerSuccessManager(config)

        goals = employee.default_goals
        assert goals == CSM_DEFAULT_GOALS
        assert len(goals) >= 1

        # Check for retention goal
        descriptions = [g.description.lower() for g in goals]
        assert any("retention" in d for d in descriptions)

    def test_default_capabilities(self):
        """Test CSM has correct default capabilities."""
        config = EmployeeConfig(
            name="Test",
            role="csm",
            email="test@test.com",
        )
        employee = CustomerSuccessManager(config)

        capabilities = employee.default_capabilities
        assert "email" in capabilities
        assert "calendar" in capabilities
        assert "crm" in capabilities

    def test_is_subclass_of_digital_employee(self):
        """Test CSM is subclass of DigitalEmployee."""
        from empla.employees.base import DigitalEmployee

        config = EmployeeConfig(
            name="Test",
            role="csm",
            email="test@test.com",
        )
        employee = CustomerSuccessManager(config)

        assert isinstance(employee, DigitalEmployee)

    def test_repr(self):
        """Test CSM repr."""
        config = EmployeeConfig(
            name="Sarah Mitchell",
            role="csm",
            email="sarah@test.com",
        )
        employee = CustomerSuccessManager(config)
        repr_str = repr(employee)

        assert "CustomerSuccessManager" in repr_str
        assert "Sarah Mitchell" in repr_str


class TestCSMAlias:
    """Tests for CSM alias."""

    def test_csm_alias_exists(self):
        """Test CSM alias is available."""
        assert CSM is CustomerSuccessManager

    def test_csm_alias_creates_same_type(self):
        """Test CSM alias creates CustomerSuccessManager."""
        config = EmployeeConfig(
            name="Test",
            role="csm",
            email="test@test.com",
        )
        employee = CSM(config)

        assert isinstance(employee, CustomerSuccessManager)


class TestRolePersonalityDifferences:
    """Tests ensuring role personalities are appropriately different."""

    def test_sales_ae_more_extraverted(self):
        """Test Sales AE is more extraverted than CSM."""
        sales_config = EmployeeConfig(name="Sales", role="sales_ae", email="s@t.com")
        csm_config = EmployeeConfig(name="CSM", role="csm", email="c@t.com")

        sales = SalesAE(sales_config)
        csm = CustomerSuccessManager(csm_config)

        assert sales.default_personality.extraversion > csm.default_personality.extraversion

    def test_csm_more_agreeable(self):
        """Test CSM is more agreeable than Sales AE."""
        sales_config = EmployeeConfig(name="Sales", role="sales_ae", email="s@t.com")
        csm_config = EmployeeConfig(name="CSM", role="csm", email="c@t.com")

        sales = SalesAE(sales_config)
        csm = CustomerSuccessManager(csm_config)

        assert csm.default_personality.agreeableness > sales.default_personality.agreeableness

    def test_sales_ae_higher_risk_tolerance(self):
        """Test Sales AE has higher risk tolerance than CSM."""
        sales_config = EmployeeConfig(name="Sales", role="sales_ae", email="s@t.com")
        csm_config = EmployeeConfig(name="CSM", role="csm", email="c@t.com")

        sales = SalesAE(sales_config)
        csm = CustomerSuccessManager(csm_config)

        sales_risk = sales.default_personality.decision_style.risk_tolerance
        csm_risk = csm.default_personality.decision_style.risk_tolerance

        assert sales_risk > csm_risk

    def test_different_communication_tones(self):
        """Test Sales AE and CSM have different communication tones."""
        sales_config = EmployeeConfig(name="Sales", role="sales_ae", email="s@t.com")
        csm_config = EmployeeConfig(name="CSM", role="csm", email="c@t.com")

        sales = SalesAE(sales_config)
        csm = CustomerSuccessManager(csm_config)

        sales_tone = sales.default_personality.communication.tone
        csm_tone = csm.default_personality.communication.tone

        # Sales should be enthusiastic, CSM should be supportive
        assert sales_tone == Tone.ENTHUSIASTIC
        assert csm_tone == Tone.SUPPORTIVE


class TestRoleGoalDifferences:
    """Tests ensuring role goals are appropriately different."""

    def test_sales_ae_has_pipeline_goals(self):
        """Test Sales AE goals focus on pipeline and deals."""
        config = EmployeeConfig(name="Test", role="sales_ae", email="t@t.com")
        employee = SalesAE(config)

        goal_texts = " ".join([g.description.lower() for g in employee.default_goals])

        # Should mention pipeline, deals, leads, or similar sales concepts
        sales_keywords = ["pipeline", "deal", "lead", "win", "quota", "close"]
        assert any(keyword in goal_texts for keyword in sales_keywords)

    def test_csm_has_retention_goals(self):
        """Test CSM goals focus on retention and customer success."""
        config = EmployeeConfig(name="Test", role="csm", email="t@t.com")
        employee = CustomerSuccessManager(config)

        goal_texts = " ".join([g.description.lower() for g in employee.default_goals])

        # Should mention retention, NPS, customer, onboarding, or similar CS concepts
        cs_keywords = ["retention", "nps", "customer", "onboarding", "satisfaction", "churn"]
        assert any(keyword in goal_texts for keyword in cs_keywords)

    def test_roles_have_different_goals(self):
        """Test that SalesAE and CSM have meaningfully different goals."""
        sales_config = EmployeeConfig(name="Sales", role="sales_ae", email="s@t.com")
        csm_config = EmployeeConfig(name="CSM", role="csm", email="c@t.com")

        sales = SalesAE(sales_config)
        csm = CustomerSuccessManager(csm_config)

        sales_descriptions = set(g.description for g in sales.default_goals)
        csm_descriptions = set(g.description for g in csm.default_goals)

        # Goals should be completely different
        assert sales_descriptions != csm_descriptions
        # No overlap
        assert len(sales_descriptions & csm_descriptions) == 0


# ---------------------------------------------------------------------------
# ProductManager
# ---------------------------------------------------------------------------


class TestProductManager:
    """Tests for ProductManager employee."""

    def test_creates_with_config(self):
        config = EmployeeConfig(name="Morgan Park", role="pm", email="morgan@co.com")
        employee = ProductManager(config)
        assert employee.name == "Morgan Park"
        assert employee.role == "pm"

    def test_default_personality_from_catalog(self):
        config = EmployeeConfig(name="Test", role="pm", email="t@t.com")
        employee = ProductManager(config)
        expected = get_role("pm").personality
        assert employee.default_personality == expected
        assert employee.default_personality.communication.tone == Tone.PROFESSIONAL
        assert employee.default_personality.communication.formality == Formality.PROFESSIONAL

    def test_default_goals_from_catalog(self):
        config = EmployeeConfig(name="Test", role="pm", email="t@t.com")
        employee = ProductManager(config)
        goals = employee.default_goals
        assert len(goals) >= 1
        text = " ".join(g.description.lower() for g in goals)
        assert any(k in text for k in ["feature", "ship", "release", "satisfaction"])

    def test_default_capabilities_from_catalog(self):
        config = EmployeeConfig(name="Test", role="pm", email="t@t.com")
        employee = ProductManager(config)
        caps = employee.default_capabilities
        assert "email" in caps
        assert "calendar" in caps

    def test_personality_override(self):
        custom = Personality(extraversion=0.1, openness=0.2)
        config = EmployeeConfig(name="Test", role="pm", email="t@t.com", personality=custom)
        employee = ProductManager(config)
        assert employee.personality.extraversion == 0.1
        assert employee.personality.openness == 0.2

    def test_goals_override(self):
        custom = [GoalConfig(description="Custom PM goal", priority=10)]
        config = EmployeeConfig(name="Test", role="pm", email="t@t.com", goals=custom)
        employee = ProductManager(config)
        assert config.goals == custom

    def test_capabilities_override(self):
        config = EmployeeConfig(name="Test", role="pm", email="t@t.com", capabilities=["email"])
        employee = ProductManager(config)
        assert config.capabilities == ["email"]

    def test_is_subclass_of_digital_employee(self):
        from empla.employees.base import DigitalEmployee

        config = EmployeeConfig(name="Test", role="pm", email="t@t.com")
        employee = ProductManager(config)
        assert isinstance(employee, DigitalEmployee)

    def test_is_catalog_backed(self):
        from empla.employees.catalog_backed import CatalogBackedEmployee

        config = EmployeeConfig(name="Test", role="pm", email="t@t.com")
        employee = ProductManager(config)
        assert isinstance(employee, CatalogBackedEmployee)

    def test_repr(self):
        config = EmployeeConfig(name="Morgan Park", role="pm", email="m@t.com")
        employee = ProductManager(config)
        repr_str = repr(employee)
        assert "ProductManager" in repr_str
        assert "Morgan Park" in repr_str


class TestPMAlias:
    def test_pm_alias_is_product_manager(self):
        assert PM is ProductManager

    def test_pm_alias_creates_same_type(self):
        config = EmployeeConfig(name="Test", role="pm", email="t@t.com")
        employee = PM(config)
        assert isinstance(employee, ProductManager)


# ---------------------------------------------------------------------------
# SDR
# ---------------------------------------------------------------------------


class TestSDR:
    """Tests for SDR employee."""

    def test_creates_with_config(self):
        config = EmployeeConfig(name="Taylor Reyes", role="sdr", email="taylor@co.com")
        employee = SDR(config)
        assert employee.name == "Taylor Reyes"
        assert employee.role == "sdr"

    def test_default_personality_from_catalog(self):
        config = EmployeeConfig(name="Test", role="sdr", email="t@t.com")
        employee = SDR(config)
        expected = get_role("sdr").personality
        assert employee.default_personality == expected
        assert employee.default_personality.communication.tone == Tone.ENTHUSIASTIC
        assert employee.default_personality.communication.verbosity == Verbosity.CONCISE
        # SDRs should be highly proactive
        assert employee.default_personality.proactivity >= 0.9

    def test_default_goals_from_catalog(self):
        config = EmployeeConfig(name="Test", role="sdr", email="t@t.com")
        employee = SDR(config)
        goals = employee.default_goals
        assert len(goals) >= 1
        text = " ".join(g.description.lower() for g in goals)
        assert any(k in text for k in ["meeting", "lead", "outbound", "inbound"])

    def test_default_capabilities_from_catalog(self):
        config = EmployeeConfig(name="Test", role="sdr", email="t@t.com")
        employee = SDR(config)
        caps = employee.default_capabilities
        assert "email" in caps
        assert "calendar" in caps
        assert "crm" in caps

    def test_personality_override(self):
        custom = Personality(extraversion=0.2)
        config = EmployeeConfig(name="Test", role="sdr", email="t@t.com", personality=custom)
        employee = SDR(config)
        assert employee.personality.extraversion == 0.2

    def test_goals_override(self):
        custom = [GoalConfig(description="Custom SDR goal", priority=10)]
        config = EmployeeConfig(name="Test", role="sdr", email="t@t.com", goals=custom)
        employee = SDR(config)
        assert config.goals == custom

    def test_capabilities_override(self):
        config = EmployeeConfig(name="Test", role="sdr", email="t@t.com", capabilities=["email"])
        employee = SDR(config)
        assert config.capabilities == ["email"]

    def test_is_subclass_of_digital_employee(self):
        from empla.employees.base import DigitalEmployee

        config = EmployeeConfig(name="Test", role="sdr", email="t@t.com")
        employee = SDR(config)
        assert isinstance(employee, DigitalEmployee)

    def test_repr(self):
        config = EmployeeConfig(name="Taylor Reyes", role="sdr", email="t@t.com")
        employee = SDR(config)
        repr_str = repr(employee)
        assert "SDR" in repr_str
        assert "Taylor Reyes" in repr_str


# ---------------------------------------------------------------------------
# Recruiter
# ---------------------------------------------------------------------------


class TestRecruiter:
    """Tests for Recruiter employee."""

    def test_creates_with_config(self):
        config = EmployeeConfig(name="Alex Kim", role="recruiter", email="alex@co.com")
        employee = Recruiter(config)
        assert employee.name == "Alex Kim"
        assert employee.role == "recruiter"

    def test_default_personality_from_catalog(self):
        config = EmployeeConfig(name="Test", role="recruiter", email="t@t.com")
        employee = Recruiter(config)
        expected = get_role("recruiter").personality
        assert employee.default_personality == expected
        assert employee.default_personality.communication.tone == Tone.SUPPORTIVE
        # Recruiters need high agreeableness
        assert employee.default_personality.agreeableness >= 0.8

    def test_default_goals_from_catalog(self):
        config = EmployeeConfig(name="Test", role="recruiter", email="t@t.com")
        employee = Recruiter(config)
        goals = employee.default_goals
        assert len(goals) >= 1
        text = " ".join(g.description.lower() for g in goals)
        assert any(k in text for k in ["candidate", "requisition", "hire", "fill"])

    def test_default_capabilities_from_catalog(self):
        config = EmployeeConfig(name="Test", role="recruiter", email="t@t.com")
        employee = Recruiter(config)
        caps = employee.default_capabilities
        assert "email" in caps
        assert "calendar" in caps

    def test_personality_override(self):
        custom = Personality(agreeableness=0.1)
        config = EmployeeConfig(name="Test", role="recruiter", email="t@t.com", personality=custom)
        employee = Recruiter(config)
        assert employee.personality.agreeableness == 0.1

    def test_goals_override(self):
        custom = [GoalConfig(description="Custom recruiting goal", priority=10)]
        config = EmployeeConfig(name="Test", role="recruiter", email="t@t.com", goals=custom)
        employee = Recruiter(config)
        assert config.goals == custom

    def test_capabilities_override(self):
        config = EmployeeConfig(
            name="Test", role="recruiter", email="t@t.com", capabilities=["email"]
        )
        employee = Recruiter(config)
        assert config.capabilities == ["email"]

    def test_is_subclass_of_digital_employee(self):
        from empla.employees.base import DigitalEmployee

        config = EmployeeConfig(name="Test", role="recruiter", email="t@t.com")
        employee = Recruiter(config)
        assert isinstance(employee, DigitalEmployee)

    def test_repr(self):
        config = EmployeeConfig(name="Alex Kim", role="recruiter", email="a@t.com")
        employee = Recruiter(config)
        repr_str = repr(employee)
        assert "Recruiter" in repr_str
        assert "Alex Kim" in repr_str


# ---------------------------------------------------------------------------
# Cross-role differentiation (5 roles)
# ---------------------------------------------------------------------------


class TestAllRolesDifferentiated:
    """Cross-role sanity checks to catch catalog mis-copies."""

    def _make_all(self) -> dict[str, object]:
        return {
            "sales_ae": SalesAE(EmployeeConfig(name="S", role="sales_ae", email="s@t.com")),
            "csm": CustomerSuccessManager(EmployeeConfig(name="C", role="csm", email="c@t.com")),
            "pm": ProductManager(EmployeeConfig(name="P", role="pm", email="p@t.com")),
            "sdr": SDR(EmployeeConfig(name="D", role="sdr", email="d@t.com")),
            "recruiter": Recruiter(EmployeeConfig(name="R", role="recruiter", email="r@t.com")),
        }

    def test_each_role_has_non_empty_goals(self):
        for code, emp in self._make_all().items():
            assert len(emp.default_goals) > 0, f"{code} has no default goals"

    def test_each_role_has_email_capability(self):
        for code, emp in self._make_all().items():
            assert "email" in emp.default_capabilities, f"{code} missing email capability"

    def test_goal_descriptions_unique_per_role(self):
        all_emps = self._make_all()
        descs_by_role = {
            code: {g.description for g in emp.default_goals} for code, emp in all_emps.items()
        }
        # No two roles should share any goal description
        codes = list(descs_by_role.keys())
        for i, a in enumerate(codes):
            for b in codes[i + 1 :]:
                overlap = descs_by_role[a] & descs_by_role[b]
                assert not overlap, f"{a} and {b} share goals: {overlap}"

    def test_focus_keywords_unique_per_role(self):
        """Guards against catalog copy-paste bugs on focus_keyword."""
        focuses = {code: get_role(code).focus_keyword for code in self._make_all()}
        assert len(set(focuses.values())) == len(focuses), f"focus_keyword collision: {focuses}"
        for code, focus in focuses.items():
            assert focus, f"{code} missing focus_keyword"

    def test_personalities_unique_per_role(self):
        """Guards against catalog copy-paste bugs on personality."""
        all_emps = self._make_all()
        personalities = {code: emp.default_personality for code, emp in all_emps.items()}
        codes = list(personalities.keys())
        for i, a in enumerate(codes):
            for b in codes[i + 1 :]:
                assert personalities[a] != personalities[b], (
                    f"{a} and {b} have identical personalities — likely copy-paste"
                )
