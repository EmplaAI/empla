"""
Tests for empla.employees.config module.

Tests employee configuration, goal config, and settings.
"""

import pytest
from uuid import uuid4
from pydantic import ValidationError

from empla.employees.config import (
    EmployeeConfig,
    GoalConfig,
    LLMSettings,
    LoopSettings,
    SALES_AE_DEFAULT_GOALS,
    CSM_DEFAULT_GOALS,
    PM_DEFAULT_GOALS,
)
from empla.employees.personality import Personality, Tone, CommunicationStyle


class TestGoalConfig:
    """Tests for GoalConfig model."""

    def test_minimal_goal(self):
        """Test creating goal with minimal config."""
        goal = GoalConfig(description="Test goal")
        assert goal.description == "Test goal"
        assert goal.goal_type == "achievement"
        assert goal.priority == 5
        assert goal.target == {}

    def test_full_goal(self):
        """Test creating goal with full config."""
        goal = GoalConfig(
            description="Close 10 deals",
            goal_type="achievement",
            priority=9,
            target={"metric": "deals_closed", "value": 10},
        )
        assert goal.description == "Close 10 deals"
        assert goal.goal_type == "achievement"
        assert goal.priority == 9
        assert goal.target["metric"] == "deals_closed"
        assert goal.target["value"] == 10

    def test_priority_validation_min(self):
        """Test priority minimum validation."""
        with pytest.raises(ValidationError):
            GoalConfig(description="Test", priority=0)

    def test_priority_validation_max(self):
        """Test priority maximum validation."""
        with pytest.raises(ValidationError):
            GoalConfig(description="Test", priority=11)

    def test_priority_boundary_values(self):
        """Test priority boundary values are valid."""
        low = GoalConfig(description="Low", priority=1)
        high = GoalConfig(description="High", priority=10)
        assert low.priority == 1
        assert high.priority == 10

    def test_goal_types(self):
        """Test different goal types."""
        achievement = GoalConfig(description="Test", goal_type="achievement")
        maintenance = GoalConfig(description="Test", goal_type="maintenance")
        prevention = GoalConfig(description="Test", goal_type="prevention")
        assert achievement.goal_type == "achievement"
        assert maintenance.goal_type == "maintenance"
        assert prevention.goal_type == "prevention"


class TestLoopSettings:
    """Tests for LoopSettings model."""

    def test_default_values(self):
        """Test default loop settings."""
        settings = LoopSettings()
        assert settings.cycle_interval_seconds == 300
        assert settings.strategic_planning_interval_hours == 24
        assert settings.reflection_interval_hours == 24
        assert settings.max_concurrent_intentions == 3
        assert settings.error_backoff_seconds == 60

    def test_custom_values(self):
        """Test custom loop settings."""
        settings = LoopSettings(
            cycle_interval_seconds=600,
            strategic_planning_interval_hours=12,
            reflection_interval_hours=6,
            max_concurrent_intentions=5,
            error_backoff_seconds=120,
        )
        assert settings.cycle_interval_seconds == 600
        assert settings.strategic_planning_interval_hours == 12
        assert settings.reflection_interval_hours == 6
        assert settings.max_concurrent_intentions == 5
        assert settings.error_backoff_seconds == 120

    def test_cycle_interval_minimum(self):
        """Test cycle interval minimum validation."""
        with pytest.raises(ValidationError):
            LoopSettings(cycle_interval_seconds=30)

    def test_cycle_interval_boundary(self):
        """Test cycle interval at minimum boundary."""
        settings = LoopSettings(cycle_interval_seconds=60)
        assert settings.cycle_interval_seconds == 60

    def test_max_concurrent_intentions_minimum(self):
        """Test max concurrent intentions minimum."""
        with pytest.raises(ValidationError):
            LoopSettings(max_concurrent_intentions=0)


class TestLLMSettings:
    """Tests for LLMSettings model."""

    def test_default_values(self):
        """Test default LLM settings."""
        settings = LLMSettings()
        assert settings.primary_model == "claude-sonnet-4-5"
        assert settings.fallback_model == "gpt-4.1"
        assert settings.temperature == 0.7
        assert settings.max_tokens == 4096

    def test_custom_values(self):
        """Test custom LLM settings."""
        settings = LLMSettings(
            primary_model="claude-opus-4",
            fallback_model=None,
            temperature=0.3,
            max_tokens=8192,
        )
        assert settings.primary_model == "claude-opus-4"
        assert settings.fallback_model is None
        assert settings.temperature == 0.3
        assert settings.max_tokens == 8192

    def test_temperature_validation_min(self):
        """Test temperature minimum validation."""
        with pytest.raises(ValidationError):
            LLMSettings(temperature=-0.1)

    def test_temperature_validation_max(self):
        """Test temperature maximum validation."""
        with pytest.raises(ValidationError):
            LLMSettings(temperature=2.5)

    def test_temperature_boundary_values(self):
        """Test temperature boundary values."""
        low = LLMSettings(temperature=0.0)
        high = LLMSettings(temperature=2.0)
        assert low.temperature == 0.0
        assert high.temperature == 2.0


class TestEmployeeConfig:
    """Tests for EmployeeConfig model."""

    def test_minimal_config(self):
        """Test creating config with minimal required fields."""
        config = EmployeeConfig(
            name="Jordan Chen",
            role="sales_ae",
            email="jordan@company.com",
        )
        assert config.name == "Jordan Chen"
        assert config.role == "sales_ae"
        assert config.email == "jordan@company.com"
        assert config.tenant_id is None
        assert config.personality is None
        assert config.goals == []
        assert config.capabilities == ["email"]
        assert isinstance(config.loop, LoopSettings)
        assert isinstance(config.llm, LLMSettings)
        assert config.metadata == {}

    def test_full_config(self):
        """Test creating config with all fields."""
        tenant_id = uuid4()
        personality = Personality(extraversion=0.9)
        goals = [GoalConfig(description="Test goal", priority=8)]

        config = EmployeeConfig(
            name="Sarah Mitchell",
            role="csm",
            email="sarah@company.com",
            tenant_id=tenant_id,
            personality=personality,
            goals=goals,
            capabilities=["email", "calendar", "crm"],
            loop=LoopSettings(cycle_interval_seconds=600),
            llm=LLMSettings(temperature=0.5),
            metadata={"team": "enterprise"},
        )

        assert config.name == "Sarah Mitchell"
        assert config.role == "csm"
        assert config.email == "sarah@company.com"
        assert config.tenant_id == tenant_id
        assert config.personality.extraversion == 0.9
        assert len(config.goals) == 1
        assert config.capabilities == ["email", "calendar", "crm"]
        assert config.loop.cycle_interval_seconds == 600
        assert config.llm.temperature == 0.5
        assert config.metadata["team"] == "enterprise"

    def test_name_required(self):
        """Test that name is required."""
        with pytest.raises(ValidationError):
            EmployeeConfig(role="sales_ae", email="test@test.com")

    def test_role_required(self):
        """Test that role is required."""
        with pytest.raises(ValidationError):
            EmployeeConfig(name="Test", email="test@test.com")

    def test_email_required(self):
        """Test that email is required."""
        with pytest.raises(ValidationError):
            EmployeeConfig(name="Test", role="sales_ae")

    def test_name_minimum_length(self):
        """Test name minimum length validation."""
        with pytest.raises(ValidationError):
            EmployeeConfig(name="", role="sales_ae", email="test@test.com")

    def test_to_db_config(self):
        """Test conversion to database config dict."""
        config = EmployeeConfig(
            name="Test",
            role="sales_ae",
            email="test@test.com",
            metadata={"key": "value"},
        )
        db_config = config.to_db_config()

        assert isinstance(db_config, dict)
        assert "loop" in db_config
        assert "llm" in db_config
        assert "metadata" in db_config
        assert db_config["metadata"]["key"] == "value"

    def test_to_db_personality_with_personality(self):
        """Test conversion to database personality dict."""
        personality = Personality(openness=0.8)
        config = EmployeeConfig(
            name="Test",
            role="sales_ae",
            email="test@test.com",
            personality=personality,
        )
        db_personality = config.to_db_personality()

        assert isinstance(db_personality, dict)
        assert db_personality["openness"] == 0.8

    def test_to_db_personality_without_personality(self):
        """Test conversion to database personality dict when no personality set."""
        config = EmployeeConfig(
            name="Test",
            role="sales_ae",
            email="test@test.com",
        )
        db_personality = config.to_db_personality()

        assert db_personality == {}


class TestDefaultGoals:
    """Tests for default goal configurations."""

    def test_sales_ae_default_goals_exist(self):
        """Test Sales AE default goals exist."""
        assert SALES_AE_DEFAULT_GOALS is not None
        assert len(SALES_AE_DEFAULT_GOALS) >= 1

    def test_sales_ae_default_goals_valid(self):
        """Test Sales AE default goals are valid GoalConfig instances."""
        for goal in SALES_AE_DEFAULT_GOALS:
            assert isinstance(goal, GoalConfig)
            assert goal.description
            assert 1 <= goal.priority <= 10

    def test_sales_ae_has_pipeline_goal(self):
        """Test Sales AE has pipeline-related goal."""
        descriptions = [g.description.lower() for g in SALES_AE_DEFAULT_GOALS]
        assert any("pipeline" in d for d in descriptions)

    def test_csm_default_goals_exist(self):
        """Test CSM default goals exist."""
        assert CSM_DEFAULT_GOALS is not None
        assert len(CSM_DEFAULT_GOALS) >= 1

    def test_csm_default_goals_valid(self):
        """Test CSM default goals are valid GoalConfig instances."""
        for goal in CSM_DEFAULT_GOALS:
            assert isinstance(goal, GoalConfig)
            assert goal.description
            assert 1 <= goal.priority <= 10

    def test_csm_has_retention_goal(self):
        """Test CSM has retention-related goal."""
        descriptions = [g.description.lower() for g in CSM_DEFAULT_GOALS]
        assert any("retention" in d for d in descriptions)

    def test_pm_default_goals_exist(self):
        """Test PM default goals exist."""
        assert PM_DEFAULT_GOALS is not None
        assert len(PM_DEFAULT_GOALS) >= 1

    def test_pm_default_goals_valid(self):
        """Test PM default goals are valid GoalConfig instances."""
        for goal in PM_DEFAULT_GOALS:
            assert isinstance(goal, GoalConfig)
            assert goal.description
            assert 1 <= goal.priority <= 10

    def test_goals_have_targets(self):
        """Test that default goals have meaningful targets."""
        all_goals = SALES_AE_DEFAULT_GOALS + CSM_DEFAULT_GOALS + PM_DEFAULT_GOALS
        goals_with_targets = [g for g in all_goals if g.target]
        # Most goals should have targets
        assert len(goals_with_targets) >= len(all_goals) // 2
