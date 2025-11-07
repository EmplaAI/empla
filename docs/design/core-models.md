# Core Models Design

> **Status:** Draft
> **Author:** Claude Code
> **Date:** 2025-10-27
> **Phase:** Phase 1 - Core Infrastructure

---

## Overview

This document defines all Pydantic models for empla's core system. These models provide:
- **Type safety** - Catch bugs at development time
- **Validation** - Ensure data integrity at API boundaries
- **Serialization** - JSON/dict conversion for API responses
- **Documentation** - Auto-generated API docs via OpenAPI

**Design Principles:**
1. **Strict validation** - Validate all inputs at boundaries
2. **Immutability where possible** - Use `frozen=True` for value objects
3. **Clear field descriptions** - Every field has `description` for docs
4. **Sensible defaults** - Required fields vs optional with defaults
5. **Custom validators** - Business logic validation (email format, priority range, etc.)
6. **Separate DB/API models** - Database models vs API request/response models

---

## Model Categories

### 1. Base Models
- `TimestampedModel` - Created/updated timestamps
- `SoftDeletableModel` - Soft delete support
- `TenantScopedModel` - Multi-tenant isolation

### 2. Domain Models
- `Employee` - Digital employee
- `EmployeeGoal` - BDI Desire
- `EmployeeIntention` - BDI Intention
- `Belief` - World model belief

### 3. Memory Models
- `EpisodicMemory` - Event/interaction memory
- `SemanticMemory` - Fact/knowledge memory
- `ProceduralMemory` - Skill/workflow memory
- `WorkingMemory` - Current context memory

### 4. Supporting Models
- `Tenant` - Customer organization
- `User` - Human user
- `AuditLogEntry` - Audit log record
- `Metric` - Performance metric

---

## Base Models

```python
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class EmplaBaseModel(BaseModel):
    """
    Base model for all empla models.

    Provides:
    - UUID generation for `id` field
    - Pydantic v2 configuration
    - JSON serialization utilities
    """

    model_config = ConfigDict(
        # Allow arbitrary types (e.g., UUID, datetime)
        arbitrary_types_allowed=True,
        # Validate on assignment (catch bugs early)
        validate_assignment=True,
        # Use enums by value in JSON
        use_enum_values=True,
        # Strict mode for better type safety
        str_strip_whitespace=True,
        # Allow populating by field name
        populate_by_name=True,
    )


class TimestampedModel(EmplaBaseModel):
    """Model with automatic timestamps."""

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this record was created (UTC)"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this record was last updated (UTC)"
    )


class SoftDeletableModel(TimestampedModel):
    """Model with soft delete support."""

    deleted_at: Optional[datetime] = Field(
        default=None,
        description="When this record was soft-deleted (UTC), None if active"
    )

    @property
    def is_deleted(self) -> bool:
        """Check if this record is soft-deleted."""
        return self.deleted_at is not None


class TenantScopedModel(SoftDeletableModel):
    """Model scoped to a tenant (multi-tenancy)."""

    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier"
    )
    tenant_id: UUID = Field(
        description="Tenant this record belongs to"
    )
```

---

## Tenant & User Models

```python
from enum import Enum
from typing import Dict, Any

from pydantic import EmailStr, Field, field_validator


class TenantStatus(str, Enum):
    """Tenant account status."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class Tenant(TenantScopedModel):
    """
    Customer organization.

    Example:
        >>> tenant = Tenant(
        ...     name="Acme Corporation",
        ...     slug="acme-corp",
        ...     settings={"llm_model": "claude-3-7-sonnet-20250219"}
        ... )
    """

    name: str = Field(
        min_length=1,
        max_length=200,
        description="Organization display name"
    )
    slug: str = Field(
        min_length=1,
        max_length=50,
        description="URL-safe identifier (e.g., 'acme-corp')"
    )
    settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tenant-specific configuration (LLM preferences, branding, etc.)"
    )
    status: TenantStatus = Field(
        default=TenantStatus.ACTIVE,
        description="Account status"
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Ensure slug is URL-safe."""
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Slug must be alphanumeric with hyphens/underscores only")
        if not v.islower():
            raise ValueError("Slug must be lowercase")
        return v


class UserRole(str, Enum):
    """User authorization role."""
    ADMIN = "admin"      # Full access
    MANAGER = "manager"  # Manage employees, read-only audit logs
    USER = "user"        # Read-only access to assigned employees


class User(TenantScopedModel):
    """
    Human user.

    Example:
        >>> user = User(
        ...     tenant_id=tenant.id,
        ...     email="jane@acme.com",
        ...     name="Jane Smith",
        ...     role=UserRole.ADMIN
        ... )
    """

    email: EmailStr = Field(
        description="User email address (must be unique within tenant)"
    )
    name: str = Field(
        min_length=1,
        max_length=200,
        description="User display name"
    )
    role: UserRole = Field(
        description="Authorization role"
    )
    settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="User preferences (notifications, UI settings, etc.)"
    )
```

---

## Employee Models

```python
from typing import List, Optional


class EmployeeRole(str, Enum):
    """Pre-built employee roles."""
    SALES_AE = "sales_ae"              # Account Executive
    SDR = "sdr"                        # Sales Development Rep
    CSM = "csm"                        # Customer Success Manager
    PM = "pm"                          # Product Manager
    RECRUITER = "recruiter"            # Technical Recruiter
    CUSTOM = "custom"                  # Custom role


class EmployeeStatus(str, Enum):
    """Employee operational status."""
    ONBOARDING = "onboarding"  # Being set up, not yet active
    ACTIVE = "active"          # Running proactive loop
    PAUSED = "paused"          # Temporarily stopped
    TERMINATED = "terminated"  # Permanently deactivated


class EmployeeLifecycleStage(str, Enum):
    """Employee learning progression."""
    SHADOW = "shadow"          # Observing human mentor
    SUPERVISED = "supervised"  # Acting with human approval
    AUTONOMOUS = "autonomous"  # Acting independently


class EmployeePersonality(EmplaBaseModel):
    """
    Employee personality traits.

    Influences communication style, decision-making, risk tolerance.

    Example:
        >>> personality = EmployeePersonality(
        ...     tone="professional",
        ...     risk_tolerance="moderate",
        ...     communication_style="direct",
        ...     traits=["persistent", "analytical", "empathetic"]
        ... )
    """

    tone: str = Field(
        default="professional",
        description="Communication tone (professional, casual, formal, friendly)"
    )
    risk_tolerance: str = Field(
        default="moderate",
        description="Risk tolerance (conservative, moderate, aggressive)"
    )
    communication_style: str = Field(
        default="balanced",
        description="Communication approach (concise, detailed, direct, diplomatic)"
    )
    traits: List[str] = Field(
        default_factory=list,
        description="Personality traits (persistent, analytical, creative, empathetic)"
    )


class EmployeeConfig(EmplaBaseModel):
    """
    Employee configuration.

    Example:
        >>> config = EmployeeConfig(
        ...     loop_interval_seconds=300,
        ...     llm_model="claude-3-7-sonnet-20250219",
        ...     max_concurrent_tasks=5
        ... )
    """

    loop_interval_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Proactive loop interval (60-3600 seconds)"
    )
    llm_model: str = Field(
        default="claude-3-7-sonnet-20250219",
        description="LLM model to use"
    )
    max_concurrent_tasks: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum concurrent tasks (1-20)"
    )
    working_hours: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Working hours configuration (timezone, start, end)"
    )


class EmployeePerformanceMetrics(EmplaBaseModel):
    """
    Employee performance metrics.

    Example:
        >>> metrics = EmployeePerformanceMetrics(
        ...     goals_achieved=10,
        ...     tasks_completed=50,
        ...     average_goal_completion_time_hours=48.5
        ... )
    """

    goals_achieved: int = Field(
        default=0,
        ge=0,
        description="Total goals achieved"
    )
    tasks_completed: int = Field(
        default=0,
        ge=0,
        description="Total tasks completed"
    )
    average_goal_completion_time_hours: float = Field(
        default=0.0,
        ge=0,
        description="Average time to complete a goal (hours)"
    )
    success_rate: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Overall success rate (0-1)"
    )


class Employee(TenantScopedModel):
    """
    Digital employee.

    Example:
        >>> employee = Employee(
        ...     tenant_id=tenant.id,
        ...     name="Jordan Chen",
        ...     role=EmployeeRole.SALES_AE,
        ...     email="jordan.chen@acme-corp.com",
        ...     personality=EmployeePersonality(traits=["persistent", "analytical"]),
        ...     status=EmployeeStatus.ACTIVE,
        ...     lifecycle_stage=EmployeeLifecycleStage.AUTONOMOUS
        ... )
    """

    # Identity
    name: str = Field(
        min_length=2,
        max_length=200,
        description="Employee display name"
    )
    role: EmployeeRole = Field(
        description="Employee role"
    )
    email: EmailStr = Field(
        description="Employee email address (must be unique within tenant)"
    )
    personality: EmployeePersonality = Field(
        default_factory=EmployeePersonality,
        description="Personality traits"
    )

    # Lifecycle
    status: EmployeeStatus = Field(
        default=EmployeeStatus.ONBOARDING,
        description="Operational status"
    )
    lifecycle_stage: EmployeeLifecycleStage = Field(
        default=EmployeeLifecycleStage.SHADOW,
        description="Learning progression stage"
    )
    onboarded_at: Optional[datetime] = Field(
        default=None,
        description="When onboarding completed (UTC)"
    )
    activated_at: Optional[datetime] = Field(
        default=None,
        description="When employee was activated (UTC)"
    )

    # Configuration
    config: EmployeeConfig = Field(
        default_factory=EmployeeConfig,
        description="Employee configuration"
    )
    capabilities: List[str] = Field(
        default_factory=list,
        description="Enabled capabilities (email, calendar, research, etc.)"
    )

    # Performance
    performance_metrics: EmployeePerformanceMetrics = Field(
        default_factory=EmployeePerformanceMetrics,
        description="Performance metrics"
    )

    # Audit
    created_by: Optional[UUID] = Field(
        default=None,
        description="User who created this employee"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is not empty after stripping."""
        if not v.strip():
            raise ValueError("Name cannot be empty")
        return v
```

---

## BDI Models

```python
class GoalType(str, Enum):
    """BDI goal/desire type."""
    ACHIEVEMENT = "achievement"  # Reach a target state
    MAINTENANCE = "maintenance"  # Maintain a state
    PREVENTION = "prevention"    # Avoid a state


class GoalStatus(str, Enum):
    """Goal lifecycle status."""
    ACTIVE = "active"          # Goal exists but not yet pursued
    IN_PROGRESS = "in_progress"  # Actively working on goal
    COMPLETED = "completed"    # Goal achieved
    ABANDONED = "abandoned"    # Goal no longer relevant
    BLOCKED = "blocked"        # Cannot proceed (external blocker)


class EmployeeGoal(TenantScopedModel):
    """
    Employee goal (BDI Desire).

    Example:
        >>> goal = EmployeeGoal(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     goal_type=GoalType.ACHIEVEMENT,
        ...     description="Close 10 deals this quarter",
        ...     priority=8,
        ...     target={"metric": "deals_closed", "value": 10, "deadline": "2025-12-31"}
        ... )
    """

    employee_id: UUID = Field(
        description="Employee this goal belongs to"
    )

    # Goal definition
    goal_type: GoalType = Field(
        description="Type of goal"
    )
    description: str = Field(
        min_length=1,
        max_length=500,
        description="Human-readable goal description"
    )
    priority: int = Field(
        ge=1,
        le=10,
        default=5,
        description="Priority (1=lowest, 10=highest)"
    )

    # Target & measurement
    target: Dict[str, Any] = Field(
        description="Goal-specific target metrics (metric, value, timeframe, etc.)"
    )
    current_progress: Dict[str, Any] = Field(
        default_factory=dict,
        description="Real-time progress tracking"
    )

    # Lifecycle
    status: GoalStatus = Field(
        default=GoalStatus.ACTIVE,
        description="Goal status"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When goal was completed (UTC)"
    )
    abandoned_at: Optional[datetime] = Field(
        default=None,
        description="When goal was abandoned (UTC)"
    )


class IntentionType(str, Enum):
    """BDI intention type."""
    ACTION = "action"      # Single executable action
    TACTIC = "tactic"      # Short-term plan (hours-days)
    STRATEGY = "strategy"  # Long-term plan (weeks)


class IntentionStatus(str, Enum):
    """Intention execution status."""
    PLANNED = "planned"          # Not yet started
    IN_PROGRESS = "in_progress"  # Currently executing
    COMPLETED = "completed"      # Successfully completed
    FAILED = "failed"            # Execution failed
    ABANDONED = "abandoned"      # No longer relevant


class EmployeeIntention(TenantScopedModel):
    """
    Employee intention (BDI Intention).

    Example:
        >>> intention = EmployeeIntention(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     goal_id=goal.id,
        ...     intention_type=IntentionType.ACTION,
        ...     description="Send follow-up email to prospect",
        ...     plan={
        ...         "type": "send_email",
        ...         "params": {"to": "prospect@company.com", "template": "follow_up_v2"}
        ...     },
        ...     priority=7
        ... )
    """

    employee_id: UUID = Field(
        description="Employee this intention belongs to"
    )
    goal_id: Optional[UUID] = Field(
        default=None,
        description="Goal this intention serves (None for opportunistic intentions)"
    )

    # Plan definition
    intention_type: IntentionType = Field(
        description="Type of intention"
    )
    description: str = Field(
        min_length=1,
        max_length=500,
        description="Human-readable intention description"
    )
    plan: Dict[str, Any] = Field(
        description="Structured plan (steps, resources, expected outcomes)"
    )

    # Execution
    status: IntentionStatus = Field(
        default=IntentionStatus.PLANNED,
        description="Execution status"
    )
    priority: int = Field(
        ge=1,
        le=10,
        default=5,
        description="Priority (1=lowest, 10=highest)"
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="When execution started (UTC)"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When execution completed (UTC)"
    )
    failed_at: Optional[datetime] = Field(
        default=None,
        description="When execution failed (UTC)"
    )

    # Context
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Why this plan was chosen (rationale, alternatives considered)"
    )
    dependencies: List[UUID] = Field(
        default_factory=list,
        description="Other intention UUIDs this depends on"
    )
```

---

## Belief Models

```python
class BeliefType(str, Enum):
    """Type of belief."""
    STATE = "state"          # Belief about current state
    EVENT = "event"          # Belief that event occurred
    CAUSAL = "causal"        # Belief about causation
    EVALUATIVE = "evaluative"  # Belief about value/quality


class BeliefSource(str, Enum):
    """Source of belief."""
    OBSERVATION = "observation"      # Direct observation
    INFERENCE = "inference"          # Inferred from other beliefs
    TOLD_BY_HUMAN = "told_by_human"  # Human instruction
    PRIOR = "prior"                  # Pre-configured belief


class Belief(TenantScopedModel):
    """
    Employee belief (world model).

    Example:
        >>> belief = Belief(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     belief_type=BeliefType.STATE,
        ...     subject="pipeline",
        ...     predicate="coverage",
        ...     object=2.1,
        ...     confidence=0.9,
        ...     source=BeliefSource.OBSERVATION
        ... )
    """

    employee_id: UUID = Field(
        description="Employee this belief belongs to"
    )

    # Belief content (Subject-Predicate-Object triple)
    belief_type: BeliefType = Field(
        description="Type of belief"
    )
    subject: str = Field(
        min_length=1,
        max_length=200,
        description="What the belief is about"
    )
    predicate: str = Field(
        min_length=1,
        max_length=200,
        description="Property or relation"
    )
    object: Any = Field(
        description="Value (can be text, number, boolean, or complex object)"
    )

    # Confidence & source
    confidence: float = Field(
        ge=0,
        le=1,
        default=0.5,
        description="Confidence level (0-1)"
    )
    source: BeliefSource = Field(
        description="How this belief was formed"
    )
    evidence: List[UUID] = Field(
        default_factory=list,
        description="UUIDs of supporting observations (episodic memories)"
    )

    # Temporal decay
    formed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When belief was formed (UTC)"
    )
    last_updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When belief was last updated (UTC)"
    )
    decay_rate: float = Field(
        ge=0,
        le=1,
        default=0.1,
        description="Linear decay per day (0-1)"
    )

    @property
    def current_confidence(self) -> float:
        """
        Calculate current confidence after temporal decay.

        Confidence decays linearly unless reinforced by new observations.
        """
        days_since_update = (datetime.now(timezone.utc) - self.last_updated_at).days
        decayed_confidence = self.confidence - (self.decay_rate * days_since_update)
        return max(0.0, decayed_confidence)


class BeliefHistory(TenantScopedModel):
    """
    Belief change history.

    Immutable audit log of belief changes for learning and debugging.
    """

    employee_id: UUID = Field(
        description="Employee this belief change relates to"
    )
    belief_id: UUID = Field(
        description="Belief that changed"
    )

    # Change tracking
    change_type: str = Field(
        description="Type of change (created, updated, deleted, decayed)"
    )
    old_value: Optional[Any] = Field(
        default=None,
        description="Previous value"
    )
    new_value: Optional[Any] = Field(
        default=None,
        description="New value"
    )
    old_confidence: Optional[float] = Field(
        default=None,
        description="Previous confidence"
    )
    new_confidence: Optional[float] = Field(
        default=None,
        description="New confidence"
    )

    # Context
    reason: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Why belief changed"
    )

    # Temporal
    changed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When change occurred (UTC)"
    )
```

---

## Memory Models

```python
class EpisodeType(str, Enum):
    """Type of episodic memory."""
    INTERACTION = "interaction"  # Email, Slack, meeting, call
    EVENT = "event"              # System event, trigger
    OBSERVATION = "observation"  # Passive observation
    FEEDBACK = "feedback"        # Human feedback


class EpisodicMemory(TenantScopedModel):
    """
    Episodic memory (events, interactions).

    Example:
        >>> memory = EpisodicMemory(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     episode_type=EpisodeType.INTERACTION,
        ...     description="Email reply from prospect",
        ...     content={
        ...         "from": "prospect@company.com",
        ...         "subject": "Re: Proposal",
        ...         "body": "Thanks for the proposal...",
        ...         "sentiment": "positive"
        ...     },
        ...     participants=["prospect@company.com"],
        ...     location="email",
        ...     importance=0.8
        ... )
    """

    employee_id: UUID = Field(
        description="Employee this memory belongs to"
    )

    # Episode content
    episode_type: EpisodeType = Field(
        description="Type of episode"
    )
    description: str = Field(
        min_length=1,
        max_length=500,
        description="Human-readable episode summary"
    )
    content: Dict[str, Any] = Field(
        description="Full episode data"
    )

    # Context
    participants: List[str] = Field(
        default_factory=list,
        description="Email addresses or identifiers of participants"
    )
    location: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Where episode occurred (email, slack, zoom, phone, etc.)"
    )

    # Embedding for similarity search
    embedding: Optional[List[float]] = Field(
        default=None,
        description="1024-dim embedding for semantic similarity search"
    )

    # Importance & recall
    importance: float = Field(
        ge=0,
        le=1,
        default=0.5,
        description="Importance score (0-1, affects retention)"
    )
    recall_count: int = Field(
        ge=0,
        default=0,
        description="How many times this memory was recalled"
    )
    last_recalled_at: Optional[datetime] = Field(
        default=None,
        description="When this memory was last recalled (UTC)"
    )

    # Temporal
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When episode occurred (UTC)"
    )


class FactType(str, Enum):
    """Type of semantic memory fact."""
    ENTITY = "entity"              # Fact about an entity
    RELATIONSHIP = "relationship"  # Fact about a relationship
    RULE = "rule"                  # Business rule or heuristic
    DEFINITION = "definition"      # Definition of a term


class SemanticMemory(TenantScopedModel):
    """
    Semantic memory (facts, knowledge).

    Uses Subject-Predicate-Object (SPO) triple structure.

    Example:
        >>> memory = SemanticMemory(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     fact_type=FactType.ENTITY,
        ...     subject="Acme Corp",
        ...     predicate="is_a",
        ...     object="enterprise_customer",
        ...     confidence=0.9,
        ...     verified=True
        ... )
    """

    employee_id: UUID = Field(
        description="Employee this memory belongs to"
    )

    # Fact content (SPO triple)
    fact_type: FactType = Field(
        description="Type of fact"
    )
    subject: str = Field(
        min_length=1,
        max_length=200,
        description="Subject of the fact"
    )
    predicate: str = Field(
        min_length=1,
        max_length=200,
        description="Predicate (relation or property)"
    )
    object: str = Field(
        min_length=1,
        max_length=500,
        description="Object of the fact"
    )

    # Additional context
    confidence: float = Field(
        ge=0,
        le=1,
        default=1.0,
        description="Confidence in this fact (0-1)"
    )
    source: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Where this fact came from"
    )
    verified: bool = Field(
        default=False,
        description="Whether fact was verified by human"
    )

    # Embedding
    embedding: Optional[List[float]] = Field(
        default=None,
        description="1024-dim embedding for semantic similarity search"
    )


class ProcedureType(str, Enum):
    """Type of procedural memory."""
    SKILL = "skill"          # Low-level action
    WORKFLOW = "workflow"    # Multi-step procedure
    HEURISTIC = "heuristic"  # Decision rule


class LearnedFrom(str, Enum):
    """How procedure was learned."""
    HUMAN_DEMONSTRATION = "human_demonstration"  # Observed human
    TRIAL_AND_ERROR = "trial_and_error"          # Learned by doing
    INSTRUCTION = "instruction"                  # Explicitly instructed
    PRE_BUILT = "pre_built"                      # Shipped with employee


class ProceduralMemory(TenantScopedModel):
    """
    Procedural memory (skills, workflows).

    Example:
        >>> memory = ProceduralMemory(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     procedure_name="send_follow_up_email",
        ...     description="Send personalized follow-up email after meeting",
        ...     procedure_type=ProcedureType.SKILL,
        ...     steps={
        ...         "steps": [
        ...             {"step": 1, "action": "retrieve_meeting_notes"},
        ...             {"step": 2, "action": "draft_email", "template": "follow_up"},
        ...             {"step": 3, "action": "personalize_email"},
        ...             {"step": 4, "action": "send_email"}
        ...         ]
        ...     },
        ...     success_rate=0.85,
        ...     learned_from=LearnedFrom.HUMAN_DEMONSTRATION
        ... )
    """

    employee_id: UUID = Field(
        description="Employee this memory belongs to"
    )

    # Procedure definition
    procedure_name: str = Field(
        min_length=1,
        max_length=200,
        description="Unique procedure name"
    )
    description: str = Field(
        min_length=1,
        max_length=500,
        description="Human-readable procedure description"
    )
    procedure_type: ProcedureType = Field(
        description="Type of procedure"
    )

    # Procedure content
    steps: Dict[str, Any] = Field(
        description="Structured procedure steps"
    )
    conditions: Dict[str, Any] = Field(
        default_factory=dict,
        description="When to use this procedure (context matching)"
    )

    # Learning & performance
    success_rate: float = Field(
        ge=0,
        le=1,
        default=0.0,
        description="Success rate (0-1, learned from outcomes)"
    )
    execution_count: int = Field(
        ge=0,
        default=0,
        description="How many times this procedure was executed"
    )
    last_executed_at: Optional[datetime] = Field(
        default=None,
        description="When this procedure was last executed (UTC)"
    )

    # Metadata
    learned_from: LearnedFrom = Field(
        description="How this procedure was learned"
    )


class ContextType(str, Enum):
    """Type of working memory context."""
    CURRENT_TASK = "current_task"          # Currently executing task
    CONVERSATION = "conversation"          # Active conversation
    SCRATCHPAD = "scratchpad"              # Temporary notes
    RECENT_OBSERVATION = "recent_observation"  # Recent observation


class WorkingMemory(TenantScopedModel):
    """
    Working memory (current context).

    Short-lived memory for current execution context.

    Example:
        >>> memory = WorkingMemory(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     context_type=ContextType.CURRENT_TASK,
        ...     content={
        ...         "task": "compose_followup_email",
        ...         "context": {"prospect": "jane@acme.com"},
        ...         "progress": {"step": "drafting"}
        ...     },
        ...     priority=8,
        ...     expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        ... )
    """

    employee_id: UUID = Field(
        description="Employee this memory belongs to"
    )

    # Context content
    context_type: ContextType = Field(
        description="Type of context"
    )
    content: Dict[str, Any] = Field(
        description="Context data"
    )

    # Lifecycle
    priority: int = Field(
        ge=1,
        le=10,
        default=5,
        description="Priority (1=lowest, 10=highest, affects eviction)"
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="When to auto-evict this memory (UTC)"
    )
```

---

## Audit & Observability Models

```python
class ActorType(str, Enum):
    """Type of actor in audit log."""
    EMPLOYEE = "employee"  # Digital employee
    USER = "user"          # Human user
    SYSTEM = "system"      # System/automated action


class AuditLogEntry(TenantScopedModel):
    """
    Audit log entry.

    Immutable append-only log of all significant actions.

    Example:
        >>> entry = AuditLogEntry(
        ...     tenant_id=tenant.id,
        ...     actor_type=ActorType.EMPLOYEE,
        ...     actor_id=employee.id,
        ...     action_type="goal_created",
        ...     resource_type="employee_goal",
        ...     resource_id=goal.id,
        ...     details={"description": "Close 10 deals this quarter"}
        ... )
    """

    # Actor
    actor_type: ActorType = Field(
        description="Type of actor"
    )
    actor_id: UUID = Field(
        description="Actor UUID (employee/user/system)"
    )

    # Action
    action_type: str = Field(
        min_length=1,
        max_length=100,
        description="Action performed (goal_created, intention_executed, etc.)"
    )
    resource_type: str = Field(
        min_length=1,
        max_length=100,
        description="Type of resource affected"
    )
    resource_id: Optional[UUID] = Field(
        default=None,
        description="Resource UUID (if applicable)"
    )

    # Details
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Action-specific details"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )

    # Temporal
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When action occurred (UTC)"
    )


class MetricType(str, Enum):
    """Type of metric."""
    COUNTER = "counter"      # Incrementing count
    GAUGE = "gauge"          # Point-in-time value
    HISTOGRAM = "histogram"  # Distribution of values


class Metric(TenantScopedModel):
    """
    Performance metric.

    Time-series data for monitoring and alerting.

    Example:
        >>> metric = Metric(
        ...     tenant_id=tenant.id,
        ...     employee_id=employee.id,
        ...     metric_name="bdi.strategic_planning.duration",
        ...     metric_type=MetricType.HISTOGRAM,
        ...     value=1.5,
        ...     tags={"goal_type": "pipeline", "outcome": "success"}
        ... )
    """

    employee_id: Optional[UUID] = Field(
        default=None,
        description="Employee this metric relates to (None for system-wide metrics)"
    )

    # Metric identity
    metric_name: str = Field(
        min_length=1,
        max_length=200,
        description="Metric name (dotted notation: bdi.strategic_planning.duration)"
    )
    metric_type: MetricType = Field(
        description="Type of metric"
    )

    # Value
    value: float = Field(
        description="Metric value"
    )
    tags: Dict[str, str] = Field(
        default_factory=dict,
        description="Metric dimensions (goal_type, outcome, etc.)"
    )

    # Temporal
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When metric was recorded (UTC)"
    )
```

---

## API Request/Response Models

### Employee API Models

```python
class EmployeeCreateRequest(EmplaBaseModel):
    """
    Request to create a new employee.

    Example:
        >>> request = EmployeeCreateRequest(
        ...     name="Jordan Chen",
        ...     role=EmployeeRole.SALES_AE,
        ...     email="jordan.chen@acme-corp.com",
        ...     personality={"tone": "professional", "traits": ["persistent"]}
        ... )
    """

    name: str = Field(
        min_length=2,
        max_length=200,
        description="Employee display name"
    )
    role: EmployeeRole = Field(
        description="Employee role"
    )
    email: EmailStr = Field(
        description="Employee email address"
    )
    personality: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Personality traits (uses defaults if not provided)"
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Configuration (uses defaults if not provided)"
    )
    capabilities: Optional[List[str]] = Field(
        default=None,
        description="Enabled capabilities (uses role defaults if not provided)"
    )


class EmployeeUpdateRequest(EmplaBaseModel):
    """Request to update an employee."""

    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=200,
        description="Employee display name"
    )
    personality: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Personality traits"
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Configuration"
    )
    capabilities: Optional[List[str]] = Field(
        default=None,
        description="Enabled capabilities"
    )
    status: Optional[EmployeeStatus] = Field(
        default=None,
        description="Operational status"
    )


class EmployeeResponse(EmplaBaseModel):
    """
    Employee API response.

    Includes full employee data plus computed fields.
    """

    id: UUID
    tenant_id: UUID
    name: str
    role: EmployeeRole
    email: EmailStr
    personality: EmployeePersonality
    status: EmployeeStatus
    lifecycle_stage: EmployeeLifecycleStage
    onboarded_at: Optional[datetime]
    activated_at: Optional[datetime]
    config: EmployeeConfig
    capabilities: List[str]
    performance_metrics: EmployeePerformanceMetrics
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime
```

### Goal API Models

```python
class GoalCreateRequest(EmplaBaseModel):
    """Request to create a new goal."""

    goal_type: GoalType = Field(
        description="Type of goal"
    )
    description: str = Field(
        min_length=1,
        max_length=500,
        description="Goal description"
    )
    priority: int = Field(
        ge=1,
        le=10,
        default=5,
        description="Priority (1-10)"
    )
    target: Dict[str, Any] = Field(
        description="Goal target metrics"
    )


class GoalResponse(EmplaBaseModel):
    """Goal API response."""

    id: UUID
    tenant_id: UUID
    employee_id: UUID
    goal_type: GoalType
    description: str
    priority: int
    target: Dict[str, Any]
    current_progress: Dict[str, Any]
    status: GoalStatus
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
```

---

## Validation Examples

```python
# Example 1: Email validation
try:
    user = User(
        tenant_id=uuid4(),
        email="invalid-email",  # Missing @domain
        name="Test User",
        role=UserRole.USER
    )
except ValidationError as e:
    print(e)  # EmailStr validation error

# Example 2: Priority range validation
try:
    goal = EmployeeGoal(
        tenant_id=uuid4(),
        employee_id=uuid4(),
        goal_type=GoalType.ACHIEVEMENT,
        description="Test goal",
        priority=15,  # Out of range (1-10)
        target={"metric": "test"}
    )
except ValidationError as e:
    print(e)  # Priority constraint violation

# Example 3: Slug format validation
try:
    tenant = Tenant(
        name="Test Corp",
        slug="Test Corp",  # Spaces not allowed
        status=TenantStatus.ACTIVE
    )
except ValidationError as e:
    print(e)  # Slug format validation error

# Example 4: Custom validator
try:
    employee = Employee(
        tenant_id=uuid4(),
        name="   ",  # Empty after strip
        role=EmployeeRole.SALES_AE,
        email="test@example.com"
    )
except ValidationError as e:
    print(e)  # Name validation error
```

---

## JSON Serialization Examples

```python
# Serialize to dict
employee = Employee(
    tenant_id=uuid4(),
    name="Jordan Chen",
    role=EmployeeRole.SALES_AE,
    email="jordan@example.com"
)
employee_dict = employee.model_dump()

# Serialize to JSON
employee_json = employee.model_dump_json()

# Deserialize from dict
employee2 = Employee.model_validate(employee_dict)

# Deserialize from JSON
employee3 = Employee.model_validate_json(employee_json)
```

---

## Database Integration

```python
from sqlalchemy import select
from empla.models import Employee as EmployeeDB

# Convert Pydantic model to SQLAlchemy model
def pydantic_to_sqlalchemy(pydantic_obj: Employee) -> EmployeeDB:
    """Convert Pydantic model to SQLAlchemy model."""
    return EmployeeDB(**pydantic_obj.model_dump())

# Convert SQLAlchemy model to Pydantic model
def sqlalchemy_to_pydantic(sqlalchemy_obj: EmployeeDB) -> Employee:
    """Convert SQLAlchemy model to Pydantic model."""
    return Employee.model_validate(sqlalchemy_obj)

# Example: Create employee in database
async def create_employee(employee: EmployeeCreateRequest) -> EmployeeResponse:
    """Create employee in database."""
    # Convert request to domain model
    employee_model = Employee(
        tenant_id=get_current_tenant_id(),
        **employee.model_dump(exclude_none=True)
    )

    # Convert to SQLAlchemy model
    db_employee = pydantic_to_sqlalchemy(employee_model)

    # Save to database
    db.add(db_employee)
    await db.commit()
    await db.refresh(db_employee)

    # Convert back to Pydantic and return
    return EmployeeResponse.model_validate(db_employee)
```

---

## Testing Utilities

```python
# Factory functions for testing
def create_test_tenant() -> Tenant:
    """Create a test tenant."""
    return Tenant(
        name="Test Corp",
        slug="test-corp",
        status=TenantStatus.ACTIVE
    )

def create_test_employee(tenant_id: UUID) -> Employee:
    """Create a test employee."""
    return Employee(
        tenant_id=tenant_id,
        name="Test Employee",
        role=EmployeeRole.SALES_AE,
        email="test@example.com",
        status=EmployeeStatus.ACTIVE
    )

def create_test_goal(tenant_id: UUID, employee_id: UUID) -> EmployeeGoal:
    """Create a test goal."""
    return EmployeeGoal(
        tenant_id=tenant_id,
        employee_id=employee_id,
        goal_type=GoalType.ACHIEVEMENT,
        description="Test goal",
        priority=5,
        target={"metric": "test", "value": 10}
    )
```

---

## Open Questions

1. **Embedding dimensions**: 1024 vs 1536 vs 3072? (Current: 1024 for balance)
2. **Memory capacity limits**: Hard limits or importance-based eviction? (Current: soft limits)
3. **Belief decay function**: Linear vs exponential? (Current: linear for simplicity)
4. **API pagination**: Offset vs cursor-based? (Current: TBD in API implementation)

---

## Next Steps

1. **Implement SQLAlchemy models** based on database schema
2. **Create Alembic migrations** for database tables
3. **Write unit tests** for all Pydantic models (validation, serialization)
4. **Implement API endpoints** using these models (FastAPI)

---

**References:**
- docs/design/database-schema.md - Database schema
- docs/design/bdi-engine.md - BDI implementation
- docs/design/memory-system.md - Memory system implementation
- ARCHITECTURE.md - System architecture
