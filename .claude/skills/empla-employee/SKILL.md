---
name: empla-employee
description: How to create new employee types in empla. Use when implementing new digital employees like Sales AE, CSM, PM, or custom employee roles. Covers the DigitalEmployee base class and required methods.
---

# Creating empla Employees

## Employee Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     DigitalEmployee                         │
│  Base class that integrates all empla systems               │
├─────────────────────────────────────────────────────────────┤
│  - BDI Engine (beliefs, goals, intentions)                  │
│  - Memory Systems (episodic, semantic, procedural, working) │
│  - Capability Registry                                      │
│  - Proactive Execution Loop                                 │
│  - LLM Service                                              │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   ┌─────────┐          ┌─────────┐          ┌─────────┐
   │ SalesAE │          │   CSM   │          │   PM    │
   │         │          │         │          │         │
   │ Sales   │          │ Customer│          │ Product │
   │ focused │          │ success │          │ focused │
   └─────────┘          └─────────┘          └─────────┘
```

## Creating a New Employee Type

### Step 1: Create the Employee Class

```python
# empla/employees/my_role.py

from empla.employees.base import DigitalEmployee
from empla.employees.config import GoalConfig
from empla.employees.personality import Personality

class MyRoleEmployee(DigitalEmployee):
    """
    My Role digital employee.

    Describe what this employee does and its key responsibilities.
    """

    @property
    def default_personality(self) -> Personality:
        """Define personality traits for this role."""
        return Personality(
            # Big Five traits (0.0-1.0)
            openness=0.7,
            conscientiousness=0.8,
            extraversion=0.6,
            agreeableness=0.7,
            neuroticism=0.3,

            # Communication style
            communication={
                "tone": "professional",
                "formality": 0.7,
                "verbosity": 0.5,
            },

            # Work style
            proactivity=0.8,
            persistence=0.7,
            attention_to_detail=0.8,
        )

    @property
    def default_goals(self) -> list[GoalConfig]:
        """Define default goals for this role."""
        return [
            GoalConfig(
                goal_type="maintain",
                description="Maintain high quality standards",
                priority=8,
                target={"metric": "quality_score", "value": 0.9}
            ),
            GoalConfig(
                goal_type="achieve",
                description="Complete weekly objectives",
                priority=7,
            ),
        ]

    @property
    def default_capabilities(self) -> list[str]:
        """Define which capabilities this role needs."""
        return ["email", "calendar", "slack"]

    async def on_start(self) -> None:
        """Custom initialization when employee starts."""
        # Add role-specific beliefs
        await self.beliefs.add(
            subject="self",
            predicate="role",
            object="my_role",
            confidence=1.0
        )

        # Load any role-specific data
        # ...

    async def on_stop(self) -> None:
        """Custom cleanup when employee stops."""
        # Save any state
        # Close any role-specific connections
        pass
```

### Step 2: Export from Package

```python
# empla/employees/__init__.py

from empla.employees.base import DigitalEmployee
from empla.employees.sales_ae import SalesAE
from empla.employees.csm import CustomerSuccessManager
from empla.employees.my_role import MyRoleEmployee  # Add this

__all__ = [
    "DigitalEmployee",
    "SalesAE",
    "CustomerSuccessManager",
    "MyRoleEmployee",  # Add this
]
```

### Step 3: Add Tests

```python
# tests/unit/test_employees_my_role.py

import pytest
from empla.employees import MyRoleEmployee
from empla.employees.config import EmployeeConfig

def test_my_role_creation():
    config = EmployeeConfig(
        name="Test Employee",
        role="my_role",
        email="test@company.com"
    )
    employee = MyRoleEmployee(config)

    assert employee.name == "Test Employee"
    assert employee.role == "my_role"

def test_my_role_default_goals():
    config = EmployeeConfig(
        name="Test",
        role="my_role",
        email="test@company.com"
    )
    employee = MyRoleEmployee(config)

    goals = employee.default_goals
    assert len(goals) > 0
    assert any(g.goal_type == "maintain" for g in goals)

def test_my_role_default_capabilities():
    config = EmployeeConfig(
        name="Test",
        role="my_role",
        email="test@company.com"
    )
    employee = MyRoleEmployee(config)

    caps = employee.default_capabilities
    assert "email" in caps
```

## Employee Configuration

### EmployeeConfig

```python
from empla.employees.config import EmployeeConfig, GoalConfig, LoopSettings, LLMSettings

config = EmployeeConfig(
    # Required
    name="Jordan Chen",
    role="sales_ae",
    email="jordan@company.com",

    # Optional - override defaults
    tenant_id=uuid4(),
    personality=Personality(extraversion=0.95),  # Override default

    goals=[  # Override default goals
        GoalConfig(
            goal_type="achieve",
            description="Close Q4 deals",
            priority=10
        )
    ],

    capabilities=["email", "crm", "calendar"],  # Override default capabilities

    loop=LoopSettings(
        cycle_interval_seconds=300,  # 5 minutes
        strategic_planning_interval_hours=24,
    ),

    llm=LLMSettings(
        primary_model="claude-sonnet-4",
        fallback_model="gpt-4o",
        temperature=0.7,
    ),
)
```

## Employee Lifecycle

```
┌─────────────┐
│   CREATE    │  config = EmployeeConfig(...)
│             │  employee = SalesAE(config)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   START     │  await employee.start()
│             │  - Validates config
│             │  - Connects to database
│             │  - Initializes BDI, Memory, Capabilities
│             │  - Creates/loads employee record
│             │  - Calls on_start()
│             │  - Starts proactive loop (if run_loop=True)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   RUNNING   │  Proactive loop running continuously
│             │  - perceive → update beliefs → deliberate → plan → execute → reflect
│             │  - Or call run_once() for single cycle
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    STOP     │  await employee.stop()
│             │  - Stops proactive loop
│             │  - Calls on_stop()
│             │  - Shuts down capabilities
│             │  - Closes database connection
└─────────────┘
```

## Key Methods

| Method | Purpose |
|--------|---------|
| `start(run_loop=True)` | Initialize and optionally start continuous loop |
| `stop()` | Graceful shutdown |
| `run_once()` | Execute single proactive cycle |
| `get_status()` | Get current employee status |
| `on_start()` | Override for custom initialization |
| `on_stop()` | Override for custom cleanup |

## Accessing Components

```python
# After start()
employee.beliefs      # BeliefSystem
employee.goals        # GoalSystem
employee.intentions   # IntentionStack
employee.memory       # MemorySystem (episodic, semantic, procedural, working)
employee.capabilities # CapabilityRegistry
employee.llm          # LLMService

# Properties
employee.employee_id  # UUID (set after start)
employee.tenant_id    # UUID
employee.is_running   # bool
employee.personality  # Personality
```

## Existing Employees

### SalesAE (Sales Account Executive)

```python
from empla.employees import SalesAE

# Goals: Pipeline coverage, deal progression, response time
# Capabilities: email, calendar, crm
# Personality: High extraversion, persistence, proactivity
```

### CustomerSuccessManager (CSM)

```python
from empla.employees import CustomerSuccessManager

# Goals: Customer health, retention, NPS
# Capabilities: email, calendar, support_tickets
# Personality: High agreeableness, conscientiousness
```

## Best Practices

1. **Keep goals measurable** - Include targets with metrics
2. **Personality should match role** - Sales = high extraversion, etc.
3. **Only request needed capabilities** - Don't enable all by default
4. **Implement on_start/on_stop** - For role-specific setup/cleanup
5. **Add comprehensive tests** - Unit + integration + e2e
6. **Document the role** - What it does, how it operates
