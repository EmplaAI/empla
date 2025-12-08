"""
empla.core.telemetry - BDI Trajectory Telemetry System

Record complete belief-desire-intention cycles for autonomous agents.
Similar to Online RL trajectory recording (state → action → reward → next_state),
but adapted for BDI architecture:

    Observation → Belief Update → Goal Formation → Intention Planning →
    Action Execution → Outcome → Learning

This enables:
- Understanding agent decision-making
- Debugging autonomous behavior
- Performance analysis and optimization
- Training data collection for behavioral cloning
- Visualization of agent reasoning
"""

from empla.core.telemetry.models import (
    BDITrajectory,
    TrajectoryObservation,
    TrajectoryBelief,
    TrajectoryGoal,
    TrajectoryIntention,
    TrajectoryAction,
    TrajectoryOutcome,
    TrajectoryStep,
    TrajectorySession,
)
from empla.core.telemetry.recorder import TelemetryRecorder
from empla.core.telemetry.visualizer import (
    TrajectoryVisualizer,
    print_trajectory,
    print_trajectory_timeline,
    print_step,
    print_session,
)
from empla.core.telemetry.analyzer import TrajectoryAnalyzer
from empla.core.telemetry.simulation import (
    SimulationTelemetryRecorder,
    create_simulation_recorder,
)

__all__ = [
    # Models
    "BDITrajectory",
    "TrajectoryObservation",
    "TrajectoryBelief",
    "TrajectoryGoal",
    "TrajectoryIntention",
    "TrajectoryAction",
    "TrajectoryOutcome",
    "TrajectoryStep",
    "TrajectorySession",
    # Recorder
    "TelemetryRecorder",
    # Visualizer
    "TrajectoryVisualizer",
    "print_trajectory",
    "print_trajectory_timeline",
    "print_step",
    "print_session",
    # Analyzer
    "TrajectoryAnalyzer",
    # Simulation
    "SimulationTelemetryRecorder",
    "create_simulation_recorder",
]
