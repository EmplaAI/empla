# BDI Engine Design

> **Status:** Draft
> **Author:** Claude Code
> **Date:** 2025-10-27
> **Phase:** Phase 1 - Core Infrastructure

---

## Overview

This document defines the **BDI (Belief-Desire-Intention) engine** - the cognitive architecture that enables empla employees to reason autonomously and pursue goals proactively.

**What is BDI?**

BDI is a cognitive architecture from AI research that models how rational agents reason and act:
- **Beliefs**: Agent's knowledge about the world (world model)
- **Desires**: Agent's goals (what it wants to achieve)
- **Intentions**: Agent's committed plans (what it's currently doing)

**Why BDI for empla?**

- ✅ **Autonomous reasoning**: Agents decide what to do based on goals, not just react to commands
- ✅ **Goal-oriented behavior**: Focus on achieving outcomes, not just executing tasks
- ✅ **Adaptive planning**: Re-plan when beliefs change (dynamic environment)
- ✅ **Explainable decisions**: Clear reasoning chain (belief → goal → intention)
- ✅ **Research-backed**: 30+ years of academic research, proven in robotics, autonomous systems

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                  Proactive Execution Loop                │
│  (Continuous cycle: Perceive → Reason → Act → Learn)    │
└─────────────────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ Beliefs  │    │ Desires  │    │Intentions│
    │  System  │───▶│  (Goals) │───▶│  (Plans) │
    └──────────┘    └──────────┘    └──────────┘
          │                │                │
          │                │                │
    World Model      Motivation        Execution
  (What I know)   (What I want)    (What I'm doing)
```

### Component Responsibilities

1. **Belief System** - Maintains world model
   - Updates beliefs from observations
   - Temporal decay (beliefs weaken over time)
   - Conflict resolution (handle contradictory beliefs)
   - Confidence tracking

2. **Desire/Goal System** - Manages goals
   - Goal prioritization (urgency × importance)
   - Goal lifecycle (formation, pursuit, completion, abandonment)
   - Goal dependencies and conflicts
   - Progress tracking

3. **Intention Stack** - Manages plans
   - Plan selection (choose best plan for goal)
   - Plan execution (execute steps)
   - Plan monitoring (detect failures)
   - Plan revision (replan when needed)

4. **Strategic Reasoning** - High-level decision making
   - When to form new goals
   - When to abandon goals
   - When to replan
   - Resource allocation across goals

---

## Belief System

### Purpose

Maintain the employee's **world model** - what they believe to be true about:
- Current state (pipeline coverage, customer health, etc.)
- Past events (prospect replied, meeting happened)
- Causal relations (personalized emails increase response rate)
- Evaluations (this account is high priority)

### Data Model

See `docs/design/core-models.md` for Pydantic models.

```python
class Belief:
    # Content (Subject-Predicate-Object triple)
    subject: str           # e.g., "pipeline"
    predicate: str         # e.g., "coverage"
    object: Any            # e.g., 2.1
    belief_type: BeliefType  # state, event, causal, evaluative

    # Confidence
    confidence: float      # 0-1 scale
    source: BeliefSource  # observation, inference, told_by_human, prior
    evidence: List[UUID]  # Supporting episodic memories

    # Temporal decay
    formed_at: datetime
    last_updated_at: datetime
    decay_rate: float     # Linear decay per day
```

### Belief Update Algorithm

**Triggered by**: New observations from proactive loop

**Input**: List of observations (episodic memories)

**Output**: Updated beliefs, list of changed beliefs

**Algorithm:**

```python
async def update_beliefs(observations: List[Observation]) -> List[BeliefChange]:
    """
    Update beliefs based on new observations.

    This is the core of the world model update mechanism.
    """
    changes = []

    for obs in observations:
        # 1. Extract propositions from observation
        propositions = extract_propositions(obs)

        for prop in propositions:
            # 2. Check if belief already exists
            existing_belief = await get_belief(prop.subject, prop.predicate)

            if existing_belief:
                # 3a. Update existing belief
                change = await update_existing_belief(existing_belief, prop, obs)
            else:
                # 3b. Form new belief
                change = await form_new_belief(prop, obs)

            changes.append(change)

    # 4. Detect and resolve conflicts
    await resolve_belief_conflicts(changes)

    # 5. Update belief history (for learning)
    await record_belief_changes(changes)

    return changes


async def update_existing_belief(
    belief: Belief,
    proposition: Proposition,
    observation: Observation
) -> BeliefChange:
    """Update confidence of existing belief."""

    # Calculate new confidence based on:
    # - Source reliability (observation > inference > prior)
    # - Consistency with evidence
    # - Time since last update

    source_weight = {
        BeliefSource.OBSERVATION: 1.0,
        BeliefSource.TOLD_BY_HUMAN: 0.9,
        BeliefSource.INFERENCE: 0.7,
        BeliefSource.PRIOR: 0.5
    }

    # Agreement: Observation supports belief
    if proposition.object == belief.object:
        # Increase confidence (bounded by 1.0)
        confidence_boost = source_weight[observation.source] * 0.2
        new_confidence = min(1.0, belief.confidence + confidence_boost)

        # Reset decay timer
        new_updated_at = datetime.utcnow()

        # Add observation to evidence
        belief.evidence.append(observation.id)

    # Disagreement: Observation contradicts belief
    else:
        # Decrease confidence based on source strength
        confidence_penalty = source_weight[observation.source] * 0.3
        new_confidence = max(0.0, belief.confidence - confidence_penalty)

        # If confidence drops below threshold, replace belief
        if new_confidence < 0.3:
            return await replace_belief(belief, proposition, observation)

        new_updated_at = datetime.utcnow()

    # Update belief
    old_confidence = belief.confidence
    belief.confidence = new_confidence
    belief.last_updated_at = new_updated_at

    await db.save(belief)

    # Record change
    return BeliefChange(
        belief_id=belief.id,
        change_type="updated",
        old_confidence=old_confidence,
        new_confidence=new_confidence,
        reason=f"Observation {observation.id}"
    )


async def form_new_belief(
    proposition: Proposition,
    observation: Observation
) -> BeliefChange:
    """Form a new belief from observation."""

    belief = Belief(
        employee_id=employee.id,
        tenant_id=employee.tenant_id,
        belief_type=proposition.belief_type,
        subject=proposition.subject,
        predicate=proposition.predicate,
        object=proposition.object,
        confidence=0.7,  # Initial confidence for new belief
        source=observation.source,
        evidence=[observation.id],
        formed_at=datetime.utcnow(),
        last_updated_at=datetime.utcnow()
    )

    await db.save(belief)

    return BeliefChange(
        belief_id=belief.id,
        change_type="created",
        new_confidence=0.7,
        reason=f"Formed from observation {observation.id}"
    )
```

### Temporal Decay

Beliefs decay over time unless reinforced by new observations (mimics human memory).

**Decay function** (linear for simplicity, exponential in Phase 3+):

```python
def calculate_current_confidence(belief: Belief) -> float:
    """
    Calculate belief confidence after temporal decay.

    Linear decay: confidence reduces by decay_rate per day.
    """
    days_since_update = (datetime.utcnow() - belief.last_updated_at).days
    decayed_confidence = belief.confidence - (belief.decay_rate * days_since_update)
    return max(0.0, decayed_confidence)
```

**When to apply decay:**
- On every belief query (lazy evaluation)
- During strategic planning cycle (batch evaluation)
- Background job (optional, for proactive cleanup)

**Decay rates by source:**
- Observation: 0.05/day (slow decay, direct evidence)
- Told by human: 0.03/day (very slow, authoritative)
- Inference: 0.1/day (faster decay, derived)
- Prior: 0.15/day (fastest decay, assumed)

### Conflict Resolution

When observations contradict existing beliefs:

**Algorithm:**

```python
async def resolve_belief_conflicts(changes: List[BeliefChange]) -> None:
    """
    Detect and resolve conflicting beliefs.

    Conflict: Two beliefs with same (subject, predicate) but different objects.
    """

    # Group changes by (subject, predicate)
    grouped = defaultdict(list)
    for change in changes:
        belief = await db.get(Belief, change.belief_id)
        key = (belief.subject, belief.predicate)
        grouped[key].append(belief)

    # Resolve conflicts
    for key, beliefs in grouped.items():
        if len(beliefs) > 1:
            # Multiple beliefs with same (subject, predicate)
            # Keep highest confidence, delete others
            beliefs_sorted = sorted(beliefs, key=lambda b: b.confidence, reverse=True)
            winner = beliefs_sorted[0]

            for loser in beliefs_sorted[1:]:
                # Archive losing belief
                await archive_belief(loser, reason=f"Lost to {winner.id}")
```

### Belief Queries

**Query interface** for other components:

```python
class BeliefSystem:
    async def get_belief(self, subject: str, predicate: str) -> Optional[Belief]:
        """Get belief by subject and predicate."""

    async def query_beliefs(self, filters: Dict[str, Any]) -> List[Belief]:
        """Query beliefs with filters (subject, belief_type, min_confidence)."""

    async def check_belief(self, subject: str, predicate: str, object: Any) -> float:
        """Check if belief exists and return confidence (0 if not found)."""

    async def all_beliefs_about(self, subject: str) -> List[Belief]:
        """Get all beliefs about a subject."""
```

---

## Desire/Goal System

### Purpose

Manage the employee's **goals** (desires) - what they want to achieve:
- Achievement goals (reach a target state)
- Maintenance goals (maintain a state)
- Prevention goals (avoid a state)

### Goal Formation

**When are goals formed?**

1. **Explicitly assigned** by human (onboarding, delegation)
2. **Derived from role** (Sales AE automatically gets pipeline goal)
3. **Opportunistically discovered** (notice problem, form goal to fix it)
4. **From reflection** (realize pattern, form goal to improve)

**Goal formation algorithm:**

```python
async def form_goal_from_observation(
    observation: Observation,
    beliefs: BeliefSystem
) -> Optional[EmployeeGoal]:
    """
    Opportunistically form goal from observation.

    Example: Notice pipeline < 3x quota → Form goal to build pipeline
    """

    # Check if observation triggers goal formation
    triggers = [
        LowPipelineGoalTrigger(),
        ChurnRiskGoalTrigger(),
        OpportunityGoalTrigger(),
        # ... more triggers
    ]

    for trigger in triggers:
        if trigger.matches(observation, beliefs):
            goal = trigger.form_goal(observation, beliefs)
            return goal

    return None


class LowPipelineGoalTrigger:
    """Trigger goal when pipeline coverage is low."""

    def matches(self, obs: Observation, beliefs: BeliefSystem) -> bool:
        # Check belief: pipeline_coverage < 3.0
        coverage = beliefs.check_belief("pipeline", "coverage", ...)
        return coverage < 3.0

    def form_goal(self, obs: Observation, beliefs: BeliefSystem) -> EmployeeGoal:
        return EmployeeGoal(
            goal_type=GoalType.ACHIEVEMENT,
            description="Build pipeline to 3x quota coverage",
            priority=8,  # High priority
            target={
                "metric": "pipeline_coverage",
                "value": 3.0,
                "deadline": end_of_quarter()
            }
        )
```

### Goal Prioritization

**Priority calculation** (1-10 scale):

```python
def calculate_goal_priority(goal: EmployeeGoal, beliefs: BeliefSystem) -> int:
    """
    Calculate goal priority based on urgency and importance.

    Priority = (Urgency × 0.6) + (Importance × 0.4)

    Urgency: How soon goal must be achieved (deadline pressure)
    Importance: Strategic value of goal (impact on role success)
    """

    urgency = calculate_urgency(goal)
    importance = calculate_importance(goal, beliefs)

    priority = (urgency * 0.6) + (importance * 0.4)
    return int(round(priority * 10))  # Scale to 1-10


def calculate_urgency(goal: EmployeeGoal) -> float:
    """
    Calculate urgency (0-1 scale).

    Based on deadline proximity and goal type.
    """
    if "deadline" not in goal.target:
        # No deadline → moderate urgency
        return 0.5

    deadline = datetime.fromisoformat(goal.target["deadline"])
    days_until_deadline = (deadline - datetime.utcnow()).days

    # Urgency curve (exponential as deadline approaches)
    if days_until_deadline <= 0:
        return 1.0  # Overdue
    elif days_until_deadline <= 7:
        return 0.9  # Due within a week
    elif days_until_deadline <= 30:
        return 0.7  # Due within a month
    else:
        return 0.5  # Not urgent


def calculate_importance(goal: EmployeeGoal, beliefs: BeliefSystem) -> float:
    """
    Calculate importance (0-1 scale).

    Based on strategic value and role alignment.
    """
    # Role-specific importance
    role_importance = {
        "build_pipeline": 1.0,  # Critical for Sales AE
        "prevent_churn": 0.9,   # Critical for CSM
        "launch_feature": 0.8,  # Important for PM
    }

    goal_category = categorize_goal(goal)
    importance = role_importance.get(goal_category, 0.5)

    # Adjust based on beliefs (e.g., account value, deal size)
    if "account_id" in goal.target:
        account = goal.target["account_id"]
        account_value = beliefs.check_belief(account, "annual_value", ...)
        if account_value > 100000:
            importance = min(1.0, importance * 1.2)  # Boost for high-value accounts

    return importance
```

**Goal prioritization updates:**
- On goal creation
- When beliefs change (e.g., deadline moves closer)
- During strategic planning cycle
- When resources become available

### Goal Lifecycle

```
   Created
      ↓
   Active ────────┐
      ↓           │
  In Progress     │
      ↓           │
   ┌──┴──┐        │
   ↓     ↓        │
Completed  ←──────┘
           ↓
        Abandoned
           ↓
         Blocked
```

**State transitions:**

```python
class GoalSystem:
    async def activate_goal(self, goal: EmployeeGoal) -> None:
        """
        Activate a goal (start pursuing it).

        Triggers intention formation (planning).
        """
        goal.status = GoalStatus.ACTIVE
        await db.save(goal)

        # Trigger planning for this goal
        await self.intention_stack.plan_for_goal(goal)

    async def mark_in_progress(self, goal: EmployeeGoal) -> None:
        """Mark goal as in progress (at least one intention executing)."""
        goal.status = GoalStatus.IN_PROGRESS
        await db.save(goal)

    async def complete_goal(self, goal: EmployeeGoal) -> None:
        """Mark goal as completed (target achieved)."""
        goal.status = GoalStatus.COMPLETED
        goal.completed_at = datetime.utcnow()
        await db.save(goal)

        # Update performance metrics
        await self.update_performance_metrics(goal)

    async def abandon_goal(self, goal: EmployeeGoal, reason: str) -> None:
        """Abandon goal (no longer relevant or achievable)."""
        goal.status = GoalStatus.ABANDONED
        goal.abandoned_at = datetime.utcnow()
        await db.save(goal)

        # Cancel related intentions
        await self.intention_stack.cancel_intentions_for_goal(goal.id)

    async def block_goal(self, goal: EmployeeGoal, blocker: str) -> None:
        """Block goal (cannot proceed due to external dependency)."""
        goal.status = GoalStatus.BLOCKED
        await db.save(goal)

        # Pause related intentions
        await self.intention_stack.pause_intentions_for_goal(goal.id)
```

### Goal Progress Tracking

```python
async def update_goal_progress(goal: EmployeeGoal, beliefs: BeliefSystem) -> None:
    """
    Update goal progress based on current beliefs.

    Example: Goal is "build pipeline to 3x", check belief "pipeline.coverage"
    """

    target_metric = goal.target["metric"]
    target_value = goal.target["value"]

    # Query belief for current value
    current_value = beliefs.check_belief(target_metric, "current_value", ...)

    # Calculate progress (0-1 scale)
    if goal.goal_type == GoalType.ACHIEVEMENT:
        progress = current_value / target_value
    elif goal.goal_type == GoalType.MAINTENANCE:
        # Maintenance: Check if above threshold
        progress = 1.0 if current_value >= target_value else 0.0
    elif goal.goal_type == GoalType.PREVENTION:
        # Prevention: Check if below threshold
        progress = 1.0 if current_value <= target_value else 0.0

    # Update goal progress
    goal.current_progress = {
        "metric": target_metric,
        "current_value": current_value,
        "target_value": target_value,
        "progress_percentage": progress * 100,
        "last_updated": datetime.utcnow().isoformat()
    }

    # Check if goal is complete
    if progress >= 1.0:
        await complete_goal(goal)

    await db.save(goal)
```

---

## Intention Stack

### Purpose

Manage the employee's **committed plans** (intentions) - what they're actively doing:
- Action intentions (single executable actions)
- Tactic intentions (short-term multi-step plans)
- Strategy intentions (long-term composed plans)

### Plan Selection

**When plans are formed:**

1. **Goal activated** → Generate plan to achieve goal
2. **Plan failed** → Generate alternative plan (replan)
3. **Opportunity detected** → Generate opportunistic plan (not tied to goal)
4. **Deadline approaching** → Generate urgent plan

**Plan selection algorithm:**

```python
async def plan_for_goal(
    goal: EmployeeGoal,
    beliefs: BeliefSystem,
    procedural_memory: ProceduralMemory
) -> EmployeeIntention:
    """
    Generate plan to achieve goal.

    Uses procedural memory (learned strategies) and strategic reasoning.
    """

    # 1. Retrieve candidate strategies from procedural memory
    strategies = await procedural_memory.retrieve_procedures(
        goal_type=goal.goal_type,
        context=extract_context(goal, beliefs)
    )

    # 2. Evaluate strategies
    evaluated = []
    for strategy in strategies:
        score = evaluate_strategy(strategy, goal, beliefs)
        evaluated.append((score, strategy))

    # Sort by score (highest first)
    evaluated.sort(key=lambda x: x[0], reverse=True)

    # 3. Select best strategy
    if evaluated:
        _, best_strategy = evaluated[0]
        plan = instantiate_strategy(best_strategy, goal, beliefs)
    else:
        # No learned strategy → Use LLM to generate plan
        plan = await generate_plan_with_llm(goal, beliefs)

    # 4. Create intention
    intention = EmployeeIntention(
        employee_id=goal.employee_id,
        tenant_id=goal.tenant_id,
        goal_id=goal.id,
        intention_type=IntentionType.STRATEGY,
        description=f"Achieve goal: {goal.description}",
        plan=plan,
        priority=goal.priority,
        status=IntentionStatus.PLANNED
    )

    await db.save(intention)

    return intention


def evaluate_strategy(
    strategy: ProceduralMemory,
    goal: EmployeeGoal,
    beliefs: BeliefSystem
) -> float:
    """
    Evaluate strategy for goal (0-1 score).

    Factors:
    - Success rate (historical performance)
    - Context match (how well context matches current situation)
    - Resource requirements (do we have required capabilities?)
    """

    # Success rate (0-1)
    success_factor = strategy.success_rate

    # Context match (0-1)
    context_match = calculate_context_match(strategy.conditions, beliefs)

    # Resource availability (0-1)
    resources_available = check_resource_availability(strategy.steps)

    # Weighted score
    score = (success_factor * 0.5) + (context_match * 0.3) + (resources_available * 0.2)

    return score
```

### Plan Execution

```python
class IntentionStack:
    """
    Manages intention execution.

    Like a stack of intentions, highest priority executes first.
    """

    async def execute_next_intention(self) -> Optional[IntentionResult]:
        """
        Execute highest priority intention.

        Called by proactive execution loop.
        """

        # 1. Get highest priority planned intention
        intention = await self.get_next_intention()

        if not intention:
            return None  # Nothing to do

        # 2. Check dependencies
        if not await self.dependencies_satisfied(intention):
            return None  # Wait for dependencies

        # 3. Mark as in progress
        intention.status = IntentionStatus.IN_PROGRESS
        intention.started_at = datetime.utcnow()
        await db.save(intention)

        # 4. Execute based on type
        try:
            if intention.intention_type == IntentionType.ACTION:
                result = await self.execute_action(intention)
            elif intention.intention_type == IntentionType.TACTIC:
                result = await self.execute_tactic(intention)
            elif intention.intention_type == IntentionType.STRATEGY:
                result = await self.execute_strategy(intention)

            # 5. Mark as completed
            intention.status = IntentionStatus.COMPLETED
            intention.completed_at = datetime.utcnow()
            await db.save(intention)

            return result

        except Exception as e:
            # 6. Handle failure
            await self.handle_intention_failure(intention, e)
            return None


    async def execute_action(self, intention: EmployeeIntention) -> IntentionResult:
        """
        Execute single action.

        Example: Send email, create task, schedule meeting
        """
        action_type = intention.plan["type"]
        params = intention.plan["params"]

        # Dispatch to capability handler
        capability = self.capabilities[action_type]
        result = await capability.execute(params)

        return IntentionResult(
            intention_id=intention.id,
            success=True,
            outcome=result
        )


    async def execute_tactic(self, intention: EmployeeIntention) -> IntentionResult:
        """
        Execute tactic (multi-step plan).

        Creates child intentions for each step.
        """
        steps = intention.plan["tactics"]

        # Create intentions for each step
        child_intentions = []
        for i, step in enumerate(steps):
            child = EmployeeIntention(
                employee_id=intention.employee_id,
                tenant_id=intention.tenant_id,
                goal_id=intention.goal_id,
                intention_type=IntentionType.ACTION,
                description=step["type"],
                plan=step,
                priority=intention.priority,
                dependencies=[intention.id] if i > 0 else []
            )
            await db.save(child)
            child_intentions.append(child)

        # Mark parent as strategy coordination
        intention.context["child_intentions"] = [c.id for c in child_intentions]
        await db.save(intention)

        return IntentionResult(
            intention_id=intention.id,
            success=True,
            outcome=f"Created {len(child_intentions)} child intentions"
        )


    async def execute_strategy(self, intention: EmployeeIntention) -> IntentionResult:
        """
        Execute strategy (long-term plan).

        Similar to tactic but creates tactic-level children.
        """
        # Similar to execute_tactic but for longer-term plans
        pass
```

### Plan Monitoring & Replanning

```python
async def monitor_intention_progress(intention: EmployeeIntention) -> None:
    """
    Monitor intention execution and replan if needed.

    Called periodically during execution.
    """

    # Check if intention is taking too long
    if intention.started_at:
        duration = datetime.utcnow() - intention.started_at
        expected_duration = estimate_duration(intention)

        if duration > expected_duration * 2:
            # Taking too long → replan
            await replan_intention(intention, reason="timeout")

    # Check if preconditions still hold
    preconditions_valid = await check_preconditions(intention)
    if not preconditions_valid:
        # World changed, plan invalid → replan
        await replan_intention(intention, reason="preconditions_invalid")


async def replan_intention(intention: EmployeeIntention, reason: str) -> None:
    """
    Abandon current plan and generate new plan.

    Triggered when:
    - Plan execution fails
    - Plan takes too long
    - World changes (preconditions invalid)
    """

    # Mark current intention as failed
    intention.status = IntentionStatus.FAILED
    intention.failed_at = datetime.utcnow()
    intention.context["failure_reason"] = reason
    await db.save(intention)

    # Generate new plan for same goal
    if intention.goal_id:
        goal = await db.get(EmployeeGoal, intention.goal_id)
        new_intention = await plan_for_goal(goal, beliefs, procedural_memory)

        # Learn from failure (update procedural memory)
        await update_procedural_memory_from_failure(intention, new_intention)
```

---

## Strategic Reasoning

### Purpose

High-level decision making that coordinates beliefs, goals, and intentions:
- **When to form new goals** (opportunity detection)
- **When to abandon goals** (goal becomes irrelevant/impossible)
- **When to replan** (plan isn't working)
- **How to allocate resources** across multiple goals

### Strategic Planning Cycle

```python
async def strategic_planning_cycle(
    employee: Employee,
    beliefs: BeliefSystem,
    goals: GoalSystem,
    intentions: IntentionStack
) -> None:
    """
    Periodic deep strategic reasoning.

    Called less frequently than tactical execution (e.g., once per hour vs every 5 min).

    This is computationally expensive (LLM calls for strategy generation).
    """

    # 1. Analyze current situation
    situation = await analyze_situation(employee, beliefs)

    # 2. Opportunity detection
    opportunities = await detect_opportunities(situation, beliefs)
    for opp in opportunities:
        # Form opportunistic goals
        goal = await form_opportunistic_goal(opp)
        await goals.add_goal(goal)

    # 3. Goal review
    active_goals = await goals.get_active_goals()
    for goal in active_goals:
        # Should we abandon this goal?
        if await should_abandon_goal(goal, beliefs):
            await goals.abandon_goal(goal, reason="no_longer_relevant")

        # Should we increase/decrease priority?
        new_priority = calculate_goal_priority(goal, beliefs)
        if new_priority != goal.priority:
            goal.priority = new_priority
            await db.save(goal)

    # 4. Resource allocation
    await allocate_resources(goals, intentions)

    # 5. Reflection (learn from recent actions)
    await reflection_cycle(employee, beliefs)
```

### Opportunity Detection

```python
async def detect_opportunities(
    situation: Dict[str, Any],
    beliefs: BeliefSystem
) -> List[Opportunity]:
    """
    Detect opportunities for proactive action.

    Uses pattern matching + LLM reasoning.
    """

    opportunities = []

    # Pattern-based detection (fast)
    patterns = [
        LowPipelinePattern(),
        ChurnRiskPattern(),
        UnansweredEmailPattern(),
        DeadlineApproachingPattern(),
        # ... more patterns
    ]

    for pattern in patterns:
        if pattern.matches(situation, beliefs):
            opp = pattern.create_opportunity(situation, beliefs)
            opportunities.append(opp)

    # LLM-based detection (slow, more creative)
    # Only run if no patterns matched or periodically for fresh perspective
    if not opportunities or random.random() < 0.1:
        llm_opps = await detect_opportunities_with_llm(situation, beliefs)
        opportunities.extend(llm_opps)

    return opportunities
```

### Should Replan?

```python
def should_replan(changed_beliefs: List[BeliefChange]) -> bool:
    """
    Decide if belief changes warrant replanning.

    Replanning is expensive (LLM calls), so only do it when necessary.
    """

    # Replan if:
    # 1. High-importance belief changed significantly
    important_changed = any(
        b.importance > 0.7 and abs(b.new_confidence - b.old_confidence) > 0.3
        for b in changed_beliefs
    )

    # 2. Belief related to current intentions changed
    relevant_to_intentions = any(
        b.subject in current_intention_subjects()
        for b in changed_beliefs
    )

    # 3. Belief about goal achievability changed
    goal_achievability_changed = any(
        b.predicate in ["achievable", "blocked", "deadline"]
        for b in changed_beliefs
    )

    return important_changed or relevant_to_intentions or goal_achievability_changed
```

---

## Integration with Proactive Loop

```python
async def run_proactive_loop():
    """
    Main proactive execution loop.

    Integrates BDI components with perception and action.
    """

    while employee.is_active:
        try:
            # ============ PERCEIVE ============
            # Gather observations from environment
            observations = await perceive_environment()

            # ============ UPDATE BELIEFS ============
            # Update world model
            changed_beliefs = await beliefs.update_beliefs(observations)

            # ============ STRATEGIC REASONING ============
            # Deep planning (only when needed)
            if should_replan(changed_beliefs):
                await strategic_planning_cycle()

            # ============ GOAL MANAGEMENT ============
            # Update goal progress
            for goal in goals.get_active_goals():
                await goals.update_goal_progress(goal, beliefs)

            # ============ INTENTION EXECUTION ============
            # Execute highest priority intention
            result = await intentions.execute_next_intention()

            # ============ LEARNING ============
            # Learn from execution result
            if result:
                await learning_cycle(result)

            # ============ SLEEP ============
            await asyncio.sleep(employee.config.loop_interval_seconds)

        except Exception as e:
            logger.error(f"Error in proactive loop: {e}", exc_info=True)
            await asyncio.sleep(employee.config.error_backoff_interval)
```

---

## Performance Considerations

### Database Queries

**Hot paths** (optimize these):
- `beliefs.get_belief(subject, predicate)` - Index on (employee_id, subject, predicate)
- `goals.get_active_goals()` - Index on (employee_id, status)
- `intentions.get_next_intention()` - Index on (employee_id, status, priority DESC)

**Cold paths** (less critical):
- `belief_history.get_changes()` - Historical analysis
- `procedural_memory.retrieve_procedures()` - Occasional retrieval

### Caching

```python
# Cache high-confidence beliefs (reduce DB queries)
@cache(ttl=300)  # 5 minutes
async def get_belief(subject: str, predicate: str) -> Optional[Belief]:
    # Only cache if confidence > 0.8
    belief = await db.query(...)
    if belief and belief.confidence > 0.8:
        return belief
    return belief

# Cache goal priorities (recalculate only when beliefs change)
@cache(ttl=600)  # 10 minutes
async def get_active_goals() -> List[EmployeeGoal]:
    return await db.query(...)
```

### Batch Operations

```python
# Batch belief updates (reduce DB round-trips)
async def update_beliefs(observations: List[Observation]) -> List[BeliefChange]:
    changes = []

    # Collect all updates
    for obs in observations:
        changes.extend(await process_observation(obs))

    # Single bulk update
    await db.bulk_update([c.belief for c in changes])

    return changes
```

---

## Testing Strategy

### Unit Tests

```python
async def test_belief_update_agreement():
    """Test belief confidence increases when observation agrees."""
    belief = Belief(subject="pipeline", predicate="coverage", object=2.0, confidence=0.7)
    observation = Observation(subject="pipeline", predicate="coverage", object=2.0)

    change = await update_existing_belief(belief, observation)

    assert change.new_confidence > 0.7
    assert belief.confidence > 0.7


async def test_belief_update_disagreement():
    """Test belief confidence decreases when observation disagrees."""
    belief = Belief(subject="pipeline", predicate="coverage", object=2.0, confidence=0.7)
    observation = Observation(subject="pipeline", predicate="coverage", object=1.5)

    change = await update_existing_belief(belief, observation)

    assert change.new_confidence < 0.7


async def test_goal_priority_deadline():
    """Test goal priority increases as deadline approaches."""
    goal = EmployeeGoal(
        goal_type=GoalType.ACHIEVEMENT,
        target={"deadline": (datetime.utcnow() + timedelta(days=3)).isoformat()}
    )

    priority = calculate_goal_priority(goal, beliefs)

    assert priority >= 8  # High priority (deadline in 3 days)
```

### Integration Tests

```python
async def test_bdi_full_cycle():
    """Test complete BDI cycle: observation → belief → goal → intention → execution."""

    # 1. Create observation (low pipeline)
    obs = Observation(subject="pipeline", predicate="coverage", object=1.5)

    # 2. Update beliefs
    changes = await beliefs.update_beliefs([obs])
    assert any(c.subject == "pipeline" for c in changes)

    # 3. Form goal
    goal = await form_goal_from_observation(obs, beliefs)
    assert goal.goal_type == GoalType.ACHIEVEMENT
    assert "pipeline" in goal.description.lower()

    # 4. Create intention
    intention = await plan_for_goal(goal, beliefs, procedural_memory)
    assert intention.goal_id == goal.id

    # 5. Execute intention
    result = await intentions.execute_next_intention()
    assert result.success
```

---

## Observability

### Metrics to Track

```python
# Belief system metrics
metrics.histogram("bdi.belief_update.duration", timer.elapsed())
metrics.gauge("bdi.beliefs.count", len(active_beliefs))
metrics.histogram("bdi.beliefs.confidence", [b.confidence for b in beliefs])

# Goal system metrics
metrics.gauge("bdi.goals.active", len(active_goals))
metrics.gauge("bdi.goals.in_progress", len(in_progress_goals))
metrics.histogram("bdi.goal_priority", [g.priority for g in goals])

# Intention system metrics
metrics.histogram("bdi.intention_execution.duration", timer.elapsed())
metrics.counter("bdi.intentions.completed", 1)
metrics.counter("bdi.intentions.failed", 1)
```

### Logging

```python
# Belief changes
logger.info(
    f"Belief updated: {belief.subject}.{belief.predicate}",
    extra={
        "employee_id": employee.id,
        "old_confidence": old_confidence,
        "new_confidence": new_confidence,
        "reason": "observation"
    }
)

# Goal lifecycle
logger.info(
    f"Goal activated: {goal.description}",
    extra={
        "employee_id": employee.id,
        "goal_id": goal.id,
        "priority": goal.priority
    }
)

# Intention execution
logger.info(
    f"Intention executed: {intention.description}",
    extra={
        "employee_id": employee.id,
        "intention_id": intention.id,
        "duration": duration,
        "success": result.success
    }
)
```

---

## Open Questions

1. **Belief decay function**: Linear vs exponential? (Current: linear, revisit Phase 3)
2. **Goal conflict resolution**: How to handle conflicting goals? (Current: priority-based, may need constraints)
3. **Intention interleaving**: Should we interleave multiple intentions or execute sequentially? (Current: sequential)
4. **LLM vs procedural memory**: When to use LLM for planning vs learned procedures? (Current: procedural first, LLM fallback)

---

## Next Steps

1. **Implement BeliefSystem class** (empla/core/bdi/beliefs.py)
2. **Implement GoalSystem class** (empla/core/bdi/goals.py)
3. **Implement IntentionStack class** (empla/core/bdi/intentions.py)
4. **Implement StrategicReasoning class** (empla/core/bdi/reasoning.py)
5. **Write comprehensive unit tests** (>80% coverage)
6. **Integrate with ProactiveExecutionLoop** (see docs/design/proactive-loop.md)

---

**References:**
- docs/design/database-schema.md - Database schema
- docs/design/core-models.md - Pydantic models
- docs/design/memory-system.md - Memory system implementation
- docs/design/proactive-loop.md - Proactive execution loop (Phase 2)
- ARCHITECTURE.md - System architecture

**Academic References:**
- Rao & Georgeff (1995): "BDI Agents: From Theory to Practice"
- Bratman (1987): "Intention, Plans, and Practical Reason"
- Wooldridge (2009): "An Introduction to MultiAgent Systems"
