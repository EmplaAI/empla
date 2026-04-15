"""
empla.core.loop.intention_execution - Intention Execution Mixin

Provides intention execution via agentic LLM-driven tool calling.
The mixin implements the execute_intentions phase of the proactive loop,
where the highest-priority intention is selected and executed by having
an LLM drive tool calls against available integrations.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from empla.core.loop.models import IntentionResult

logger = logging.getLogger(__name__)


def _compute_scheduled_action_ttl(scheduled_for_iso: str) -> int:
    """TTL in seconds so a row persists 24h past its fire time.

    Working memory's ``get_active_items`` filters on ``expires_at > now``,
    so a too-short TTL makes scheduled actions vanish before firing.
    """
    try:
        scheduled_for = datetime.fromisoformat(scheduled_for_iso)
    except (ValueError, TypeError):
        return 3600  # fall back to WorkingMemory default
    delta = scheduled_for - datetime.now(UTC)
    return max(3600, int(delta.total_seconds()) + 86400)


class IntentionExecutionMixin:
    """Mixin providing intention execution via agentic tool calling.

    Expects the host class to provide:
        self.employee       - Employee instance (with .id)
        self.intentions     - IntentionSystem
        self.memory         - MemorySystem (with .working)
        self.llm_service    - LLMService (optional)
        self.tool_router    - ToolRouter (optional)
        self.config         - LoopConfig
        self._identity_prompt - str | None
    """

    async def execute_intentions(self) -> IntentionResult | None:
        """
        Execute highest priority intention from intention stack.

        Executes intention plan steps via the capability registry.
        Each step in the intention's plan is converted to an Action and
        executed by the appropriate capability.

        Returns:
            IntentionResult if work was done, None if no work to do
        """
        # Get next intention
        intention = await self.intentions.get_next_intention()

        if not intention:
            logger.debug("No intentions to execute", extra={"employee_id": str(self.employee.id)})
            return None

        # Check dependencies
        if not await self.intentions.dependencies_satisfied(intention):
            logger.debug(
                "Intention waiting on dependencies",
                extra={
                    "employee_id": str(self.employee.id),
                    "intention_id": str(intention.id),
                },
            )
            return None

        # Mark as in progress
        await self.intentions.start_intention(intention.id)

        # Store current intention in working memory as focus
        if hasattr(self.memory, "working"):
            try:
                await self.memory.working.clear_by_type("task")
                await self.memory.working.add_item(
                    item_type="task",
                    content={
                        "intention": intention.description,
                        "goal_id": str(intention.goal_id) if intention.goal_id else None,
                        "type": intention.intention_type,
                    },
                    importance=intention.priority / 10.0,
                    ttl_seconds=3600,
                )
            except Exception:
                logger.debug(
                    "Failed to store intention in working memory",
                    exc_info=True,
                    extra={"employee_id": str(self.employee.id)},
                )

        logger.info(
            f"Executing intention: {intention.description}",
            extra={
                "employee_id": str(self.employee.id),
                "intention_id": str(intention.id),
                "intention_type": intention.intention_type,
                "priority": intention.priority,
            },
        )

        start_time = time.time()

        try:
            # Execute the intention's plan via capabilities
            execution_result = await self._execute_intention_plan(intention)

            duration_ms = max(0.01, (time.time() - start_time) * 1000)

            # Enrich outcome with goal context for procedural memory matching
            _goal_id = getattr(intention, "goal_id", None)
            execution_result["goal_id"] = str(_goal_id) if _goal_id else None
            execution_result["intention_description"] = getattr(intention, "description", "")

            result = IntentionResult(
                intention_id=intention.id,
                success=execution_result["success"],
                outcome=execution_result,
                duration_ms=duration_ms,
            )

            if result.success:
                await self.intentions.complete_intention(intention.id, outcome=result.outcome)
                logger.info(
                    f"Intention completed: {intention.description}",
                    extra={
                        "employee_id": str(self.employee.id),
                        "intention_id": str(intention.id),
                        "success": True,
                        "duration_ms": duration_ms,
                        "steps_executed": execution_result.get("steps_completed", 0),
                    },
                )
            else:
                error_msg = execution_result.get("error", "Unknown error")
                await self.intentions.fail_intention(intention.id, error=error_msg)
                logger.warning(
                    f"Intention failed: {intention.description}",
                    extra={
                        "employee_id": str(self.employee.id),
                        "intention_id": str(intention.id),
                        "error": error_msg,
                        "duration_ms": duration_ms,
                    },
                )

            return result

        except Exception as e:
            logger.error(
                f"Intention execution error: {intention.description}",
                exc_info=True,
                extra={
                    "employee_id": str(self.employee.id),
                    "intention_id": str(intention.id),
                    "error": str(e),
                },
            )

            await self.intentions.fail_intention(intention.id, error=str(e))

            return IntentionResult(
                intention_id=intention.id,
                success=False,
                outcome={"error": str(e)},
                duration_ms=max(0.01, (time.time() - start_time) * 1000),
            )

    async def _execute_intention_plan(self, intention: Any) -> dict[str, Any]:
        """
        Execute an intention's plan via agentic LLM-driven tool calling.

        Requires both an LLM service and tools to be available. Returns a
        clear error if either is missing.

        Args:
            intention: The intention to execute

        Returns:
            Execution result with success status and outputs
        """
        if not self.llm_service or not self.tool_router:
            return {
                "success": False,
                "error": "Agentic execution requires LLM service and tool router",
                "agentic": True,
            }

        try:
            tool_schemas = self.tool_router.get_all_tool_schemas(self.employee.id)
        except Exception:
            logger.error(
                "Failed to collect tool schemas",
                exc_info=True,
                extra={
                    "employee_id": str(self.employee.id),
                    "intention_id": str(intention.id),
                },
            )
            return {
                "success": False,
                "error": "Failed to collect tool schemas",
                "agentic": True,
            }

        if not tool_schemas:
            return {
                "success": False,
                "error": "No tools available for execution",
                "agentic": True,
            }

        logger.info(
            "Using agentic execution with %d tool schemas",
            len(tool_schemas),
            extra={
                "employee_id": str(self.employee.id),
                "intention_id": str(intention.id),
                "tool_count": len(tool_schemas),
            },
        )
        return await self._execute_intention_with_tools(intention, tool_schemas)

    async def _execute_intention_with_tools(
        self, intention: Any, tool_schemas: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Execute intention using LLM function calling.

        The LLM receives the intention description and available tools,
        then drives execution by making tool calls. It can adapt based
        on results, chain multiple calls, and decide when it's done.

        Args:
            intention: The intention to execute
            tool_schemas: Tool schemas from capabilities

        Returns:
            Execution result dict
        """
        from empla.llm.models import Message

        messages = [
            Message(role="system", content=self._build_execution_system_prompt()),
            Message(role="user", content=self._build_intention_prompt(intention)),
        ]

        max_iterations = 10
        tool_calls_made: list[dict[str, Any]] = []

        for iteration in range(max_iterations):
            try:
                response = await self.llm_service.generate_with_tools(
                    messages=messages,
                    tools=tool_schemas,
                    tool_choice="auto",
                    temperature=0.2,
                )
            except Exception as e:
                logger.error(
                    f"LLM generate_with_tools failed during agentic execution: {e}",
                    extra={
                        "employee_id": str(self.employee.id),
                        "intention_id": str(intention.id),
                        "iteration": iteration,
                    },
                )
                return {
                    "success": False,
                    "error": f"LLM call failed: {e}",
                    "tool_calls_made": len(tool_calls_made),
                    "tools_used": [tc["tool"] for tc in tool_calls_made],
                    "tool_results": tool_calls_made,
                    "agentic": True,
                }

            # If no tool calls, LLM is done
            if not response.tool_calls:
                if not response.content or not response.content.strip():
                    return {
                        "success": False,
                        "error": "Empty assistant response",
                        "tool_calls_made": len(tool_calls_made),
                        "tools_used": [tc["tool"] for tc in tool_calls_made],
                        "tool_results": tool_calls_made,
                        "agentic": True,
                    }
                return {
                    "success": True,
                    "message": response.content,
                    "tool_calls_made": len(tool_calls_made),
                    "tools_used": [tc["tool"] for tc in tool_calls_made],
                    "tool_results": tool_calls_made,
                    "agentic": True,
                }

            # Add assistant message with tool calls to conversation
            assistant_msg = Message(
                role="assistant",
                content=response.content or "",
                tool_calls=response.tool_calls,
            )
            messages.append(assistant_msg)

            # Execute each tool call via tool_router
            if self.tool_router is None:
                logger.error(
                    "No tool executor available — cannot execute tool calls",
                    extra={"employee_id": str(self.employee.id)},
                )
                return {
                    "success": False,
                    "error": "No tool executor configured",
                    "tool_calls_made": 0,
                    "tools_used": [],
                    "tool_results": [],
                    "agentic": True,
                }
            for tool_call in response.tool_calls:
                try:
                    result = await self.tool_router.execute_tool_call(
                        self.employee.id,
                        tool_call.name,
                        tool_call.arguments,
                        employee_role=getattr(self.employee, "role", None),
                        tenant_id=getattr(self.employee, "tenant_id", None),
                    )
                except Exception as e:
                    logger.error(
                        f"Tool call {tool_call.name} raised exception: {e}",
                        extra={
                            "employee_id": str(self.employee.id),
                            "tool_name": tool_call.name,
                        },
                    )
                    result_content = json.dumps(
                        {"success": False, "error": f"{type(e).__name__}: {e}"}
                    )
                    tool_calls_made.append({"tool": tool_call.name, "success": False})
                    messages.append(
                        Message(role="tool", content=result_content, tool_call_id=tool_call.id)
                    )
                    continue

                tool_calls_made.append({"tool": tool_call.name, "success": result.success})

                # Handle scheduled action tool results — persist to working memory
                await self._handle_scheduling_result(result)

                result_content = json.dumps(
                    {
                        "success": result.success,
                        "output": result.output,
                        "error": result.error,
                    },
                    default=str,
                )
                messages.append(
                    Message(role="tool", content=result_content, tool_call_id=tool_call.id)
                )

                logger.debug(
                    f"Tool call {tool_call.name}: {'success' if result.success else 'failed'}",
                    extra={
                        "employee_id": str(self.employee.id),
                        "tool_name": tool_call.name,
                        "success": result.success,
                        "iteration": iteration,
                    },
                )

        # Max iterations reached — incomplete execution
        logger.warning(
            "Agentic execution reached max iterations without completing",
            extra={
                "employee_id": str(self.employee.id),
                "intention_id": str(intention.id),
                "max_iterations": max_iterations,
                "tool_calls_made": len(tool_calls_made),
            },
        )
        return {
            "success": False,
            "error": f"Agentic execution exhausted iteration budget (max_iterations={max_iterations})",
            "tool_calls_made": len(tool_calls_made),
            "tools_used": [tc["tool"] for tc in tool_calls_made],
            "agentic": True,
        }

    def _build_execution_system_prompt(self) -> str:
        """Build system prompt for agentic execution."""
        execution_instructions = (
            "Use the available tools to accomplish the intention. "
            "Call tools as needed, adapt based on results, and stop when done. "
            "Be efficient — don't make unnecessary tool calls."
        )
        if self._identity_prompt:
            return f"{self._identity_prompt}\n\n{execution_instructions}"
        return f"You are a digital employee. {execution_instructions}"

    def _build_intention_prompt(self, intention: Any) -> str:
        """Build user prompt from intention context and plan."""
        parts = [f"Execute this intention: {intention.description}"]
        context = getattr(intention, "context", None)
        if context and isinstance(context, dict):
            if "reasoning" in context:
                parts.append(f"Reasoning: {context['reasoning']}")
            if "success_criteria" in context:
                parts.append(f"Success criteria: {context['success_criteria']}")

        # Include generated plan steps if available
        plan = getattr(intention, "plan", None)
        if plan and isinstance(plan, dict):
            steps = plan.get("steps", [])
            if steps:
                step_lines = []
                for i, step in enumerate(steps):
                    desc = step.get("description", step.get("action", ""))
                    if desc:
                        step_lines.append(f"{i + 1}. {desc}")
                if step_lines:
                    parts.append(
                        "Planned steps:\n"
                        + "\n".join(step_lines)
                        + "\n\nFollow this plan, adapting as needed based on tool results."
                    )

        return "\n".join(parts)

    async def _handle_scheduling_result(self, result: Any) -> None:
        """Persist scheduled action tool results to working memory.

        When the LLM calls schedule_action/list/cancel, the tool returns
        a signal dict. This method intercepts the result and performs
        the actual working memory operations.
        """
        if not result.success or not isinstance(result.output, dict):
            return

        output = result.output

        # schedule_action → store in working memory
        if output.get("_store_as_scheduled_action"):
            if not hasattr(self.memory, "working"):
                return
            try:
                content = {
                    "subtype": "scheduled_action",
                    "action_id": output.get("action_id"),
                    "description": output.get("description", ""),
                    "scheduled_for": output.get("scheduled_for", ""),
                    "recurring": output.get("recurring", False),
                    "interval_hours": output.get("interval_hours"),
                    "context": output.get("context", {}),
                    "created_at": output.get("created_at", ""),
                    # PR #82: tag self-scheduled actions so the API can
                    # distinguish from user_requested ones.
                    "source": "employee",
                }
                # Working memory's default TTL is 1 hour. Scheduled actions
                # may fire arbitrarily far in the future, so compute a TTL
                # that extends 24h past scheduled_for; otherwise the row
                # disappears from get_active_items before ever firing.
                ttl_seconds = _compute_scheduled_action_ttl(content["scheduled_for"])
                await self.memory.working.add_item(
                    item_type="task",
                    content=content,
                    importance=0.7,
                    ttl_seconds=ttl_seconds,
                )
                logger.info(
                    "Stored scheduled action: %s at %s",
                    content["description"][:50],
                    content["scheduled_for"],
                    extra={"employee_id": str(self.employee.id)},
                )
            except Exception:
                logger.warning(
                    "Failed to store scheduled action in working memory",
                    exc_info=True,
                    extra={"employee_id": str(self.employee.id)},
                )

        # list_scheduled_actions → populate with actual data
        elif output.get("_list_scheduled_actions"):
            if not hasattr(self.memory, "working"):
                result.output = {"actions": [], "count": 0}
                return
            try:
                items = await self.memory.working.get_active_items()
                actions = []
                for item in items:
                    c = getattr(item, "content", {}) or {}
                    if c.get("subtype") == "scheduled_action":
                        actions.append(
                            {
                                "action_id": c.get("action_id", str(item.id)),
                                "description": c.get("description", ""),
                                "scheduled_for": c.get("scheduled_for", ""),
                                "recurring": c.get("recurring", False),
                            }
                        )
                result.output = {"actions": actions, "count": len(actions)}
            except Exception:
                result.output = {"actions": [], "count": 0, "error": "Failed to list"}

        # cancel_scheduled_action → remove from working memory
        elif output.get("_cancel_scheduled_action"):
            action_id = output.get("action_id")
            if not action_id or not hasattr(self.memory, "working"):
                return
            try:
                items = await self.memory.working.get_active_items()
                for item in items:
                    c = getattr(item, "content", {}) or {}
                    if c.get("subtype") == "scheduled_action" and c.get("action_id") == action_id:
                        await self.memory.working.remove_item(item.id)
                        logger.info(
                            "Cancelled scheduled action %s (item %s)",
                            action_id,
                            item.id,
                            extra={"employee_id": str(self.employee.id)},
                        )
                        result.output = {"cancelled": True, "action_id": action_id}
                        return
                logger.warning(
                    "Scheduled action %s not found for cancellation",
                    action_id,
                    extra={"employee_id": str(self.employee.id)},
                )
                result.output = {"cancelled": False, "error": f"Action {action_id} not found"}
            except Exception:
                logger.warning(
                    "Failed to cancel scheduled action %s",
                    action_id,
                    exc_info=True,
                    extra={"employee_id": str(self.employee.id)},
                )
                result.output = {"cancelled": False, "error": "Failed to cancel"}
