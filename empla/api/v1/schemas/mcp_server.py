"""
empla.api.v1.schemas.mcp_server - MCP Server API Schemas

Request/response schemas for MCP server management endpoints.
"""

import ipaddress
import re
from datetime import datetime
from typing import Any, Literal, Self
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MCPTransport = Literal["http", "stdio"]
MCPAuthType = Literal["none", "api_key", "bearer_token", "oauth"]
MCPServerStatusValue = Literal["active", "disabled", "revoked"]

# Slug pattern: lowercase letters, numbers, hyphens, underscores
_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{0,48}[a-z0-9]$")

# Hostnames that must never be used as MCP server targets
_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal"}


def _validate_url_safety(url: str) -> str:
    """Reject URLs targeting private/internal network addresses (SSRF protection)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must have a valid hostname")
    # Normalize: lowercase and strip trailing dot to prevent bypass (e.g. "localhost.")
    hostname_norm = hostname.lower().rstrip(".")
    try:
        ip = ipaddress.ip_address(hostname_norm)
    except ValueError:
        # Not an IP literal — treat as DNS name and check against blocklist
        if hostname_norm in _BLOCKED_HOSTNAMES:
            raise ValueError("Cannot connect to reserved hostnames") from None
    else:
        # Valid IP — check for private/internal ranges
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError("Cannot connect to private/internal network addresses")
    return url


def _validate_url_for_transport(url: str | None, transport: str | None) -> str | None:
    """Validate that URL is provided for HTTP transport and is safe."""
    if transport == "http" and not url:
        raise ValueError("URL is required for HTTP transport")
    if url:
        _validate_url_safety(url)
    return url


def _validate_command_for_transport(
    command: list[str] | None, transport: str | None
) -> list[str] | None:
    """Validate that command is provided for stdio transport."""
    if transport == "stdio" and not command:
        raise ValueError("Command is required for stdio transport")
    return command


class MCPServerCreate(BaseModel):
    """Schema for creating an MCP server integration."""

    name: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Server name slug (used as tool prefix, e.g. 'salesforce')",
    )
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Human-readable display name",
    )
    description: str = Field(
        default="",
        max_length=500,
        description="Description of this MCP server",
    )
    transport: MCPTransport = Field(
        ...,
        description="Transport type: 'http' or 'stdio'",
    )
    url: str | None = Field(
        default=None,
        max_length=2000,
        description="URL for HTTP transport (required if transport=http)",
    )
    command: list[str] | None = Field(
        default=None,
        description="Command for stdio transport (required if transport=stdio)",
    )
    env: dict[str, str] | None = Field(
        default=None,
        description="Environment variables for stdio subprocess",
    )
    auth_type: MCPAuthType = Field(
        default="none",
        description="Authentication type",
    )
    credentials: dict[str, Any] | None = Field(
        default=None,
        description="Credentials (api_key, token, or OAuth client config). Never returned in responses.",
    )

    @field_validator("name")
    @classmethod
    def validate_name_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                "Name must be a slug: lowercase letters, numbers, hyphens, underscores. "
                "Must start with a letter and end with a letter or number."
            )
        return v

    @field_validator("url")
    @classmethod
    def validate_url_for_http(cls, v: str | None, info: Any) -> str | None:
        return _validate_url_for_transport(v, info.data.get("transport"))

    @field_validator("command")
    @classmethod
    def validate_command_for_stdio(cls, v: list[str] | None, info: Any) -> list[str] | None:
        return _validate_command_for_transport(v, info.data.get("transport"))

    @model_validator(mode="after")
    def validate_auth_credentials(self) -> Self:
        """Ensure credentials are provided when auth_type requires them."""
        if self.auth_type not in ("none",) and not self.credentials:
            raise ValueError(f"Credentials are required when auth_type is '{self.auth_type}'")
        return self


class MCPServerUpdate(BaseModel):
    """Schema for updating an MCP server integration."""

    display_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    description: str | None = Field(
        default=None,
        max_length=500,
    )
    url: str | None = Field(
        default=None,
        max_length=2000,
    )
    command: list[str] | None = Field(default=None)
    env: dict[str, str] | None = Field(default=None)
    auth_type: MCPAuthType | None = Field(default=None)
    credentials: dict[str, Any] | None = Field(default=None)
    status: MCPServerStatusValue | None = Field(default=None)

    @field_validator("url")
    @classmethod
    def validate_url_safety(cls, v: str | None) -> str | None:
        if v is not None:
            _validate_url_safety(v)
        return v


class MCPToolInfo(BaseModel):
    """Discovered tool from an MCP server."""

    name: str
    description: str = ""


class MCPServerResponse(BaseModel):
    """Response schema for an MCP server."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str = Field(description="Server name slug")
    display_name: str
    description: str = ""
    transport: MCPTransport
    url: str | None = None
    command: list[str] | None = None
    auth_type: MCPAuthType
    has_credentials: bool = False
    status: MCPServerStatusValue
    discovered_tools: list[MCPToolInfo] = Field(default_factory=list)
    last_connected_at: str | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class MCPServerListResponse(BaseModel):
    """Response for listing MCP servers."""

    items: list[MCPServerResponse]
    total: int


class MCPServerTestRequest(BaseModel):
    """Schema for testing an MCP server connection without saving."""

    transport: MCPTransport
    url: str | None = None
    command: list[str] | None = None
    env: dict[str, str] | None = None
    auth_type: MCPAuthType = "none"
    credentials: dict[str, Any] | None = None

    @field_validator("url")
    @classmethod
    def validate_url_for_http(cls, v: str | None, info: Any) -> str | None:
        return _validate_url_for_transport(v, info.data.get("transport"))

    @field_validator("command")
    @classmethod
    def validate_command_for_stdio(cls, v: list[str] | None, info: Any) -> list[str] | None:
        return _validate_command_for_transport(v, info.data.get("transport"))

    @model_validator(mode="after")
    def validate_auth_credentials(self) -> Self:
        """Ensure credentials match auth_type."""
        if self.auth_type != "none" and not self.credentials:
            raise ValueError(f"Credentials are required when auth_type is '{self.auth_type}'")
        if self.auth_type == "none" and self.credentials:
            raise ValueError("Credentials should not be provided when auth_type is 'none'")
        return self


class MCPServerTestResponse(BaseModel):
    """Response from testing an MCP server connection."""

    success: bool
    tools_discovered: int = 0
    tool_names: list[str] = Field(default_factory=list)
    error: str | None = None

    @model_validator(mode="after")
    def validate_consistency(self) -> Self:
        """Ensure success/error/tools are consistent."""
        if not self.success and self.error is None:
            raise ValueError("error is required when success is False")
        if self.success and self.tools_discovered != len(self.tool_names):
            raise ValueError("tools_discovered must equal len(tool_names)")
        return self
