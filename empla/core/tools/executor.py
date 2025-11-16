"""
empla.core.tools.executor - Tool Execution Engine

Executes tools with retry logic, error handling, and performance tracking.
"""

import asyncio
import logging
from datetime import UTC, datetime
from time import time
from typing import Any

from .base import Tool, ToolImplementation, ToolResult

logger = logging.getLogger(__name__)


class ToolExecutionEngine:
    """
    Executes tools with retry logic and error handling.

    Features:
    - Exponential backoff retry for transient failures
    - Parameter validation against tool schema
    - Execution timing and metrics
    - Structured error logging
    - Graceful degradation

    Design Decision (ADR-009): Custom implementation rather than framework
    because our tool patterns are simple (direct API calls) and we already
    have complex orchestration (IntentionStack with plan generation).

    Example:
        >>> engine = ToolExecutionEngine()
        >>> tool = Tool(name="send_email", ...)
        >>> implementation = SendEmailTool()
        >>> result = await engine.execute(
        ...     tool=tool,
        ...     implementation=implementation,
        ...     params={"to": "user@example.com", "subject": "Hello"}
        ... )
        >>> if result.success:
        ...     print(f"Email sent: {result.output}")
        >>> else:
        ...     print(f"Failed: {result.error}")
    """

    def __init__(
        self,
        max_retries: int = 3,
        initial_backoff_ms: int = 100,
        max_backoff_ms: int = 5000,
        backoff_multiplier: float = 2.0,
    ):
        """
        Initialize tool execution engine.

        Args:
            max_retries: Maximum retry attempts for transient failures
            initial_backoff_ms: Initial backoff delay in milliseconds
            max_backoff_ms: Maximum backoff delay in milliseconds
            backoff_multiplier: Multiplier for exponential backoff
        """
        self.max_retries = max_retries
        self.initial_backoff_ms = initial_backoff_ms
        self.max_backoff_ms = max_backoff_ms
        self.backoff_multiplier = backoff_multiplier

    async def execute(
        self,
        tool: Tool,
        implementation: ToolImplementation,
        params: dict[str, Any],
    ) -> ToolResult:
        """
        Execute tool with retry logic and error handling.

        This method NEVER raises exceptions - all errors are captured in ToolResult.
        This is critical for autonomous operation: employees must handle failures
        gracefully and decide whether to retry, replan, or escalate.

        Args:
            tool: Tool definition with schema and metadata
            implementation: Concrete tool implementation
            params: Parameters for tool execution

        Returns:
            ToolResult with success/failure, output/error, timing, retries

        Example:
            >>> result = await engine.execute(tool, impl, {"to": "user@example.com"})
            >>> if not result.success:
            ...     # Employee can decide: retry? replan? escalate?
            ...     if "rate_limit" in result.error:
            ...         await asyncio.sleep(60)  # Back off
            ...     elif "auth" in result.error:
            ...         await reauthorize()  # Fix credentials
            ...     else:
            ...         await create_fallback_intention()  # Replan
        """
        start_time = time()
        retries = 0

        # Validate parameters (basic validation - detailed validation in implementation)
        validation_error = self._validate_params(tool, params)
        if validation_error:
            logger.warning(
                f"Parameter validation failed for {tool.name}: {validation_error}",
                extra={"tool_id": str(tool.tool_id), "tool_name": tool.name},
            )
            return ToolResult(
                tool_id=tool.tool_id,
                success=False,
                error=f"Parameter validation failed: {validation_error}",
                duration_ms=(time() - start_time) * 1000,
                retries=0,
            )

        # Execute with retry logic
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                # Log attempt
                if attempt > 0:
                    logger.info(
                        f"Retrying {tool.name} (attempt {attempt + 1}/{self.max_retries + 1})",
                        extra={"tool_id": str(tool.tool_id), "attempt": attempt + 1},
                    )

                # Execute tool implementation
                output = await implementation._execute(params)

                # Success!
                duration_ms = (time() - start_time) * 1000
                logger.info(
                    f"Tool {tool.name} executed successfully",
                    extra={
                        "tool_id": str(tool.tool_id),
                        "duration_ms": duration_ms,
                        "retries": attempt,
                    },
                )

                return ToolResult(
                    tool_id=tool.tool_id,
                    success=True,
                    output=output,
                    duration_ms=duration_ms,
                    retries=attempt,
                )

            except Exception as e:
                last_error = e
                retries = attempt

                # Log error
                logger.warning(
                    f"Tool {tool.name} failed: {e}",
                    exc_info=True,
                    extra={
                        "tool_id": str(tool.tool_id),
                        "attempt": attempt + 1,
                        "error": str(e),
                    },
                )

                # Check if we should retry
                if not self._should_retry(e) or attempt >= self.max_retries:
                    break

                # Exponential backoff with jitter
                backoff_ms = min(
                    self.initial_backoff_ms * (self.backoff_multiplier**attempt),
                    self.max_backoff_ms,
                )
                # Add jitter (±25%) to avoid thundering herd
                import random

                jitter = backoff_ms * 0.25 * (2 * random.random() - 1)
                backoff_ms += jitter

                await asyncio.sleep(backoff_ms / 1000)

        # All retries exhausted
        duration_ms = (time() - start_time) * 1000
        error_msg = str(last_error) if last_error else "Unknown error"

        logger.error(
            f"Tool {tool.name} failed after {retries + 1} attempts",
            extra={
                "tool_id": str(tool.tool_id),
                "duration_ms": duration_ms,
                "retries": retries,
                "error": error_msg,
            },
        )

        return ToolResult(
            tool_id=tool.tool_id,
            success=False,
            error=error_msg,
            duration_ms=duration_ms,
            retries=retries,
        )

    def _validate_params(self, tool: Tool, params: dict[str, Any]) -> str | None:
        """
        Validate parameters against tool schema.

        This is basic validation - detailed validation happens in tool implementation.
        We check:
        - Required parameters are present
        - No unexpected parameters
        - Types match (basic type checking)

        Args:
            tool: Tool with parameters_schema
            params: Parameters to validate

        Returns:
            Error message if validation fails, None if valid

        Example:
            >>> error = self._validate_params(
            ...     Tool(parameters_schema={"to": {"type": "string", "required": True}}),
            ...     {"to": "user@example.com"}
            ... )
            >>> assert error is None  # Valid
        """
        schema = tool.parameters_schema

        # Check for required parameters
        for param_name, param_spec in schema.items():
            if isinstance(param_spec, dict) and param_spec.get("required", False):
                if param_name not in params:
                    return f"Missing required parameter: {param_name}"

        # Check for unexpected parameters
        for param_name in params.keys():
            if param_name not in schema:
                return f"Unexpected parameter: {param_name}"

        # Basic type checking (detailed validation in implementation)
        for param_name, param_value in params.items():
            if param_name in schema:
                param_spec = schema[param_name]
                if isinstance(param_spec, dict) and "type" in param_spec:
                    expected_type = param_spec["type"]
                    # Basic type validation (string, number, boolean, array, object)
                    if not self._check_type(param_value, expected_type):
                        return f"Parameter {param_name} has wrong type (expected {expected_type})"

        return None

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """
        Check if value matches expected JSON schema type.

        Args:
            value: Value to check
            expected_type: JSON schema type (string, number, boolean, array, object, null)

        Returns:
            True if type matches, False otherwise
        """
        type_mapping = {
            "string": str,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }

        if expected_type not in type_mapping:
            # Unknown type - allow it (detailed validation in implementation)
            return True

        expected_python_type = type_mapping[expected_type]
        return isinstance(value, expected_python_type)

    def _should_retry(self, error: Exception) -> bool:
        """
        Determine if error is retryable.

        Transient errors (network, rate limit, timeout) should be retried.
        Permanent errors (auth, validation, not found) should not.

        Args:
            error: Exception that occurred

        Returns:
            True if should retry, False otherwise

        Design Decision: Conservative approach - only retry obvious transient errors.
        When in doubt, don't retry (avoid wasting time on permanent failures).

        Example:
            >>> self._should_retry(TimeoutError())  # True
            >>> self._should_retry(ValueError("Invalid email"))  # False
        """
        error_str = str(error).lower()

        # Transient errors - should retry
        transient_indicators = [
            "timeout",
            "rate limit",
            "too many requests",
            "connection",
            "network",
            "temporary",
            "503",  # Service Unavailable
            "429",  # Too Many Requests
        ]

        for indicator in transient_indicators:
            if indicator in error_str:
                return True

        # Permanent errors - should NOT retry
        permanent_indicators = [
            "auth",
            "unauthorized",
            "forbidden",
            "not found",
            "invalid",
            "validation",
            "400",  # Bad Request
            "401",  # Unauthorized
            "403",  # Forbidden
            "404",  # Not Found
        ]

        for indicator in permanent_indicators:
            if indicator in error_str:
                return False

        # Unknown error type - don't retry (conservative approach)
        # Let employee decide whether to retry at higher level
        return False
