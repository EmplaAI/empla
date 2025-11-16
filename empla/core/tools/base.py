"""
empla.core.tools.base - Base Tool Definitions

Core interfaces and data models for tool execution system.
"""

from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Tool(BaseModel):
    """
    Tool definition for autonomous execution.

    Tools represent capabilities that employees can use to accomplish their goals.
    Each tool has a defined interface (parameters schema) and required capabilities.

    Example:
        >>> email_tool = Tool(
        ...     name="send_email",
        ...     description="Send an email via Microsoft Graph API",
        ...     parameters_schema={
        ...         "to": {"type": "string", "description": "Recipient email"},
        ...         "subject": {"type": "string", "description": "Email subject"},
        ...         "body": {"type": "string", "description": "Email body"}
        ...     },
        ...     required_capabilities=["email"]
        ... )
    """

    # Identity
    tool_id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Tool name (e.g., 'send_email')")
    description: str = Field(..., description="What this tool does")

    # Interface
    parameters_schema: dict[str, Any] = Field(
        ..., description="JSON schema for tool parameters"
    )

    # Requirements
    required_capabilities: list[str] = Field(
        default_factory=list,
        description="Capabilities needed to use this tool (e.g., ['email', 'microsoft_graph'])",
    )

    # Metadata
    category: str | None = Field(
        default=None, description="Tool category (e.g., 'communication', 'research')"
    )
    tags: list[str] = Field(default_factory=list, description="Tags for discovery")

    class Config:
        json_schema_extra = {
            "example": {
                "tool_id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "send_email",
                "description": "Send an email via Microsoft Graph API",
                "parameters_schema": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required_capabilities": ["email", "microsoft_graph"],
                "category": "communication",
                "tags": ["email", "communication"],
            }
        }


class ToolResult(BaseModel):
    """
    Result of tool execution.

    Captures outcome, timing, and any errors that occurred during execution.

    Example:
        >>> result = ToolResult(
        ...     tool_id=tool.tool_id,
        ...     success=True,
        ...     output={"message_id": "AAMkAD..."},
        ...     duration_ms=1250.5,
        ...     retries=0
        ... )
    """

    # Identity
    tool_id: UUID = Field(..., description="ID of tool that was executed")

    # Outcome
    success: bool = Field(..., description="Whether execution succeeded")
    output: Any | None = Field(default=None, description="Tool output if successful")
    error: str | None = Field(default=None, description="Error message if failed")

    # Performance
    duration_ms: float = Field(..., ge=0, description="Execution duration in milliseconds")
    retries: int = Field(default=0, ge=0, description="Number of retry attempts")

    # Context
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional execution metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "tool_id": "550e8400-e29b-41d4-a716-446655440000",
                "success": True,
                "output": {"message_id": "AAMkADEwM..."},
                "duration_ms": 1250.5,
                "retries": 0,
                "metadata": {"api_version": "v1.0"},
            }
        }


class ToolExecutor(Protocol):
    """
    Protocol for tool execution.

    Implementations must provide async execution with error handling and retry logic.
    This is a Protocol (structural subtyping) to allow multiple implementations:
    - ToolExecutionEngine (default implementation with retry logic)
    - MockToolExecutor (for testing)
    - Future framework adapters (AgnoToolExecutor, LangGraphToolExecutor, etc.)

    Example:
        >>> class MyExecutor:
        ...     async def execute(self, tool: Tool, params: dict[str, Any]) -> ToolResult:
        ...         # Implementation here
        ...         pass
        >>> executor: ToolExecutor = MyExecutor()  # Type checks!
    """

    async def execute(self, tool: Tool, params: dict[str, Any]) -> ToolResult:
        """
        Execute a tool with given parameters.

        Args:
            tool: Tool to execute
            params: Parameters matching tool's parameters_schema

        Returns:
            ToolResult with outcome, duration, and any errors

        Raises:
            Should NOT raise - all errors captured in ToolResult.error
        """
        ...


class ToolImplementation(Protocol):
    """
    Protocol for concrete tool implementations.

    Each capability (email, calendar, research) implements this protocol.
    The ToolExecutionEngine calls _execute() to run the actual tool logic.

    Example:
        >>> class SendEmailTool:
        ...     async def _execute(self, params: dict[str, Any]) -> Any:
        ...         # Send email via Microsoft Graph API
        ...         return {"message_id": "AAMkAD..."}
    """

    async def _execute(self, params: dict[str, Any]) -> Any:
        """
        Execute the tool's core logic.

        Args:
            params: Validated parameters for this tool

        Returns:
            Tool output (will be placed in ToolResult.output)

        Raises:
            Exception if execution fails (will be caught and placed in ToolResult.error)
        """
        ...


class ToolCapability(BaseModel):
    """
    Capability definition for tool discovery.

    Capabilities group related tools (e.g., "email" capability has send/read/reply tools).
    Employees have capabilities based on their configuration and credentials.

    Example:
        >>> email_capability = ToolCapability(
        ...     name="email",
        ...     description="Email operations (send, read, reply)",
        ...     required_credentials=["microsoft_graph_token"],
        ...     tools=["send_email", "read_email", "reply_to_email"]
        ... )
    """

    # Identity
    capability_id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Capability name (e.g., 'email')")
    description: str = Field(..., description="What this capability enables")

    # Requirements
    required_credentials: list[str] = Field(
        default_factory=list,
        description="Credentials needed for this capability",
    )

    # Tools
    tools: list[str] = Field(
        default_factory=list, description="Tool names in this capability"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "capability_id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "email",
                "description": "Email operations (send, read, reply)",
                "required_credentials": ["microsoft_graph_token"],
                "tools": ["send_email", "read_email", "reply_to_email"],
            }
        }
