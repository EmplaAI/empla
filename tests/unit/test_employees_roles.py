"""
Tests for empla.employees role implementations.

Tests SalesAE and CustomerSuccessManager employees.
"""

from empla.employees import (
    CSM,
    CustomerSuccessManager,
    EmployeeConfig,
    SalesAE,
)
from empla.employees.config import CSM_DEFAULT_GOALS, SALES_AE_DEFAULT_GOALS, GoalConfig
from empla.employees.personality import (
    CSM_PERSONALITY,
    SALES_AE_PERSONALITY,
    Personality,
    Tone,
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
