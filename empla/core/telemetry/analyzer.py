"""
empla.core.telemetry.analyzer - Trajectory Analysis

Analyze BDI trajectories for patterns, performance, and insights.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from empla.core.telemetry.models import (
    BDITrajectory,
    GoalStatus,
    OutcomeStatus,
    TrajectorySession,
)


class TrajectoryAnalyzer:
    """
    Analyze BDI trajectories to extract insights and patterns.

    Provides:
    - Performance metrics (success rates, duration analysis)
    - Pattern detection (common belief → goal → action sequences)
    - Learning insights (what strategies work best)
    - Anomaly detection (unexpected behaviors)
    """

    def __init__(self, trajectories: list[BDITrajectory]):
        """
        Initialize analyzer with trajectories.

        Args:
            trajectories: List of trajectories to analyze
        """
        self.trajectories = trajectories

    # ==========================================
    # Performance Metrics
    # ==========================================

    def calculate_success_rate(self) -> float:
        """
        Calculate overall success rate across all trajectories.

        Returns:
            Success rate 0.0-1.0
        """
        if not self.trajectories:
            return 0.0

        successful = sum(1 for t in self.trajectories if t.overall_success)
        return successful / len(self.trajectories)

    def calculate_goal_achievement_rate(self) -> dict[str, float]:
        """
        Calculate goal achievement rates by goal type.

        Returns:
            Dict mapping goal type to achievement rate
        """
        goal_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"total": 0, "achieved": 0}
        )

        for traj in self.trajectories:
            for step in traj.steps:
                for goal in step.goals_formed + step.goals_updated:
                    goal_stats[goal.goal_type.value]["total"] += 1
                    if goal.status == GoalStatus.COMPLETED:
                        goal_stats[goal.goal_type.value]["achieved"] += 1

        return {
            goal_type: stats["achieved"] / stats["total"] if stats["total"] > 0 else 0.0
            for goal_type, stats in goal_stats.items()
        }

    def calculate_action_success_rate(self) -> dict[str, float]:
        """
        Calculate action success rates by action type.

        Returns:
            Dict mapping action type to success rate
        """
        action_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"total": 0, "successful": 0}
        )

        for traj in self.trajectories:
            for step in traj.steps:
                for action in step.actions_executed:
                    # Find corresponding outcome
                    outcome = next(
                        (o for o in step.outcomes if o.action_id == action.action_id), None
                    )
                    action_stats[action.action_type]["total"] += 1
                    if outcome and outcome.status == OutcomeStatus.SUCCESS:
                        action_stats[action.action_type]["successful"] += 1

        return {
            action_type: stats["successful"] / stats["total"] if stats["total"] > 0 else 0.0
            for action_type, stats in action_stats.items()
        }

    def calculate_average_duration(self) -> float:
        """
        Calculate average trajectory duration in seconds.

        Returns:
            Average duration in seconds
        """
        durations = []
        for traj in self.trajectories:
            if traj.ended_at and traj.started_at:
                delta = traj.ended_at - traj.started_at
                durations.append(delta.total_seconds())

        return sum(durations) / len(durations) if durations else 0.0

    def calculate_llm_efficiency(self) -> dict[str, float]:
        """
        Calculate LLM usage efficiency metrics.

        Returns:
            Dict with LLM efficiency metrics
        """
        total_calls = 0
        total_tokens = 0
        total_steps = 0

        for traj in self.trajectories:
            for step in traj.steps:
                total_calls += step.llm_calls
                total_tokens += step.llm_tokens_used
                total_steps += 1

        return {
            "avg_calls_per_step": total_calls / total_steps if total_steps > 0 else 0.0,
            "avg_tokens_per_step": total_tokens / total_steps if total_steps > 0 else 0.0,
            "avg_tokens_per_call": total_tokens / total_calls if total_calls > 0 else 0.0,
        }

    # ==========================================
    # Pattern Detection
    # ==========================================

    def find_common_belief_patterns(self, min_frequency: int = 3) -> list[dict[str, Any]]:
        """
        Find common belief patterns (subject-predicate pairs).

        Args:
            min_frequency: Minimum times a pattern must appear

        Returns:
            List of common patterns with frequency
        """
        pattern_counts: dict[tuple[str, str], int] = defaultdict(int)

        for traj in self.trajectories:
            for step in traj.steps:
                for belief in step.beliefs_updated:
                    pattern = (belief.subject, belief.predicate)
                    pattern_counts[pattern] += 1

        common_patterns = [
            {
                "subject": subject,
                "predicate": predicate,
                "frequency": count,
            }
            for (subject, predicate), count in pattern_counts.items()
            if count >= min_frequency
        ]

        return sorted(common_patterns, key=lambda x: x["frequency"], reverse=True)

    def find_successful_strategies(self) -> list[dict[str, Any]]:
        """
        Find intention strategies with high success rates.

        Returns:
            List of successful strategies
        """
        strategy_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"total": 0, "successful": 0}
        )

        for traj in self.trajectories:
            for step in traj.steps:
                for intention in step.intentions_planned:
                    strategy_desc = intention.description
                    strategy_stats[strategy_desc]["total"] += 1

                    # Check if actions for this intention were successful
                    intention_actions = [
                        a for a in step.actions_executed if a.intention_id == intention.intention_id
                    ]
                    if intention_actions:
                        outcomes = [
                            o
                            for o in step.outcomes
                            if o.action_id in [a.action_id for a in intention_actions]
                        ]
                        if outcomes and all(o.status == OutcomeStatus.SUCCESS for o in outcomes):
                            strategy_stats[strategy_desc]["successful"] += 1

        strategies = []
        for strategy, stats in strategy_stats.items():
            if stats["total"] >= 2:  # At least 2 occurrences
                success_rate = stats["successful"] / stats["total"]
                strategies.append(
                    {
                        "strategy": strategy,
                        "success_rate": success_rate,
                        "count": stats["total"],
                    }
                )

        return sorted(strategies, key=lambda x: x["success_rate"], reverse=True)

    # ==========================================
    # Temporal Analysis
    # ==========================================

    def analyze_time_to_goal(self) -> dict[str, float]:
        """
        Analyze average time from goal formation to completion.

        Returns:
            Dict mapping goal type to average completion time (seconds)
        """
        completion_times: dict[str, list[float]] = defaultdict(list)

        for traj in self.trajectories:
            goal_formed_times: dict[Any, datetime] = {}

            for step in traj.steps:
                # Track when goals are formed
                for goal in step.goals_formed:
                    goal_formed_times[goal.goal_id] = goal.timestamp

                # Track when goals are completed
                for goal in step.goals_updated:
                    if goal.status == GoalStatus.COMPLETED and goal.goal_id in goal_formed_times:
                        formed_time = goal_formed_times[goal.goal_id]
                        completed_time = goal.timestamp
                        duration = (completed_time - formed_time).total_seconds()
                        completion_times[goal.goal_type.value].append(duration)

        return {
            goal_type: sum(times) / len(times) if times else 0.0
            for goal_type, times in completion_times.items()
        }

    def analyze_peak_activity_times(self) -> dict[int, int]:
        """
        Analyze what times of day have most activity.

        Returns:
            Dict mapping hour (0-23) to activity count
        """
        activity_by_hour: dict[int, int] = defaultdict(int)

        for traj in self.trajectories:
            for step in traj.steps:
                hour = step.timestamp.hour
                activity_by_hour[hour] += len(step.actions_executed)

        return dict(sorted(activity_by_hour.items()))

    # ==========================================
    # Summary Reports
    # ==========================================

    def generate_summary_report(self) -> dict[str, Any]:
        """
        Generate comprehensive summary report.

        Returns:
            Dict with summary metrics
        """
        return {
            "total_trajectories": len(self.trajectories),
            "success_rate": self.calculate_success_rate(),
            "goal_achievement_rates": self.calculate_goal_achievement_rate(),
            "action_success_rates": self.calculate_action_success_rate(),
            "average_duration_seconds": self.calculate_average_duration(),
            "llm_efficiency": self.calculate_llm_efficiency(),
            "common_belief_patterns": self.find_common_belief_patterns()[:5],
            "successful_strategies": self.find_successful_strategies()[:5],
            "time_to_goal_completion": self.analyze_time_to_goal(),
        }

    def compare_sessions(self, session1: TrajectorySession, session2: TrajectorySession) -> dict[str, Any]:
        """
        Compare two sessions.

        Args:
            session1: First session
            session2: Second session

        Returns:
            Comparison metrics
        """
        return {
            "session1": {
                "id": str(session1.session_id),
                "duration_minutes": session1.total_duration_ms / 1000 / 60,
                "total_actions": session1.total_actions,
                "success_rate": (
                    session1.successful_actions / session1.total_actions
                    if session1.total_actions > 0
                    else 0.0
                ),
                "llm_tokens": session1.total_llm_tokens,
            },
            "session2": {
                "id": str(session2.session_id),
                "duration_minutes": session2.total_duration_ms / 1000 / 60,
                "total_actions": session2.total_actions,
                "success_rate": (
                    session2.successful_actions / session2.total_actions
                    if session2.total_actions > 0
                    else 0.0
                ),
                "llm_tokens": session2.total_llm_tokens,
            },
        }
