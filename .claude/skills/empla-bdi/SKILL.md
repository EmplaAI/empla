---
name: empla-bdi
description: BDI (Beliefs-Desires-Intentions) architecture patterns for empla. Use when implementing beliefs, goals, intentions, the proactive execution loop, or designing autonomous employee behavior.
---

# empla BDI Architecture

BDI (Beliefs-Desires-Intentions) is the cognitive architecture that makes empla employees autonomous.

## Core Concepts

### Beliefs (World Model)
What the employee knows/believes about the world.

```python
from empla.bdi import BeliefSystem

# Beliefs are stored with subject-predicate-object triples
await beliefs.add(
    subject="Acme Corp",
    predicate="deal_stage",
    object="negotiation",
    confidence=0.9,
    source="crm_sync"
)

# Query beliefs
stage = await beliefs.get("Acme Corp", "deal_stage")
# Returns: Belief(object="negotiation", confidence=0.9, ...)

# Beliefs decay over time - confidence decreases
# Use beliefs.refresh() to update stale beliefs
```

### Goals (Desires)
What the employee wants to achieve.

```python
from empla.bdi import GoalSystem
from empla.employees.config import GoalConfig

# Goals have types: achieve, maintain, avoid, query
goal = GoalConfig(
    goal_type="maintain",           # maintain this state continuously
    description="Maintain 3x pipeline coverage",
    priority=9,                     # 1-10, higher = more important
    target={"metric": "pipeline_coverage", "value": 3.0}
)

# Add goals to system
await goals.add_goal(
    goal_type=goal.goal_type,
    description=goal.description,
    priority=goal.priority,
    target=goal.target
)

# Get active goals (not completed, not failed)
active = await goals.get_active_goals()
```

### Intentions (Commitments)
What the employee is currently committed to doing.

```python
from empla.bdi import IntentionStack

# Intentions are formed from goals + beliefs
# The proactive loop handles this automatically

# Push new intention
await intentions.push(
    goal_id=goal.id,
    action_type="send_outreach_email",
    parameters={"prospect": "john@acme.com", "template": "intro"}
)

# Pop and execute top intention
intention = await intentions.pop()
if intention:
    result = await execute_intention(intention)
    await intentions.record_outcome(intention.id, result)
```

## The BDI Reasoning Cycle

The proactive loop implements this cycle continuously:

```
┌─────────────────────────────────────────────────────────────┐
│                    PROACTIVE LOOP                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. PERCEIVE ──────► Gather observations from capabilities  │
│        │              (emails, CRM updates, calendar, etc.) │
│        ▼                                                    │
│  2. UPDATE BELIEFS ─► Process observations into beliefs     │
│        │              (LLM extracts structured beliefs)     │
│        ▼                                                    │
│  3. DELIBERATE ────► Evaluate goals against beliefs         │
│        │              (Which goals need attention?)         │
│        ▼                                                    │
│  4. PLAN ──────────► Form intentions to achieve goals       │
│        │              (What actions to take?)               │
│        ▼                                                    │
│  5. EXECUTE ───────► Execute top intention                  │
│        │              (Call capability actions)             │
│        ▼                                                    │
│  6. REFLECT ───────► Learn from outcomes                    │
│        │              (Update procedural memory)            │
│        ▼                                                    │
│  [Wait interval, then repeat]                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `empla/bdi/beliefs.py` | BeliefSystem - manages world model |
| `empla/bdi/goals.py` | GoalSystem - manages goals |
| `empla/bdi/intentions.py` | IntentionStack - manages commitments |
| `empla/core/loop/execution.py` | ProactiveExecutionLoop - the main loop |

## Belief Extraction from Observations

The LLM extracts structured beliefs from unstructured observations:

```python
# Observation (from email capability)
observation = {
    "type": "email_received",
    "from": "john@acme.com",
    "subject": "Re: Proposal",
    "body": "We're interested but need to reduce the price by 20%"
}

# LLM extracts beliefs:
# - subject: "Acme Corp", predicate: "interest_level", object: "high"
# - subject: "Acme Corp", predicate: "objection", object: "price"
# - subject: "Acme Corp", predicate: "discount_requested", object: "20%"
```

## Goal Types

| Type | Description | Example |
|------|-------------|---------|
| `achieve` | One-time goal, complete when done | "Close deal with Acme" |
| `maintain` | Continuous goal, keep state | "Maintain 3x pipeline coverage" |
| `avoid` | Prevent a state | "Avoid customer churn" |
| `query` | Information gathering | "Understand competitor pricing" |

## Common Patterns

### Checking if Goal Needs Action

```python
async def should_work_on_goal(goal: Goal, beliefs: BeliefSystem) -> bool:
    if goal.goal_type == "maintain":
        current = await beliefs.get_metric(goal.target["metric"])
        return current < goal.target["value"]
    elif goal.goal_type == "achieve":
        return goal.status == "active"
    return False
```

### Forming Intentions from Goals

```python
async def form_intentions(goal: Goal, beliefs: BeliefSystem) -> list[Intention]:
    if goal.description.contains("pipeline"):
        # Check current pipeline
        coverage = await beliefs.get("pipeline", "coverage")
        if coverage.object < 3.0:
            return [
                Intention(action="research_new_prospects", priority=8),
                Intention(action="send_outreach_emails", priority=7),
            ]
    return []
```

## Testing BDI Components

```python
import pytest
from empla.bdi import BeliefSystem, GoalSystem

@pytest.fixture
async def belief_system(db_session, employee_id, tenant_id, llm_service):
    return BeliefSystem(db_session, employee_id, tenant_id, llm_service)

async def test_belief_update(belief_system):
    await belief_system.add("Acme", "stage", "discovery", confidence=0.8)
    belief = await belief_system.get("Acme", "stage")
    assert belief.object == "discovery"
    assert belief.confidence == 0.8
```

## Anti-Patterns

1. **Don't hard-code intentions** - Let the BDI cycle form them from goals + beliefs
2. **Don't skip belief updates** - Stale beliefs lead to wrong decisions
3. **Don't ignore confidence** - Low-confidence beliefs need verification
4. **Don't create goals without targets** - How will you know when it's achieved?
