"""
empla.core.telemetry.simulation - Simulation Integration

Integrate telemetry recording with simulation framework for testing and validation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from empla.core.telemetry.models import (
    BDITrajectory,
    TrajectorySession,
)
from empla.core.telemetry.recorder import TelemetryRecorder


class SimulationTelemetryRecorder(TelemetryRecorder):
    """
    Extended telemetry recorder for simulation environment.

    Adds simulation-specific features:
    - Simulated time control (for deterministic testing)
    - Environment state snapshots
    - Automated validation of BDI cycles
    - Debugging hooks
    """

    def __init__(
        self,
        employee_id: UUID,
        tenant_id: UUID,
        simulation_id: str | None = None,
        capture_env_state: bool = True,
    ):
        """
        Initialize simulation telemetry recorder.

        Args:
            employee_id: Employee being recorded
            tenant_id: Tenant ID
            simulation_id: Optional simulation identifier
            capture_env_state: Whether to capture environment state snapshots
        """
        super().__init__(employee_id, tenant_id)
        self.simulation_id = simulation_id
        self.capture_env_state = capture_env_state
        self.env_state_snapshots: list[dict[str, Any]] = []

    def capture_environment_state(self, env_state: dict[str, Any]) -> None:
        """
        Capture current simulation environment state.

        Args:
            env_state: Current environment state dictionary
        """
        if self.capture_env_state:
            snapshot = {
                "timestamp": datetime.now(),
                "state": env_state.copy(),
                "step_number": len(self.current_trajectory.steps) if self.current_trajectory else 0,
            }
            self.env_state_snapshots.append(snapshot)

    def validate_bdi_cycle(self) -> dict[str, bool]:
        """
        Validate that the current step follows proper BDI cycle.

        Returns:
            Dict of validation checks
        """
        if not self.current_step:
            return {"error": True, "message": "No active step"}

        validations = {
            "has_observations": len(self.current_step.observations) > 0,
            "has_beliefs": len(self.current_step.beliefs_updated) > 0,
            "has_goals": (
                len(self.current_step.goals_formed) > 0
                or len(self.current_step.goals_updated) > 0
            ),
            "has_intentions": len(self.current_step.intentions_planned) > 0,
            "has_actions": len(self.current_step.actions_executed) > 0,
            "has_outcomes": len(self.current_step.outcomes) > 0,
        }

        # Check if BDI flow makes sense
        validations["valid_flow"] = (
            validations["has_observations"]
            and (
                validations["has_beliefs"]
                or validations["has_goals"]
                or validations["has_actions"]
            )
        )

        return validations

    def get_simulation_summary(self) -> dict[str, Any]:
        """
        Get simulation-specific summary.

        Returns:
            Summary dict with simulation metrics
        """
        summary = self.get_session_summary()
        if summary:
            summary["simulation_id"] = self.simulation_id
            summary["env_state_snapshots"] = len(self.env_state_snapshots)
            summary["completed_trajectories_details"] = [
                t.summary() for t in self.completed_trajectories
            ]

        return summary or {}

    def export_simulation_report(self, filepath: str) -> None:
        """
        Export comprehensive simulation report.

        Args:
            filepath: Output file path (JSON)
        """
        import json

        report = {
            "simulation_id": self.simulation_id,
            "employee_id": str(self.employee_id),
            "session": (
                self.current_session.model_dump(mode="json") if self.current_session else None
            ),
            "trajectories": [t.model_dump(mode="json") for t in self.completed_trajectories],
            "environment_snapshots": self.env_state_snapshots,
            "summary": self.get_simulation_summary(),
        }

        with open(filepath, "w") as f:
            json.dump(report, f, indent=2, default=str)


def create_simulation_recorder(
    employee_id: UUID,
    tenant_id: UUID,
    simulation_name: str = "test_simulation",
) -> SimulationTelemetryRecorder:
    """
    Factory function to create simulation recorder.

    Args:
        employee_id: Employee ID
        tenant_id: Tenant ID
        simulation_name: Name of simulation

    Returns:
        Configured SimulationTelemetryRecorder
    """
    return SimulationTelemetryRecorder(
        employee_id=employee_id,
        tenant_id=tenant_id,
        simulation_id=f"{simulation_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        capture_env_state=True,
    )
