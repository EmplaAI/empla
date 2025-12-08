# BDI Trajectory Telemetry System - Usage Guide

## Overview

The telemetry system records complete BDI (Belief-Desire-Intention) cycles during autonomous agent execution, similar to Online RL trajectory recording but adapted for cognitive architecture.

**Flow:**
```
Observation → Belief Update → Goal Formation → Intention Planning →
Action Execution → Outcome → Learning
```

## Quick Start

### Basic Usage

```python
from uuid import UUID
from empla.core.telemetry import TelemetryRecorder, print_trajectory

# Create recorder
employee_id = UUID("...")
tenant_id = UUID("...")
recorder = TelemetryRecorder(employee_id, tenant_id)

# Start session
session = recorder.start_session(session_type="autonomous_loop")

# Start trajectory
trajectory = recorder.start_trajectory(
    trigger="scheduled_loop",
    trigger_data={"interval": "5m"}
)

# Start step
step = recorder.start_step()

# Log observation
recorder.log_observation(
    observation_type="perception",
    source="EmailCapability",
    priority=8,
    data={
        "type": "urgent_email",
        "from": "customer@acme.com",
        "subject": "System down"
    }
)

# Log belief update
recorder.log_belief(
    subject="customer_health",
    predicate="status",
    object="at_risk",
    confidence=0.95,
    source="observation",
    reasoning="Customer reported critical issue - urgent response needed"
)

# Log goal
goal = recorder.log_goal(
    goal_type="maintenance",
    description="Prevent customer churn",
    priority=10,
    target={"metric": "customer_health", "value": "healthy"},
    reasoning="Critical issue must be resolved immediately"
)

# Log intention
intention = recorder.log_intention(
    intention_type="tactic",
    description="Send empathetic response and schedule call",
    plan={
        "steps": [
            {"action": "send_email", "type": "empathetic_response"},
            {"action": "schedule_meeting", "duration": 30}
        ]
    },
    goal_id=goal.goal_id,
    priority=10,
    selection_rationale="Personal touch needed for critical situation"
)

# Log action
action = recorder.log_action(
    intention_id=intention.intention_id,
    action_type="send_email",
    capability_used="EmailCapability",
    parameters={
        "recipient_count": 1,
        "email_type": "customer_support",
        "tone": "empathetic"
    },
    execution_duration_ms=1250
)

# Log outcome
recorder.log_outcome(
    action_id=action.action_id,
    status="success",
    result={
        "email_sent": True,
        "delivery_confirmed": True
    },
    impact={"customer_response": "positive"},
    learning="Empathetic responses work well for critical issues"
)

# End step
recorder.end_step(llm_calls=2, llm_tokens=1500)

# End trajectory
recorder.end_trajectory(success=True, learnings=[
    "Quick empathetic response prevents churn",
    "Personal touch matters for critical issues"
])

# End session
session = recorder.end_session()

# Visualize
print_trajectory(trajectory)
```

## Visualization

### Terminal Visualization

```python
from empla.core.telemetry import (
    TrajectoryVisualizer,
    print_trajectory,
    print_trajectory_timeline,
    print_step,
    print_session
)

viz = TrajectoryVisualizer()

# Show trajectory summary
viz.show_trajectory_summary(trajectory)

# Show timeline view
viz.show_trajectory_timeline(trajectory)

# Show detailed step
viz.show_step_detail(trajectory.steps[0])

# Show session summary
viz.show_session_summary(session)

# Compare multiple trajectories
viz.compare_trajectories([traj1, traj2, traj3])
```

### Export Formats

```python
# Export to JSON
viz.export_trajectory_json(trajectory, "trajectory_report.json")

# Export to Markdown
viz.export_trajectory_markdown(trajectory, "trajectory_report.md")
```

## Analysis

### Analyzing Patterns

```python
from empla.core.telemetry.analyzer import TrajectoryAnalyzer

# Collect multiple trajectories
trajectories = recorder.get_completed_trajectories()

# Create analyzer
analyzer = TrajectoryAnalyzer(trajectories)

# Calculate metrics
success_rate = analyzer.calculate_success_rate()
goal_achievement = analyzer.calculate_goal_achievement_rate()
action_success = analyzer.calculate_action_success_rate()

# Find patterns
common_beliefs = analyzer.find_common_belief_patterns(min_frequency=3)
successful_strategies = analyzer.find_successful_strategies()

# Temporal analysis
time_to_goal = analyzer.analyze_time_to_goal()
peak_hours = analyzer.analyze_peak_activity_times()

# Generate report
report = analyzer.generate_summary_report()
print(f"Success Rate: {report['success_rate']:.2%}")
print(f"Avg Duration: {report['average_duration_seconds']:.1f}s")
```

## Simulation Integration

### Using with Simulation Framework

```python
from uuid import uuid4
from empla.core.telemetry.simulation import (
    SimulationTelemetryRecorder,
    create_simulation_recorder
)

# Create simulation recorder
recorder = create_simulation_recorder(
    employee_id=uuid4(),
    tenant_id=uuid4(),
    simulation_name="sales_ae_pipeline_building"
)

# Start session
session = recorder.start_session(
    session_type="simulation",
    config={
        "simulation_type": "autonomous_behavior",
        "scenario": "low_pipeline_response"
    }
)

# Start trajectory
trajectory = recorder.start_trajectory(
    trigger="low_pipeline_detected",
    trigger_data={"pipeline_coverage": 2.0, "target": 3.0}
)

# Start step
step = recorder.start_step()

# Capture environment state
from tests.simulation.environment import SimulatedEnvironment

env = SimulatedEnvironment()
recorder.capture_environment_state(env.get_state_summary())

# ... log observations, beliefs, goals, etc ...

# Validate BDI cycle
validation = recorder.validate_bdi_cycle()
if not validation["valid_flow"]:
    print("WARNING: Invalid BDI flow detected!")

# End step
recorder.end_step(llm_calls=3, llm_tokens=2000)

# End trajectory
recorder.end_trajectory(success=True)

# Export simulation report
recorder.export_simulation_report("simulation_report.json")

# Get summary
summary = recorder.get_simulation_summary()
print(f"Simulation: {summary['simulation_id']}")
print(f"Environment Snapshots: {summary['env_state_snapshots']}")
```

## Integration with ProactiveExecutionLoop

```python
from empla.core.loop.execution import ProactiveExecutionLoop
from empla.core.telemetry import TelemetryRecorder

class TelemetryEnabledLoop(ProactiveExecutionLoop):
    """Execution loop with telemetry recording."""

    def __init__(self, *args, telemetry_recorder=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.recorder = telemetry_recorder

    async def run_continuous_loop(self):
        """Run loop with telemetry."""
        if self.recorder:
            session = self.recorder.start_session()

        while self.is_active:
            if self.recorder:
                trajectory = self.recorder.start_trajectory(
                    trigger="scheduled_loop"
                )
                step = self.recorder.start_step()

            # PERCEIVE
            observations = await self.perceive_environment()
            if self.recorder:
                for obs in observations:
                    self.recorder.log_observation(
                        observation_type="perception",
                        source=obs.source,
                        priority=obs.priority,
                        data=obs.content
                    )

            # UPDATE BELIEFS
            # ... (log beliefs with recorder.log_belief())

            # FORM GOALS
            # ... (log goals with recorder.log_goal())

            # PLAN & EXECUTE
            # ... (log intentions and actions)

            if self.recorder:
                self.recorder.end_step(llm_calls=5, llm_tokens=3000)
                self.recorder.end_trajectory(success=True)

            await asyncio.sleep(self.reflection_interval)

        if self.recorder:
            self.recorder.end_session()
```

## Best Practices

### 1. Session Management

- Start one session per autonomous loop run
- End sessions properly to calculate metrics
- Use descriptive session types

### 2. Trajectory Granularity

- One trajectory = one trigger event (scheduled loop, external event, etc.)
- Multiple steps within a trajectory = multiple BDI cycles
- End trajectories with success status and learnings

### 3. Step Recording

- One step = one complete BDI cycle
- Record in order: Observations → Beliefs → Goals → Intentions → Actions → Outcomes
- Always end steps with LLM usage metrics

### 4. PII Safety

- Never log sensitive data in parameters (credentials, tokens, etc.)
- Use counts/domains instead of full email addresses
- Log hashes for subjects/IDs when needed

### 5. Performance

- Telemetry has minimal overhead (~1-5ms per logged item)
- Use async I/O for database persistence
- Batch write trajectories after completion

### 6. Analysis

- Collect 10+ trajectories before analysis
- Look for patterns in successful vs failed trajectories
- Use learnings to improve procedural memory

## Example: Complete E2E Recording

```python
# tests/simulation/test_telemetry_integration.py
import pytest
from uuid import uuid4
from empla.core.telemetry.simulation import create_simulation_recorder
from tests.simulation.environment import SimulatedEnvironment
from tests.simulation.capabilities import get_simulated_capabilities

@pytest.mark.asyncio
async def test_sales_ae_with_telemetry():
    """Test Sales AE with full telemetry recording."""

    # Setup
    employee_id = uuid4()
    tenant_id = uuid4()
    recorder = create_simulation_recorder(employee_id, tenant_id, "sales_ae_test")

    env = SimulatedEnvironment()
    capabilities = get_simulated_capabilities(env)

    # Start session
    session = recorder.start_session(session_type="simulation")

    # Start trajectory
    trajectory = recorder.start_trajectory(
        trigger="low_pipeline",
        trigger_data={"coverage": 2.0}
    )

    # Execute BDI cycle with telemetry
    step = recorder.start_step()

    # Perceive
    observations = []
    for cap in capabilities:
        obs = await cap.perceive()
        observations.extend(obs)
        for o in obs:
            recorder.log_observation(
                observation_type="perception",
                source=cap.capability_type.value,
                priority=o.priority,
                data=o.data
            )

    # Record environment state
    recorder.capture_environment_state(env.get_state_summary())

    # ... continue with beliefs, goals, intentions, actions ...

    # End
    recorder.end_step(llm_calls=3, llm_tokens=2500)
    recorder.end_trajectory(success=True)
    session = recorder.end_session()

    # Validate
    validation = recorder.validate_bdi_cycle()
    assert validation["valid_flow"]
    assert len(recorder.completed_trajectories) == 1

    # Export
    recorder.export_simulation_report("tests/output/telemetry_report.json")
```

## Troubleshooting

### No observations logged
- Ensure capabilities are providing observations
- Check perception logic is working
- Verify recorder.start_step() was called

### Invalid BDI flow
- Check that observations lead to beliefs
- Ensure goals are formed from beliefs
- Verify intentions reference goals

### Missing outcomes
- Ensure actions complete execution
- Log outcomes immediately after action execution
- Check outcome status mapping

### Large JSON exports
- Limit trajectory count in analysis
- Use summary() instead of full export
- Filter steps to most relevant ones
