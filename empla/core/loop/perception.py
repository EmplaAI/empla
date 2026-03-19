"""
empla.core.loop.perception - Perception capabilities for the execution loop.

Provides the PerceptionMixin class which encapsulates all environment
perception logic: agentic LLM-driven perception, prompt building, and
context formatting for goals and beliefs.

Used as a mixin by ProactiveExecutionLoop.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from empla.core.loop.models import Observation, PerceptionResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PerceptionMixin:
    """Mixin providing perception capabilities for the proactive execution loop.

    Expects the host class to provide:
        - self.employee: Employee instance
        - self.llm_service: Optional LLMService
        - self.tool_router: Optional tool router
        - self.beliefs: BeliefSystem
        - self.goals: GoalSystem
        - self.memory: MemorySystem
        - self.config: LoopConfig
        - self._identity_prompt: Optional[str]
    """

    async def perceive_environment(self) -> PerceptionResult:
        """
        Collects observations from the environment via agentic perception.

        Uses LLM-driven perception when LLM and tools are available.
        Returns empty result otherwise.

        Returns:
            PerceptionResult with observations, opportunity/problem/risk counts,
            duration, and sources checked.
        """
        start_time = time.time()

        if self.llm_service is not None and self.tool_router is not None:
            tool_schemas = self.tool_router.get_all_tool_schemas(self.employee.id)
            if tool_schemas:
                try:
                    result = await self._perceive_agentic(tool_schemas)
                    duration_ms = max(0.01, (time.time() - start_time) * 1000)
                    result.perception_duration_ms = duration_ms
                    return result
                except Exception:
                    logger.warning(
                        "Agentic perception failed",
                        exc_info=True,
                        extra={"employee_id": str(self.employee.id)},
                    )

        # No LLM or no tools — return empty result
        duration_ms = max(0.01, (time.time() - start_time) * 1000)
        return PerceptionResult(
            observations=[],
            perception_duration_ms=duration_ms,
        )

    async def _perceive_agentic(self, tool_schemas: list[dict[str, Any]]) -> PerceptionResult:
        """LLM-driven perception: check environment based on goals.

        The LLM receives current goals and available tools, then decides
        what to check. This replaces hardcoded perceive() methods with
        goal-aware, adaptive environment scanning.

        Args:
            tool_schemas: Available tool schemas for the LLM.

        Returns:
            PerceptionResult with observations from tool calls.
        """
        from empla.llm.models import Message

        # Build context for perception
        goals_context = await self._format_goals_for_perception()
        beliefs_context = await self._format_recent_beliefs_for_perception()

        system_prompt = self._build_perception_system_prompt()

        # Include working memory context (current attention/focus)
        working_context = ""
        if hasattr(self.memory, "working"):
            try:
                context_summary = await self.memory.working.get_context_summary()
                items = context_summary.get("total_items", 0)
                if items > 0:
                    parts = []
                    for key, val in context_summary.items():
                        if key.startswith("active_") and val:
                            type_name = key.replace("active_", "")
                            summaries = [
                                str(v.get("content", v))[:100]
                                if isinstance(v, dict)
                                else str(v)[:100]
                                for v in val[:3]
                            ]
                            parts.append(f"  {type_name}: {', '.join(summaries)}")
                    if parts:
                        working_context = "\n\nCurrent focus:\n" + "\n".join(parts)
            except Exception:
                logger.debug(
                    "Failed to load working memory context for perception",
                    exc_info=True,
                    extra={"employee_id": str(self.employee.id)},
                )

        user_prompt = (
            f"Check your environment for changes relevant to your goals.\n\n"
            f"Current goals:\n{goals_context}\n\n"
            f"Recent beliefs:\n{beliefs_context}"
            f"{working_context}\n\n"
            f"Use the available tools to check for new information. "
            f"Focus on what's most relevant to your highest-priority goals. "
            f"Be efficient — don't check everything every time."
        )

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ]

        observations: list[Observation] = []
        sources_checked: set[str] = set()
        max_perception_iterations = self.config.max_perception_iterations

        for iteration in range(max_perception_iterations):
            try:
                response = await self.llm_service.generate_with_tools(
                    messages=messages,
                    tools=tool_schemas,
                    tool_choice="auto",
                    temperature=0.2,
                )
            except Exception:
                logger.exception(
                    "LLM call failed during agentic perception",
                    extra={
                        "employee_id": str(self.employee.id),
                        "iteration": iteration,
                    },
                )
                break

            if not response.tool_calls:
                break

            # Add assistant message to conversation
            assistant_msg = Message(
                role="assistant",
                content=response.content or "",
                tool_calls=response.tool_calls,
            )
            messages.append(assistant_msg)

            # Execute each tool call
            if self.tool_router is None:
                break

            for tc in response.tool_calls:
                source = tc.name.split(".")[0] if "." in tc.name else tc.name
                sources_checked.add(source)

                try:
                    result = await self.tool_router.execute_tool_call(
                        self.employee.id, tc.name, tc.arguments
                    )
                    result_output = result.output if hasattr(result, "output") else result
                    result_error = getattr(result, "error", None)
                    result_success = getattr(result, "success", True)

                    obs_content: dict[str, Any] = {
                        "tool_result": result_output,
                        "arguments": tc.arguments,
                    }
                    if result_error:
                        obs_content["error"] = result_error

                    observations.append(
                        Observation(
                            employee_id=self.employee.id,
                            tenant_id=self.employee.tenant_id,
                            observation_type=tc.name,
                            source=source,
                            content=obs_content,
                            priority=5,
                            requires_action=False,
                        )
                    )

                    result_payload: dict[str, Any] = {
                        "success": result_success,
                        "output": result_output,
                    }
                    if result_error:
                        result_payload["error"] = result_error
                    result_content = json.dumps(result_payload, default=str)
                except Exception as e:
                    logger.exception(
                        "Tool call %s failed during perception",
                        tc.name,
                        extra={"employee_id": str(self.employee.id), "tool_name": tc.name},
                    )
                    result_content = json.dumps({"success": False, "error": str(e)})

                messages.append(Message(role="tool", content=result_content, tool_call_id=tc.id))

        # Classify observations
        opportunities = sum(
            1 for obs in observations if "opportunity" in obs.observation_type.lower()
        )
        problems = sum(
            1
            for obs in observations
            if "problem" in obs.observation_type.lower() or "error" in obs.observation_type.lower()
        )
        risks = sum(
            1 for obs in observations if "risk" in obs.observation_type.lower() or obs.priority >= 9
        )

        logger.info(
            f"Agentic perception: {len(observations)} observations from {len(sources_checked)} sources",
            extra={
                "employee_id": str(self.employee.id),
                "observations": len(observations),
                "sources": list(sources_checked),
            },
        )

        # Store key observations in working memory for short-term context
        if hasattr(self.memory, "working") and observations:
            try:
                await self.memory.working.cleanup_expired()
                await self.memory.working.clear_by_type("observation")
                for obs in observations[:5]:
                    await self.memory.working.add_item(
                        item_type="observation",
                        content={
                            "source": obs.source,
                            "type": obs.observation_type,
                            "summary": str(obs.content)[:500],
                        },
                        importance=obs.priority / 10.0,
                        ttl_seconds=1800,
                    )
            except Exception:
                logger.debug(
                    "Failed to store observations in working memory",
                    exc_info=True,
                    extra={"employee_id": str(self.employee.id)},
                )

        return PerceptionResult(
            observations=observations,
            opportunities_detected=opportunities,
            problems_detected=problems,
            risks_detected=risks,
            perception_duration_ms=0.01,  # Updated by caller
            sources_checked=list(sources_checked),
        )

    def _build_perception_system_prompt(self) -> str:
        """Build system prompt for agentic perception."""
        perception_instructions = (
            "You are the perception system for a digital employee. "
            "Your job is to check the environment for changes relevant to current goals. "
            "Use the available tools to gather information. "
            "Be efficient — focus on the most important sources first."
        )
        if self._identity_prompt:
            return f"{self._identity_prompt}\n\n{perception_instructions}"
        return perception_instructions

    async def _format_goals_for_perception(self) -> str:
        """Format current goals for the perception prompt."""
        try:
            active_goals = await self.goals.get_active_goals()
            if not active_goals:
                return "No active goals."
            lines = []
            for g in active_goals:
                desc = getattr(g, "description", "Unknown")
                priority = getattr(g, "priority", "?")
                lines.append(f"- [{priority}] {desc}")
            return "\n".join(lines)
        except Exception as e:
            logger.warning("Failed to format goals for perception: %s", e)
            return "Unable to load goals."

    async def _format_recent_beliefs_for_perception(self) -> str:
        """Format recent beliefs for context in perception prompt."""
        try:
            beliefs = await self.beliefs.get_all_beliefs(min_confidence=0.5)
            if not beliefs:
                return "No current beliefs."
            lines = []
            for b in beliefs[:10]:
                subject = getattr(b, "subject", "?")
                predicate = getattr(b, "predicate", "?")
                confidence = getattr(b, "confidence", "?")
                lines.append(f"- {subject}.{predicate} (confidence: {confidence})")
            return "\n".join(lines)
        except Exception as e:
            logger.warning("Failed to format beliefs for perception: %s", e)
            return "Unable to load beliefs."
