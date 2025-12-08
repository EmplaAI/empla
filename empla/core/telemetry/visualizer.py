"""
empla.core.telemetry.visualizer - Trajectory Visualization

Beautiful terminal visualization of BDI trajectories using rich library.
Makes it easy to understand agent reasoning and debug behavior.
"""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from empla.core.telemetry.models import (
    BDITrajectory,
    TrajectorySession,
    TrajectoryStep,
)


class TrajectoryVisualizer:
    """
    Visualize BDI trajectories in terminal using rich library.

    Provides multiple visualization formats:
    - Summary tables (session, trajectory, step summaries)
    - Detailed step views (complete BDI cycle)
    - Tree views (hierarchical goal → intention → action structure)
    - Timeline views (chronological event flow)
    - Export formats (JSON, Markdown)
    """

    def __init__(self, console: Console | None = None):
        """
        Initialize visualizer.

        Args:
            console: Rich console (creates new one if not provided)
        """
        self.console = console or Console()

    # ==========================================
    # Session Visualization
    # ==========================================

    def show_session_summary(self, session: TrajectorySession) -> None:
        """
        Display session summary table.

        Args:
            session: TrajectorySession to visualize
        """
        table = Table(title=f"Session Summary: {session.session_id}", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Session Type", session.session_type)
        table.add_row("Employee ID", str(session.employee_id))
        table.add_row("Started At", session.started_at.strftime("%Y-%m-%d %H:%M:%S"))
        if session.ended_at:
            table.add_row("Ended At", session.ended_at.strftime("%Y-%m-%d %H:%M:%S"))
            duration_min = session.total_duration_ms / 1000 / 60
            table.add_row("Duration", f"{duration_min:.2f} minutes")

        table.add_row("Total Steps", str(session.total_steps))
        table.add_row("Total Observations", str(session.total_observations))
        table.add_row("Total Beliefs", str(session.total_beliefs))
        table.add_row("Total Goals", str(session.total_goals))
        table.add_row("Total Intentions", str(session.total_intentions))
        table.add_row("Total Actions", str(session.total_actions))
        table.add_row(
            "Successful Actions",
            f"{session.successful_actions} ({session.successful_actions / session.total_actions * 100:.1f}%)"
            if session.total_actions > 0
            else "0",
        )
        table.add_row(
            "Failed Actions",
            f"{session.failed_actions} ({session.failed_actions / session.total_actions * 100:.1f}%)"
            if session.total_actions > 0
            else "0",
        )
        table.add_row("LLM Calls", str(session.total_llm_calls))
        table.add_row("LLM Tokens", f"{session.total_llm_tokens:,}")

        self.console.print(table)

    # ==========================================
    # Trajectory Visualization
    # ==========================================

    def show_trajectory_summary(self, trajectory: BDITrajectory) -> None:
        """
        Display trajectory summary.

        Args:
            trajectory: BDITrajectory to visualize
        """
        summary = trajectory.summary()

        table = Table(
            title=f"Trajectory Summary: {trajectory.trajectory_id}", show_header=True
        )
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Trigger", trajectory.trigger)
        table.add_row("Started At", trajectory.started_at.strftime("%Y-%m-%d %H:%M:%S"))
        if trajectory.ended_at:
            table.add_row("Ended At", trajectory.ended_at.strftime("%Y-%m-%d %H:%M:%S"))
            duration_sec = summary["duration_ms"] / 1000 if summary["duration_ms"] else 0
            table.add_row("Duration", f"{duration_sec:.2f} seconds")

        table.add_row("Total Steps", str(summary["total_steps"]))
        table.add_row("Observations", str(summary["total_observations"]))
        table.add_row("Beliefs Updated", str(summary["total_beliefs"]))
        table.add_row("Goals Formed", str(summary["total_goals"]))
        table.add_row("Intentions Planned", str(summary["total_intentions"]))
        table.add_row("Actions Executed", str(summary["total_actions"]))
        table.add_row("Outcomes", str(summary["total_outcomes"]))

        table.add_row("Goals Achieved", str(summary["goals_achieved"]), style="green")
        table.add_row("Goals Blocked", str(summary["goals_blocked"]), style="red")
        table.add_row(
            "Overall Success", "✓" if summary["overall_success"] else "✗",
            style="green" if summary["overall_success"] else "red"
        )

        if summary["key_learnings"]:
            learnings_text = "\n".join(f"• {l}" for l in summary["key_learnings"])
            table.add_row("Key Learnings", learnings_text, style="yellow")

        self.console.print(table)

    def show_trajectory_timeline(self, trajectory: BDITrajectory) -> None:
        """
        Display trajectory as timeline of steps.

        Args:
            trajectory: BDITrajectory to visualize
        """
        tree = Tree(f"[bold]Trajectory Timeline: {trajectory.trigger}[/bold]")

        for step in trajectory.steps:
            step_node = tree.add(
                f"[cyan]Step {step.step_number}[/cyan] "
                f"({step.cycle_duration_ms / 1000:.2f}s)"
            )

            # Observations
            if step.observations:
                obs_node = step_node.add(f"[yellow]Observations ({len(step.observations)})[/yellow]")
                for obs in step.observations[:3]:  # Show first 3
                    obs_node.add(
                        f"[dim]{obs.observation_type.value}[/dim] from {obs.source} "
                        f"(priority: {obs.priority})"
                    )
                if len(step.observations) > 3:
                    obs_node.add(f"[dim]... and {len(step.observations) - 3} more[/dim]")

            # Beliefs
            if step.beliefs_updated:
                belief_node = step_node.add(
                    f"[blue]Beliefs Updated ({len(step.beliefs_updated)})[/blue]"
                )
                for belief in step.beliefs_updated[:3]:
                    belief_node.add(
                        f"[dim]{belief.subject}[/dim] {belief.predicate} {belief.object} "
                        f"(conf: {belief.confidence:.2f})"
                    )
                if len(step.beliefs_updated) > 3:
                    belief_node.add(f"[dim]... and {len(step.beliefs_updated) - 3} more[/dim]")

            # Goals
            if step.goals_formed or step.goals_updated:
                goal_count = len(step.goals_formed) + len(step.goals_updated)
                goal_node = step_node.add(f"[green]Goals ({goal_count})[/green]")
                for goal in step.goals_formed[:2]:
                    goal_node.add(
                        f"[green]NEW:[/green] {goal.description} (priority: {goal.priority})"
                    )
                for goal in step.goals_updated[:2]:
                    goal_node.add(
                        f"[yellow]UPDATED:[/yellow] {goal.description} → {goal.status.value}"
                    )

            # Intentions
            if step.intentions_planned:
                intent_node = step_node.add(
                    f"[magenta]Intentions ({len(step.intentions_planned)})[/magenta]"
                )
                for intention in step.intentions_planned[:2]:
                    intent_node.add(
                        f"{intention.intention_type.value}: {intention.description}"
                    )
                if len(step.intentions_planned) > 2:
                    intent_node.add(f"[dim]... and {len(step.intentions_planned) - 2} more[/dim]")

            # Actions & Outcomes
            if step.actions_executed:
                action_node = step_node.add(
                    f"[red]Actions ({len(step.actions_executed)})[/red]"
                )
                for action in step.actions_executed[:3]:
                    # Find corresponding outcome
                    outcome = next(
                        (o for o in step.outcomes if o.action_id == action.action_id), None
                    )
                    outcome_str = f" → {outcome.status.value}" if outcome else ""
                    action_node.add(
                        f"{action.action_type} via {action.capability_used}{outcome_str}"
                    )
                if len(step.actions_executed) > 3:
                    action_node.add(f"[dim]... and {len(step.actions_executed) - 3} more[/dim]")

        self.console.print(tree)

    # ==========================================
    # Step Visualization
    # ==========================================

    def show_step_detail(self, step: TrajectoryStep) -> None:
        """
        Display detailed view of a single step.

        Args:
            step: TrajectoryStep to visualize
        """
        # Create main panel
        content = []

        content.append(f"[bold cyan]Step {step.step_number}[/bold cyan]")
        content.append(f"Duration: {step.cycle_duration_ms / 1000:.2f}s")
        content.append(f"LLM Calls: {step.llm_calls}, Tokens: {step.llm_tokens_used:,}")
        content.append("")

        # Observations
        if step.observations:
            content.append("[bold yellow]📥 Observations[/bold yellow]")
            for obs in step.observations:
                content.append(
                    f"  • [{obs.observation_type.value}] {obs.source} "
                    f"(priority: {obs.priority})"
                )
                if obs.data:
                    data_str = json.dumps(obs.data, indent=4)[:200]
                    content.append(f"    [dim]{data_str}...[/dim]")
            content.append("")

        # Beliefs
        if step.beliefs_updated:
            content.append("[bold blue]🧠 Beliefs Updated[/bold blue]")
            for belief in step.beliefs_updated:
                content.append(
                    f"  • {belief.subject} {belief.predicate} {belief.object} "
                    f"(confidence: {belief.confidence:.2f})"
                )
                content.append(f"    [dim]Reasoning: {belief.reasoning[:100]}...[/dim]")
            content.append("")

        # Goals
        if step.goals_formed:
            content.append("[bold green]🎯 Goals Formed[/bold green]")
            for goal in step.goals_formed:
                content.append(
                    f"  • [{goal.goal_type.value}] {goal.description} "
                    f"(priority: {goal.priority})"
                )
                content.append(f"    [dim]Reasoning: {goal.reasoning[:100]}...[/dim]")
            content.append("")

        if step.goals_updated:
            content.append("[bold yellow]🎯 Goals Updated[/bold yellow]")
            for goal in step.goals_updated:
                content.append(f"  • {goal.description} → {goal.status.value}")
            content.append("")

        # Intentions
        if step.intentions_planned:
            content.append("[bold magenta]📋 Intentions Planned[/bold magenta]")
            for intention in step.intentions_planned:
                content.append(
                    f"  • [{intention.intention_type.value}] {intention.description}"
                )
                content.append(
                    f"    [dim]Rationale: {intention.selection_rationale[:100]}...[/dim]"
                )
            content.append("")

        # Actions
        if step.actions_executed:
            content.append("[bold red]⚡ Actions Executed[/bold red]")
            for action in step.actions_executed:
                content.append(
                    f"  • {action.action_type} via {action.capability_used} "
                    f"({action.execution_duration_ms:.0f}ms)"
                )
                if action.retries > 0:
                    content.append(f"    [yellow]Retries: {action.retries}[/yellow]")
            content.append("")

        # Outcomes
        if step.outcomes:
            content.append("[bold green]✓ Outcomes[/bold green]")
            for outcome in step.outcomes:
                status_color = "green" if outcome.status.value == "success" else "red"
                content.append(f"  • [{status_color}]{outcome.status.value}[/{status_color}]")
                if outcome.learning:
                    content.append(f"    [yellow]Learning: {outcome.learning}[/yellow]")
            content.append("")

        panel = Panel(
            "\n".join(content),
            title=f"Step {step.step_number} Detail",
            border_style="cyan",
        )
        self.console.print(panel)

    # ==========================================
    # Comparison & Analytics
    # ==========================================

    def compare_trajectories(self, trajectories: list[BDITrajectory]) -> None:
        """
        Compare multiple trajectories side-by-side.

        Args:
            trajectories: List of trajectories to compare
        """
        table = Table(title="Trajectory Comparison", show_header=True)
        table.add_column("Metric", style="cyan")

        for i, traj in enumerate(trajectories[:5]):  # Max 5 trajectories
            table.add_column(f"Trajectory {i + 1}", style="green")

        # Add comparison rows
        metrics = [
            ("Trigger", lambda t: t.trigger),
            ("Steps", lambda t: str(len(t.steps))),
            ("Observations", lambda t: str(sum(len(s.observations) for s in t.steps))),
            ("Beliefs", lambda t: str(sum(len(s.beliefs_updated) for s in t.steps))),
            ("Goals", lambda t: str(sum(len(s.goals_formed) for s in t.steps))),
            ("Actions", lambda t: str(sum(len(s.actions_executed) for s in t.steps))),
            ("Success Rate", lambda t: self._calc_success_rate(t)),
            ("Duration", lambda t: self._format_duration(t)),
        ]

        for metric_name, metric_func in metrics:
            row = [metric_name]
            for traj in trajectories[:5]:
                row.append(metric_func(traj))
            table.add_row(*row)

        self.console.print(table)

    def _calc_success_rate(self, trajectory: BDITrajectory) -> str:
        """Calculate success rate for trajectory."""
        total_outcomes = sum(len(s.outcomes) for s in trajectory.steps)
        if total_outcomes == 0:
            return "N/A"

        successful = sum(
            len([o for o in s.outcomes if o.status.value == "success"]) for s in trajectory.steps
        )
        rate = successful / total_outcomes * 100
        return f"{rate:.1f}%"

    def _format_duration(self, trajectory: BDITrajectory) -> str:
        """Format trajectory duration."""
        if not trajectory.ended_at or not trajectory.started_at:
            return "N/A"
        delta = trajectory.ended_at - trajectory.started_at
        return f"{delta.total_seconds():.1f}s"

    # ==========================================
    # Export Formats
    # ==========================================

    def export_trajectory_json(self, trajectory: BDITrajectory, filepath: str) -> None:
        """
        Export trajectory to JSON file.

        Args:
            trajectory: Trajectory to export
            filepath: Output file path
        """
        with open(filepath, "w") as f:
            json.dump(trajectory.model_dump(mode="json"), f, indent=2, default=str)

        self.console.print(f"[green]✓ Exported trajectory to {filepath}[/green]")

    def export_trajectory_markdown(self, trajectory: BDITrajectory, filepath: str) -> None:
        """
        Export trajectory to Markdown file.

        Args:
            trajectory: Trajectory to export
            filepath: Output file path
        """
        lines = []

        # Header
        lines.append(f"# Trajectory: {trajectory.trajectory_id}")
        lines.append("")
        lines.append(f"**Trigger:** {trajectory.trigger}")
        lines.append(f"**Started:** {trajectory.started_at}")
        if trajectory.ended_at:
            lines.append(f"**Ended:** {trajectory.ended_at}")
        lines.append("")

        # Summary
        summary = trajectory.summary()
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- Total Steps: {summary['total_steps']}")
        lines.append(f"- Observations: {summary['total_observations']}")
        lines.append(f"- Beliefs: {summary['total_beliefs']}")
        lines.append(f"- Goals: {summary['total_goals']}")
        lines.append(f"- Actions: {summary['total_actions']}")
        lines.append(f"- Success: {'Yes' if summary['overall_success'] else 'No'}")
        lines.append("")

        # Steps
        lines.append("## Steps")
        lines.append("")

        for step in trajectory.steps:
            lines.append(f"### Step {step.step_number}")
            lines.append("")

            if step.observations:
                lines.append("**Observations:**")
                for obs in step.observations:
                    lines.append(f"- [{obs.observation_type.value}] {obs.source}")
                lines.append("")

            if step.beliefs_updated:
                lines.append("**Beliefs:**")
                for belief in step.beliefs_updated:
                    lines.append(
                        f"- {belief.subject} {belief.predicate} {belief.object} "
                        f"(conf: {belief.confidence:.2f})"
                    )
                lines.append("")

            if step.goals_formed:
                lines.append("**Goals:**")
                for goal in step.goals_formed:
                    lines.append(f"- {goal.description} (priority: {goal.priority})")
                lines.append("")

            if step.actions_executed:
                lines.append("**Actions:**")
                for action in step.actions_executed:
                    lines.append(f"- {action.action_type} via {action.capability_used}")
                lines.append("")

        with open(filepath, "w") as f:
            f.write("\n".join(lines))

        self.console.print(f"[green]✓ Exported trajectory to {filepath}[/green]")


# ==========================================
# Quick Display Functions
# ==========================================


def print_trajectory(trajectory: BDITrajectory) -> None:
    """Quick print of trajectory summary."""
    viz = TrajectoryVisualizer()
    viz.show_trajectory_summary(trajectory)


def print_trajectory_timeline(trajectory: BDITrajectory) -> None:
    """Quick print of trajectory timeline."""
    viz = TrajectoryVisualizer()
    viz.show_trajectory_timeline(trajectory)


def print_step(step: TrajectoryStep) -> None:
    """Quick print of step details."""
    viz = TrajectoryVisualizer()
    viz.show_step_detail(step)


def print_session(session: TrajectorySession) -> None:
    """Quick print of session summary."""
    viz = TrajectoryVisualizer()
    viz.show_session_summary(session)
