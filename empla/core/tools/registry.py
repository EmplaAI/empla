"""
empla.core.tools.registry - Tool Registry

Manages available tools and capabilities for employees.
"""

import logging
from typing import Any
from uuid import UUID

from .base import Tool, ToolCapability, ToolImplementation

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry of available tools and their implementations.

    Features:
    - Tool registration and lookup
    - Capability-based filtering
    - Tool discovery by tags
    - Implementation management

    Design: Simple dict-based registry for fast lookup. No database persistence yet
    (tools are defined in code). In future phases, can extend to support:
    - Dynamic tool loading from plugins
    - Database-backed tool catalog
    - MCP-based tool discovery

    Example:
        >>> registry = ToolRegistry()
        >>> registry.register_tool(email_tool, SendEmailTool())
        >>> registry.register_capability(email_capability)
        >>> tools = registry.list_tools(capability="email")
        >>> tool = registry.get_tool_by_name("send_email")
    """

    def __init__(self) -> None:
        """Initialize empty tool registry."""
        self._tools: dict[UUID, Tool] = {}
        self._implementations: dict[UUID, ToolImplementation] = {}
        self._capabilities: dict[str, ToolCapability] = {}
        self._name_to_id: dict[str, UUID] = {}

    def register_tool(
        self,
        tool: Tool,
        implementation: ToolImplementation,
    ) -> None:
        """
        Register a tool with its implementation.

        Args:
            tool: Tool definition with schema and metadata
            implementation: Concrete implementation of the tool

        Raises:
            ValueError: If tool name already registered

        Example:
            >>> tool = Tool(name="send_email", ...)
            >>> impl = SendEmailTool()
            >>> registry.register_tool(tool, impl)
        """
        # Check for duplicate names
        if tool.name in self._name_to_id:
            existing_id = self._name_to_id[tool.name]
            if existing_id != tool.tool_id:
                raise ValueError(
                    f"Tool with name '{tool.name}' already registered with different ID"
                )

        # Store tool and implementation
        self._tools[tool.tool_id] = tool
        self._implementations[tool.tool_id] = implementation
        self._name_to_id[tool.name] = tool.tool_id

        logger.info(
            f"Registered tool: {tool.name}",
            extra={
                "tool_id": str(tool.tool_id),
                "capabilities": tool.required_capabilities,
                "category": tool.category,
            },
        )

    def register_capability(self, capability: ToolCapability) -> None:
        """
        Register a capability.

        Capabilities group related tools and define requirements.

        Args:
            capability: Capability definition

        Example:
            >>> capability = ToolCapability(
            ...     name="email",
            ...     description="Email operations",
            ...     tools=["send_email", "read_email"]
            ... )
            >>> registry.register_capability(capability)
        """
        self._capabilities[capability.name] = capability

        logger.info(
            f"Registered capability: {capability.name}",
            extra={
                "capability_id": str(capability.capability_id),
                "tools": capability.tools,
                "required_credentials": capability.required_credentials,
            },
        )

    def get_tool(self, tool_id: UUID) -> Tool | None:
        """
        Get tool by ID.

        Args:
            tool_id: Tool UUID

        Returns:
            Tool if found, None otherwise
        """
        return self._tools.get(tool_id)

    def get_tool_by_name(self, name: str) -> Tool | None:
        """
        Get tool by name.

        Args:
            name: Tool name (e.g., "send_email")

        Returns:
            Tool if found, None otherwise

        Example:
            >>> tool = registry.get_tool_by_name("send_email")
            >>> if tool:
            ...     print(f"Found: {tool.description}")
        """
        tool_id = self._name_to_id.get(name)
        if tool_id:
            return self._tools.get(tool_id)
        return None

    def get_implementation(self, tool_id: UUID) -> ToolImplementation | None:
        """
        Get tool implementation by ID.

        Args:
            tool_id: Tool UUID

        Returns:
            ToolImplementation if found, None otherwise
        """
        return self._implementations.get(tool_id)

    def get_capability(self, name: str) -> ToolCapability | None:
        """
        Get capability by name.

        Args:
            name: Capability name (e.g., "email")

        Returns:
            ToolCapability if found, None otherwise
        """
        return self._capabilities.get(name)

    def list_tools(
        self,
        capability: str | None = None,
        category: str | None = None,
        tag: str | None = None,
    ) -> list[Tool]:
        """
        List available tools with optional filtering.

        Args:
            capability: Filter by required capability
            category: Filter by category
            tag: Filter by tag

        Returns:
            List of matching tools

        Example:
            >>> # Get all email tools
            >>> email_tools = registry.list_tools(capability="email")
            >>> # Get all communication tools
            >>> comm_tools = registry.list_tools(category="communication")
            >>> # Get tools by tag
            >>> tagged = registry.list_tools(tag="priority")
        """
        tools = list(self._tools.values())

        # Filter by capability
        if capability:
            tools = [t for t in tools if capability in t.required_capabilities]

        # Filter by category
        if category:
            tools = [t for t in tools if t.category == category]

        # Filter by tag
        if tag:
            tools = [t for t in tools if tag in t.tags]

        return tools

    def list_capabilities(self) -> list[ToolCapability]:
        """
        List all registered capabilities.

        Returns:
            List of all capabilities
        """
        return list(self._capabilities.values())

    def has_capability(self, capability_name: str, credentials: dict[str, Any]) -> bool:
        """
        Check if given credentials satisfy a capability's requirements.

        Args:
            capability_name: Capability to check
            credentials: Available credentials (dict of credential_name -> credential_value)

        Returns:
            True if all required credentials are present, False otherwise

        Example:
            >>> credentials = {"microsoft_graph_token": "eyJ0..."}
            >>> can_email = registry.has_capability("email", credentials)
            >>> if can_email:
            ...     tools = registry.list_tools(capability="email")
        """
        capability = self._capabilities.get(capability_name)
        if not capability:
            return False

        # Check all required credentials are present
        for required_cred in capability.required_credentials:
            if required_cred not in credentials:
                return False

        return True

    def get_tools_for_employee(
        self, capabilities: list[str], credentials: dict[str, Any]
    ) -> list[Tool]:
        """
        Get tools available to an employee based on their capabilities and credentials.

        Args:
            capabilities: Employee's configured capabilities
            credentials: Employee's available credentials

        Returns:
            List of tools employee can use

        Example:
            >>> employee_capabilities = ["email", "calendar"]
            >>> employee_credentials = {
            ...     "microsoft_graph_token": "eyJ0...",
            ...     "google_oauth_token": "ya29..."
            ... }
            >>> available_tools = registry.get_tools_for_employee(
            ...     employee_capabilities,
            ...     employee_credentials
            ... )
            >>> for tool in available_tools:
            ...     print(f"- {tool.name}: {tool.description}")
        """
        available_tools = []

        for tool in self._tools.values():
            # Check if employee has all required capabilities
            if all(cap in capabilities for cap in tool.required_capabilities):
                # Check if employee has required credentials for those capabilities
                has_credentials = True
                for cap_name in tool.required_capabilities:
                    if not self.has_capability(cap_name, credentials):
                        has_credentials = False
                        break

                if has_credentials:
                    available_tools.append(tool)

        return available_tools

    def clear(self) -> None:
        """
        Clear all registered tools and capabilities.

        Useful for testing or reloading tool catalog.
        """
        self._tools.clear()
        self._implementations.clear()
        self._capabilities.clear()
        self._name_to_id.clear()

        logger.info("Tool registry cleared")

    def __len__(self) -> int:
        """Return number of registered tools."""
        return len(self._tools)

    def __contains__(self, tool_name: str) -> bool:
        """Check if tool with given name is registered."""
        return tool_name in self._name_to_id
