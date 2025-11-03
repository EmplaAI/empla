# Proactive Execution Loop Design

> **Status:** Draft
> **Author:** Claude Code
> **Date:** 2025-10-30
> **Phase:** Phase 1 - Core Infrastructure

---

## Overview

The **Proactive Execution Loop** is the "heartbeat" of empla's autonomous operation. It's what transforms empla from a reactive task executor into a proactive digital employee that continuously monitors, reasons, and acts on its own initiative.

**What makes this different from traditional agent frameworks:**

❌ **Traditional Agents**: Wait for commands → Execute → Return to idle
✅ **empla Employees**: Continuously monitor → Identify opportunities → Plan → Execute → Learn → Repeat

**Core Philosophy:**
- Employees should work **without instructions** (autonomy first)
- Employees should **identify their own work** (proactive, not reactive)
- Employees should **improve from experience** (learning and adaptation)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│              Proactive Execution Loop (Continuous)                │
│                                                                    │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐     │
│  │ PERCEIVE │──▶│  REASON  │──▶│   ACT    │──▶│  LEARN   │──┐  │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘  │  │
│       ▲                                                        │  │
│       └────────────────────────────────────────────────────────┘  │
│                                                                    │
│  Default Interval: 5 minutes (configurable per employee/role)     │
└──────────────────────────────────────────────────────────────────┘
```

### Integration with BDI Engine

```
Proactive Loop
      │
      ├──▶ PERCEIVE ───────────▶ Observations (raw events)
      │                               │
      ├──▶ UPDATE BELIEFS ◀───────────┘
      │         │
      │         ▼
      ├──▶ STRATEGIC REASONING
      │    (if beliefs changed significantly)
      │         │
      │         ▼
      ├──▶ GOAL MANAGEMENT
      │    (update progress, form new goals)
      │         │
      │         ▼
      ├──▶ INTENTION EXECUTION
      │    (execute highest priority intention)
      │         │
      │         ▼
      └──▶ LEARNING
           (update procedural memory, beliefs)
```

---

## Component 1: Perceive Environment

### Purpose

Gather observations from the environment - everything the employee needs to know to make decisions.

**What to perceive:**
- External events (emails, calendar changes, mentions, customer activity)
- Internal state (goal progress, resource availability, system metrics)
- Opportunities (market signals, buying signals, customer health changes)
- Problems (blockers, risks, anomalies)

### Data Model

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

class Observation(BaseModel):
    """Single observation from environment"""

    # Identity
    observation_id: UUID
    employee_id: UUID
    tenant_id: UUID

    # Content
    observation_type: str  # "email_received", "calendar_event", "metric_threshold", etc.
    source: str           # "email", "calendar", "metric_monitor", "external_api"
    content: Dict[str, Any]  # Structured observation data

    # Context
    timestamp: datetime
    priority: int = Field(ge=1, le=10, default=5)

    # Processing
    processed: bool = False
    belief_changes: List[UUID] = []  # Beliefs updated from this observation


class PerceptionResult(BaseModel):
    """Result of perception cycle"""

    observations: List[Observation]
    opportunities_detected: int
    problems_detected: int
    risks_detected: int

    # Performance
    perception_duration_ms: float
    sources_checked: List[str]
```

### Perception Algorithm

```python
async def perceive_environment() -> PerceptionResult:
    """
    Gather observations from all sources.

    Called every loop iteration to understand current environment state.
    """

    start_time = time.time()
    observations = []

    # 1. CHECK EXTERNAL SOURCES (async in parallel)
    external_tasks = [
        check_email_inbox(),
        check_calendar_events(),
        check_chat_mentions(),
        check_customer_events(),
        check_crm_updates(),
    ]

    external_results = await asyncio.gather(*external_tasks, return_exceptions=True)

    for result in external_results:
        if isinstance(result, Exception):
            logger.error(f"Perception error: {result}")
            metrics.increment("perception_errors")
            continue
        observations.extend(result)

    # 2. CHECK INTERNAL STATE
    internal_observations = await check_internal_state()
    observations.extend(internal_observations)

    # 3. MONITOR METRICS (detect threshold crossings)
    metric_observations = await monitor_metrics()
    observations.extend(metric_observations)

    # 4. CHECK TIME-BASED TRIGGERS (scheduled events)
    time_observations = await check_time_triggers()
    observations.extend(time_observations)

    # 5. CLASSIFY OBSERVATIONS
    opportunities = [o for o in observations if o.observation_type.startswith("opportunity_")]
    problems = [o for o in observations if o.observation_type.startswith("problem_")]
    risks = [o for o in observations if o.observation_type.startswith("risk_")]

    # 6. PRIORITIZE OBSERVATIONS
    observations = prioritize_observations(observations)

    duration_ms = (time.time() - start_time) * 1000

    # 7. LOG AND METRICS
    logger.info(
        f"Perception complete: {len(observations)} observations",
        extra={
            "employee_id": employee.id,
            "observations": len(observations),
            "opportunities": len(opportunities),
            "problems": len(problems),
            "risks": len(risks),
            "duration_ms": duration_ms
        }
    )

    metrics.histogram("perception.duration_ms", duration_ms)
    metrics.gauge("perception.observations", len(observations))

    return PerceptionResult(
        observations=observations,
        opportunities_detected=len(opportunities),
        problems_detected=len(problems),
        risks_detected=len(risks),
        perception_duration_ms=duration_ms,
        sources_checked=[t.__name__ for t in external_tasks]
    )
```

### Perception Sources

```python
async def check_email_inbox() -> List[Observation]:
    """Check for new emails"""
    # Get unread emails since last check
    emails = await email_client.get_unread_emails(since=last_check_time)

    observations = []
    for email in emails:
        obs = Observation(
            observation_id=uuid4(),
            employee_id=employee.id,
            tenant_id=employee.tenant_id,
            observation_type="email_received",
            source="email",
            content={
                "from": email.from_addr,
                "subject": email.subject,
                "body": email.body[:500],  # Preview
                "importance": email.importance,
                "thread_id": email.thread_id
            },
            timestamp=email.received_at,
            priority=calculate_email_priority(email)
        )
        observations.append(obs)

    return observations


async def check_calendar_events() -> List[Observation]:
    """Check for upcoming calendar events"""
    # Get events in next 15 minutes (preparation time)
    upcoming = await calendar_client.get_upcoming_events(
        start=datetime.utcnow(),
        end=datetime.utcnow() + timedelta(minutes=15)
    )

    observations = []
    for event in upcoming:
        obs = Observation(
            observation_id=uuid4(),
            employee_id=employee.id,
            tenant_id=employee.tenant_id,
            observation_type="calendar_event_upcoming",
            source="calendar",
            content={
                "event_id": event.id,
                "title": event.title,
                "start_time": event.start_time.isoformat(),
                "attendees": [a.email for a in event.attendees],
                "meeting_url": event.meeting_url
            },
            timestamp=datetime.utcnow(),
            priority=8  # High priority - meeting soon
        )
        observations.append(obs)

    return observations


async def monitor_metrics() -> List[Observation]:
    """Monitor key metrics for threshold crossings"""
    observations = []

    # Define metric thresholds (role-specific)
    thresholds = employee.config.metric_thresholds
    # Example for Sales AE:
    # {
    #     "pipeline_coverage": {"operator": "<", "value": 3.0, "priority": 8},
    #     "response_time_hours": {"operator": ">", "value": 4.0, "priority": 7},
    #     "meetings_this_week": {"operator": "<", "value": 10, "priority": 6},
    # }

    for metric_name, threshold in thresholds.items():
        # Get current metric value
        current_value = await get_metric_value(metric_name)

        # Check if threshold crossed
        if threshold_crossed(current_value, threshold):
            obs = Observation(
                observation_id=uuid4(),
                employee_id=employee.id,
                tenant_id=employee.tenant_id,
                observation_type=f"metric_threshold_{metric_name}",
                source="metric_monitor",
                content={
                    "metric": metric_name,
                    "current_value": current_value,
                    "threshold": threshold["value"],
                    "operator": threshold["operator"]
                },
                timestamp=datetime.utcnow(),
                priority=threshold.get("priority", 5)
            )
            observations.append(obs)

    return observations


async def check_time_triggers() -> List[Observation]:
    """Check time-based triggers (scheduled events)"""
    observations = []

    # Check if any scheduled triggers should fire
    triggers = employee.config.scheduled_triggers
    # Example:
    # [
    #     CronTrigger("0 9 * * 1", "weekly_strategic_planning"),
    #     CronTrigger("0 6 * * *", "daily_priority_review"),
    # ]

    for trigger in triggers:
        if trigger.should_fire(datetime.utcnow()):
            obs = Observation(
                observation_id=uuid4(),
                employee_id=employee.id,
                tenant_id=employee.tenant_id,
                observation_type=f"scheduled_{trigger.action}",
                source="time_trigger",
                content={"trigger_type": trigger.action},
                timestamp=datetime.utcnow(),
                priority=trigger.priority
            )
            observations.append(obs)

    return observations
```

---

## Component 2: Strategic Reasoning Cycle

### Purpose

Deep strategic thinking to analyze situation, identify gaps, generate strategies, and form/abandon goals.

**When to run:**
- Significant belief changes (world model updated)
- Scheduled (e.g., weekly strategic review)
- Goal progress stalled
- New opportunities/problems detected

### Algorithm

```python
async def strategic_planning_cycle() -> None:
    """
    Periodic deep strategic reasoning.

    This is computationally expensive (multiple LLM calls), so only run when needed.
    """

    logger.info(
        "Starting strategic planning cycle",
        extra={"employee_id": employee.id}
    )

    start_time = time.time()

    # 1. ANALYZE SITUATION
    situation = await comprehensive_situation_analysis()
    # Returns:
    # - Current state (beliefs, metrics, resources)
    # - Goal progress vs targets
    # - External factors (market, competition, seasonality)
    # - Historical patterns

    # 2. GAP ANALYSIS (Where are we vs where we want to be?)
    gaps = analyze_gaps(
        current=situation.current_state,
        desired=situation.desired_state
    )

    # Example for Sales AE:
    # Gap: Pipeline coverage 2.1x (current) vs 3.0x (target) = -0.9x gap

    # 3. ROOT CAUSE ANALYSIS (Why do gaps exist?)
    root_causes = await analyze_root_causes(gaps, situation)
    # Example:
    # - Not enough outbound activity (20 emails/week vs 50 target)
    # - Low response rate (10% vs 20% benchmark)
    # - Stalled deals not being progressed

    # 4. OPPORTUNITY DETECTION
    opportunities = await detect_opportunities(situation, beliefs)
    # Pattern-based + LLM-based detection
    # Example:
    # - 5 leads from target ICP just raised funding (buying signal)
    # - Competitor X had outage (competitive opportunity)

    # 5. GENERATE STRATEGIES
    strategies = await generate_strategies(
        gaps=gaps,
        root_causes=root_causes,
        opportunities=opportunities,
        constraints=situation.constraints
    )

    # Example strategies for pipeline gap:
    # 1. "Warm up cold leads with personalized video outreach"
    # 2. "Accelerate stalled deals with executive engagement"
    # 3. "Expand into new market segment (fintech)"
    # 4. "Partner with marketing for co-selling campaign"

    # 6. EVALUATE STRATEGIES
    scored_strategies = await evaluate_strategies(
        strategies,
        criteria={
            'success_probability': 0.3,
            'impact': 0.3,
            'resource_cost': 0.2,
            'time_to_value': 0.2
        }
    )

    # 7. SELECT BEST STRATEGY
    selected = select_strategy(scored_strategies)

    # 8. DECOMPOSE INTO TACTICAL PLANS
    tactical_plans = decompose_strategy_to_plans(selected)

    # 9. FORM/UPDATE GOALS
    for plan in tactical_plans:
        # Check if goal already exists
        existing_goal = await goals.find_goal_for_plan(plan)

        if existing_goal:
            # Update existing goal
            await goals.update_goal_priority(existing_goal, plan.priority)
        else:
            # Form new goal
            new_goal = await goals.form_goal_from_plan(plan)
            await goals.add_goal(new_goal)

    # 10. GOAL REVIEW (Abandon irrelevant goals)
    active_goals = await goals.get_active_goals()
    for goal in active_goals:
        if await should_abandon_goal(goal, situation):
            await goals.abandon_goal(
                goal,
                reason="No longer relevant after strategic review"
            )

    # 11. DOCUMENT STRATEGY
    await memory.episodic.record_strategic_decision(
        situation=situation,
        gaps=gaps,
        strategies_considered=strategies,
        chosen=selected,
        rationale=selected.selection_rationale
    )

    duration_ms = (time.time() - start_time) * 1000

    logger.info(
        "Strategic planning cycle complete",
        extra={
            "employee_id": employee.id,
            "duration_ms": duration_ms,
            "strategies_evaluated": len(strategies),
            "strategy_selected": selected.name,
            "new_goals": len(tactical_plans)
        }
    )

    metrics.histogram("strategic_planning.duration_ms", duration_ms)
    metrics.gauge("strategic_planning.strategies_evaluated", len(strategies))
```

### Deciding When to Replan

```python
def should_replan(changed_beliefs: List[BeliefChange]) -> bool:
    """
    Decide if belief changes warrant strategic replanning.

    Replanning is expensive, so only do it when necessary.
    """

    # Replan if:

    # 1. High-importance belief changed significantly
    important_changed = any(
        b.importance > 0.7 and abs(b.new_confidence - b.old_confidence) > 0.3
        for b in changed_beliefs
    )

    # 2. Belief related to current intentions changed
    current_subjects = {i.context.get("subject") for i in intentions.get_active()}
    relevant_to_intentions = any(
        b.subject in current_subjects
        for b in changed_beliefs
    )

    # 3. Belief about goal achievability changed
    goal_beliefs_changed = any(
        b.predicate in ["achievable", "blocked", "deadline", "priority"]
        for b in changed_beliefs
    )

    # 4. Scheduled strategic planning time
    scheduled = check_scheduled_planning()

    return (
        important_changed
        or relevant_to_intentions
        or goal_beliefs_changed
        or scheduled
    )
```

---

## Component 3: Intention Execution

### Purpose

Execute the highest priority intention from the intention stack.

**Execution logic:**
- Get highest priority planned intention
- Check dependencies satisfied
- Execute based on type (action, tactic, strategy)
- Update intention status
- Record outcome

### Algorithm

```python
async def execute_intentions() -> Optional[IntentionResult]:
    """
    Execute highest priority intention.

    Returns None if no work to do or dependencies not satisfied.
    """

    # 1. Get next intention to execute
    intention = await intentions.get_next_intention()

    if not intention:
        logger.debug("No intentions to execute")
        return None

    # 2. Check dependencies
    if not await intentions.dependencies_satisfied(intention):
        logger.debug(
            f"Intention {intention.id} waiting on dependencies",
            extra={"intention_id": intention.id, "dependencies": intention.dependencies}
        )
        return None

    # 3. Mark as in progress
    await intentions.start_intention(intention)

    logger.info(
        f"Executing intention: {intention.description}",
        extra={
            "employee_id": employee.id,
            "intention_id": intention.id,
            "intention_type": intention.intention_type,
            "priority": intention.priority
        }
    )

    # 4. Execute based on type
    try:
        start_time = time.time()

        if intention.intention_type == IntentionType.ACTION:
            result = await execute_action(intention)
        elif intention.intention_type == IntentionType.TACTIC:
            result = await execute_tactic(intention)
        elif intention.intention_type == IntentionType.STRATEGY:
            result = await execute_strategy(intention)
        else:
            raise ValueError(f"Unknown intention type: {intention.intention_type}")

        duration_ms = (time.time() - start_time) * 1000

        # 5. Mark as completed
        await intentions.complete_intention(intention, result)

        logger.info(
            f"Intention completed: {intention.description}",
            extra={
                "employee_id": employee.id,
                "intention_id": intention.id,
                "success": result.success,
                "duration_ms": duration_ms
            }
        )

        metrics.histogram("intention_execution.duration_ms", duration_ms)
        metrics.increment("intentions.completed")

        return result

    except Exception as e:
        # 6. Handle failure
        logger.error(
            f"Intention failed: {intention.description}",
            exc_info=True,
            extra={
                "employee_id": employee.id,
                "intention_id": intention.id,
                "error": str(e)
            }
        )

        await intentions.fail_intention(intention, error=str(e))

        metrics.increment("intentions.failed")

        # Decide if we should replan or retry
        if should_replan_after_failure(intention, e):
            await handle_intention_failure(intention, e)

        return None
```

---

## Component 4: Reflection & Learning Cycle

### Purpose

Learn from execution outcomes to improve future performance.

**What to learn:**
- Successful patterns → Strengthen in procedural memory
- Failed patterns → Record failure modes
- Effectiveness beliefs → Update based on outcomes
- Strategy effectiveness → Adjust scoring for future selection

### Algorithm

```python
async def reflection_cycle(result: IntentionResult) -> None:
    """
    Learn from execution result.

    Updates procedural memory and beliefs based on what worked/failed.
    """

    logger.info(
        "Starting reflection cycle",
        extra={
            "employee_id": employee.id,
            "intention_id": result.intention_id
        }
    )

    # 1. Retrieve intention and outcome
    intention = await db.get(EmployeeIntention, result.intention_id)

    # 2. Record outcome in episodic memory
    await memory.episodic.record_outcome(
        intention=intention,
        result=result,
        timestamp=datetime.utcnow()
    )

    # 3. Update procedural memory
    if result.success:
        # Successful execution - reinforce pattern
        await memory.procedural.strengthen_workflow(
            workflow_type=intention.intention_type,
            plan=intention.plan,
            success_metric=result.outcome.get("metric")
        )

        logger.info(
            f"Strengthened workflow: {intention.description}",
            extra={
                "employee_id": employee.id,
                "workflow_type": intention.intention_type
            }
        )
    else:
        # Failed execution - record failure mode
        await memory.procedural.record_failure_pattern(
            workflow_type=intention.intention_type,
            plan=intention.plan,
            failure_mode=result.outcome.get("error"),
            context=intention.context
        )

        logger.warning(
            f"Recorded failure pattern: {intention.description}",
            extra={
                "employee_id": employee.id,
                "workflow_type": intention.intention_type,
                "failure_mode": result.outcome.get("error")
            }
        )

    # 4. Update effectiveness beliefs
    # Example: "personalized_video_outreach effectiveness high"
    if "tactic" in intention.context:
        tactic = intention.context["tactic"]
        effectiveness = 0.8 if result.success else 0.2

        await beliefs.update_or_create_belief(
            subject=tactic,
            predicate="effectiveness",
            object=effectiveness,
            source=BeliefSource.OBSERVATION,
            evidence=[result.intention_id]
        )

    # 5. Update goal progress (if intention was tied to goal)
    if intention.goal_id:
        goal = await db.get(EmployeeGoal, intention.goal_id)
        await goals.update_goal_progress(goal, beliefs)

    # 6. Learn from patterns (periodic deep reflection)
    if should_do_deep_reflection():
        await deep_reflection_cycle()

    logger.info(
        "Reflection cycle complete",
        extra={"employee_id": employee.id}
    )


async def deep_reflection_cycle() -> None:
    """
    Periodic deep reflection on patterns and learnings.

    Run less frequently (e.g., daily) to identify meta-patterns.
    """

    logger.info("Starting deep reflection cycle")

    # 1. Analyze recent outcomes (last 24 hours)
    recent_outcomes = await memory.episodic.get_recent_outcomes(hours=24)

    # 2. Identify patterns using LLM
    patterns = await analyze_outcome_patterns(recent_outcomes)
    # Example patterns:
    # - "Video outreach gets 3x response rate vs text emails"
    # - "Deals with >2 stakeholders take 30% longer to close"
    # - "Follow-up within 1 hour increases response rate by 40%"

    # 3. Update procedural memory with meta-patterns
    for pattern in patterns:
        await memory.procedural.record_meta_pattern(
            pattern=pattern.description,
            evidence=pattern.supporting_outcomes,
            confidence=pattern.confidence
        )

    # 4. Update beliefs based on patterns
    for pattern in patterns:
        await beliefs.update_or_create_belief(
            subject=pattern.subject,
            predicate=pattern.predicate,
            object=pattern.insight,
            source=BeliefSource.INFERENCE,
            evidence=pattern.supporting_outcomes
        )

    # 5. Identify skill gaps
    gaps = identify_skill_gaps(recent_outcomes)
    # Example: "Objection handling success rate only 60% (target 80%)"

    # 6. Form learning goals
    for gap in gaps:
        learning_goal = await goals.form_learning_goal(gap)
        await goals.add_goal(learning_goal)

    logger.info(
        "Deep reflection complete",
        extra={
            "employee_id": employee.id,
            "patterns_identified": len(patterns),
            "skill_gaps": len(gaps)
        }
    )
```

---

## Main Loop Implementation

```python
class ProactiveExecutionLoop:
    """
    The continuous autonomous operation loop.

    This is the "heartbeat" of empla - what makes employees truly autonomous.
    """

    def __init__(
        self,
        employee: Employee,
        beliefs: BeliefSystem,
        goals: GoalSystem,
        intentions: IntentionStack,
        memory: EmployeeMemorySystem,
        config: Optional[LoopConfig] = None
    ):
        self.employee = employee
        self.beliefs = beliefs
        self.goals = goals
        self.intentions = intentions
        self.memory = memory

        # Configuration
        self.config = config or LoopConfig()
        self.cycle_interval = self.config.cycle_interval_seconds
        self.error_backoff_interval = self.config.error_backoff_seconds

        # State
        self.is_running = False
        self.cycle_count = 0
        self.last_strategic_planning = None

    async def start(self) -> None:
        """Start the proactive execution loop"""

        if self.is_running:
            logger.warning(f"Loop already running for employee {self.employee.id}")
            return

        self.is_running = True

        logger.info(
            f"Starting proactive loop for {self.employee.name}",
            extra={
                "employee_id": self.employee.id,
                "cycle_interval": self.cycle_interval
            }
        )

        await self.run_continuous_loop()

    async def stop(self) -> None:
        """Stop the proactive execution loop"""

        self.is_running = False

        logger.info(
            f"Stopping proactive loop for {self.employee.name}",
            extra={"employee_id": self.employee.id}
        )

    async def run_continuous_loop(self) -> None:
        """
        Main continuous execution loop.

        This runs until employee is deactivated or loop is stopped.
        """

        while self.is_running and self.employee.is_active:
            try:
                cycle_start = time.time()
                self.cycle_count += 1

                logger.debug(
                    f"Loop cycle {self.cycle_count} starting",
                    extra={"employee_id": self.employee.id}
                )

                # ============ PERCEIVE ============
                # Gather observations from environment
                perception_result = await self.perceive_environment()

                # ============ UPDATE BELIEFS ============
                # Process observations into world model updates
                changed_beliefs = await self.beliefs.update_beliefs(
                    perception_result.observations
                )

                logger.info(
                    f"Beliefs updated: {len(changed_beliefs)} changes",
                    extra={
                        "employee_id": self.employee.id,
                        "changed_beliefs": len(changed_beliefs)
                    }
                )

                # ============ STRATEGIC REASONING ============
                # Deep planning when needed (expensive)
                if self.should_replan(changed_beliefs):
                    await self.strategic_planning_cycle()
                    self.last_strategic_planning = datetime.utcnow()

                # ============ GOAL MANAGEMENT ============
                # Update goal progress based on current beliefs
                active_goals = await self.goals.get_active_goals()
                for goal in active_goals:
                    await self.goals.update_goal_progress(goal, self.beliefs)

                # ============ INTENTION EXECUTION ============
                # Execute highest priority work
                result = await self.execute_intentions()

                # ============ LEARNING ============
                # Reflect on outcomes and learn
                if result:
                    await self.reflection_cycle(result)

                # ============ METRICS ============
                cycle_duration = time.time() - cycle_start

                metrics.histogram("proactive_loop.cycle_duration", cycle_duration)
                metrics.gauge("proactive_loop.cycle_count", self.cycle_count)

                logger.debug(
                    f"Loop cycle {self.cycle_count} complete",
                    extra={
                        "employee_id": self.employee.id,
                        "duration_seconds": cycle_duration
                    }
                )

                # ============ SLEEP ============
                # Wait before next cycle
                await asyncio.sleep(self.cycle_interval)

            except Exception as e:
                # NEVER let loop crash - log error and continue
                logger.error(
                    f"Error in proactive loop cycle {self.cycle_count}",
                    exc_info=True,
                    extra={
                        "employee_id": self.employee.id,
                        "cycle_count": self.cycle_count,
                        "error": str(e)
                    }
                )

                metrics.increment("proactive_loop.errors")

                # Back off on errors to avoid thundering herd
                await asyncio.sleep(self.error_backoff_interval)

        logger.info(
            f"Proactive loop ended for {self.employee.name}",
            extra={
                "employee_id": self.employee.id,
                "total_cycles": self.cycle_count
            }
        )
```

---

## Configuration

```python
class LoopConfig(BaseModel):
    """Configuration for proactive execution loop"""

    # Timing
    cycle_interval_seconds: int = 300  # 5 minutes default
    error_backoff_seconds: int = 60    # 1 minute on error

    # Strategic planning frequency
    strategic_planning_interval_hours: int = 24  # Daily strategic review
    force_strategic_planning_on_significant_change: bool = True

    # Perception configuration
    perception_sources: List[str] = [
        "email",
        "calendar",
        "chat",
        "crm",
        "metrics"
    ]

    # Execution limits
    max_intentions_per_cycle: int = 1  # Execute one intention per cycle
    max_cycle_duration_seconds: int = 600  # 10 minutes max per cycle

    # Learning
    deep_reflection_interval_hours: int = 24  # Daily deep reflection
    enable_cross_employee_learning: bool = True


# Role-specific configurations
ROLE_CONFIGS = {
    "sales_ae": LoopConfig(
        cycle_interval_seconds=300,  # 5 minutes
        strategic_planning_interval_hours=168,  # Weekly
    ),
    "csm": LoopConfig(
        cycle_interval_seconds=600,  # 10 minutes (less urgent than sales)
        strategic_planning_interval_hours=168,  # Weekly
    ),
    "pm": LoopConfig(
        cycle_interval_seconds=900,  # 15 minutes (strategic work, less reactive)
        strategic_planning_interval_hours=24,  # Daily
    ),
}
```

---

## Performance Considerations

### Cycle Time Budget

Default 5-minute cycle breakdown:
- **Perceive**: 10-30 seconds (async I/O)
- **Update Beliefs**: 5-10 seconds (DB queries + logic)
- **Strategic Reasoning**: 0-60 seconds (only when triggered, expensive)
- **Goal Management**: 5-10 seconds (DB queries)
- **Intention Execution**: 60-240 seconds (actual work, variable)
- **Learning**: 5-10 seconds (DB writes)
- **Buffer**: 60-120 seconds

### Optimization Strategies

1. **Async Perception**: Run all perception sources in parallel
2. **Lazy Strategic Planning**: Only run when beliefs change significantly
3. **Caching**: Cache high-confidence beliefs (reduce DB queries)
4. **Batch Operations**: Batch DB updates where possible
5. **Timeouts**: Set timeouts on all I/O operations
6. **Graceful Degradation**: If cycle takes too long, skip low-priority tasks

### Monitoring

Key metrics to track:
- `proactive_loop.cycle_duration` - How long each cycle takes
- `proactive_loop.cycle_count` - Total cycles executed
- `proactive_loop.errors` - Error count
- `perception.duration_ms` - Perception phase timing
- `strategic_planning.duration_ms` - Strategic planning timing (expensive)
- `intention_execution.duration_ms` - Execution timing

---

## Testing Strategy

### Unit Tests

```python
async def test_perceive_environment():
    """Test perception gathers observations correctly"""
    loop = ProactiveExecutionLoop(employee, beliefs, goals, intentions, memory)

    result = await loop.perceive_environment()

    assert len(result.observations) > 0
    assert result.perception_duration_ms > 0


async def test_should_replan_on_significant_belief_change():
    """Test replanning triggered by important belief changes"""
    belief_change = BeliefChange(
        belief_id=uuid4(),
        change_type="updated",
        importance=0.9,
        old_confidence=0.5,
        new_confidence=0.9
    )

    assert should_replan([belief_change]) == True


async def test_execute_intentions_with_no_work():
    """Test graceful handling when no intentions exist"""
    loop = ProactiveExecutionLoop(employee, beliefs, goals, intentions, memory)

    result = await loop.execute_intentions()

    assert result is None  # No work to do
```

### Integration Tests

```python
async def test_full_loop_cycle():
    """Test complete loop cycle executes successfully"""
    loop = ProactiveExecutionLoop(employee, beliefs, goals, intentions, memory)

    # Add a test intention
    intention = EmployeeIntention(
        employee_id=employee.id,
        intention_type=IntentionType.ACTION,
        plan={"type": "send_email", "params": {...}}
    )
    await db.add(intention)

    # Run single cycle
    await loop.run_single_cycle()  # Test helper

    # Verify cycle completed
    assert loop.cycle_count == 1

    # Verify intention was executed
    updated_intention = await db.get(EmployeeIntention, intention.id)
    assert updated_intention.status == IntentionStatus.COMPLETED
```

### E2E Tests

```python
async def test_employee_runs_autonomously_for_one_hour():
    """Test employee operates autonomously for 1 hour"""

    # Start loop
    loop = ProactiveExecutionLoop(employee, beliefs, goals, intentions, memory)
    loop_task = asyncio.create_task(loop.start())

    # Let run for 1 hour (in test: 5 seconds with fast cycle)
    await asyncio.sleep(5)

    # Stop loop
    await loop.stop()
    await loop_task

    # Verify autonomous operation
    assert loop.cycle_count >= 5  # At least 5 cycles
    assert loop.cycle_count < 10  # Not too many

    # Verify work was done
    completed_intentions = await db.query(
        EmployeeIntention
    ).filter(
        EmployeeIntention.status == IntentionStatus.COMPLETED
    ).all()

    assert len(completed_intentions) > 0  # Some work completed
```

---

## Error Handling

### Error Scenarios

1. **Perception failure** (e.g., email API down)
   - Log error, skip that source, continue with other sources
   - Don't block entire cycle

2. **Strategic planning timeout** (LLM taking too long)
   - Cancel planning, defer to next cycle
   - Don't block intention execution

3. **Intention execution failure**
   - Mark intention as failed
   - Trigger replanning for that goal
   - Continue loop (don't crash)

4. **Database connection lost**
   - Retry with exponential backoff
   - If persistent, pause loop and alert

5. **Out of memory**
   - Clear working memory cache
   - Force garbage collection
   - Reduce perception scope temporarily

### Recovery Strategies

```python
async def safe_execute_with_retry(
    func: Callable,
    max_retries: int = 3,
    backoff_base: float = 2.0
) -> Any:
    """Execute function with retry and exponential backoff"""

    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                # Last attempt failed, raise
                raise

            # Exponential backoff
            wait_time = backoff_base ** attempt
            logger.warning(
                f"Attempt {attempt + 1} failed, retrying in {wait_time}s",
                extra={"error": str(e)}
            )
            await asyncio.sleep(wait_time)
```

---

## Open Questions

1. **Cycle interval tuning**: How to automatically adjust cycle interval based on workload?
2. **Multi-employee coordination**: How to prevent thundering herd when many employees run loops simultaneously?
3. **Cost optimization**: How to minimize LLM API costs during strategic planning?
4. **Interruptions**: How to handle urgent events that need immediate action (can't wait for next cycle)?

---

## Next Steps

1. **Implement ProactiveExecutionLoop class** (empla/core/loop/execution.py)
2. **Implement perception methods** (empla/core/loop/perception.py)
3. **Implement strategic reasoning** (empla/core/loop/reasoning.py)
4. **Implement reflection/learning** (empla/core/loop/learning.py)
5. **Write comprehensive unit tests** (>80% coverage)
6. **Write integration tests** (BDI + Proactive Loop)
7. **Write E2E test** (employee runs autonomously for 1 hour)

---

**References:**
- docs/design/bdi-engine.md - BDI architecture
- docs/design/memory-system.md - Memory systems
- ARCHITECTURE.md - System architecture (Layer 1.2, 1.3)
- ADR-006 - Proactive loop over event-driven architecture

**Research References:**
- Wooldridge & Jennings (1995): "Intelligent Agents: Theory and Practice"
- Bratman (1987): "Intention, Plans, and Practical Reason"
- Rao & Georgeff (1995): "BDI Agents: From Theory to Practice"
