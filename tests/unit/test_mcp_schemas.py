"""
tests/unit/test_mcp_schemas.py - MCP Server Schema Validation Tests

Tests for:
- SSRF URL validation (_validate_url_safety, validate_url_dns_safety)
- Slug validation
- Transport/URL/command cross-validation
- Auth/credential cross-validation and credential shape validation
- MCPServerTestResponse consistency
"""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from empla.api.v1.schemas.mcp_server import (
    MCPServerCreate,
    MCPServerTestRequest,
    MCPServerTestResponse,
    _is_dangerous_ip,
    _validate_url_safety,
    validate_url_dns_safety,
)


class TestIsDangerousIP:
    """Tests for _is_dangerous_ip helper."""

    def test_loopback_ipv4(self):
        import ipaddress

        assert _is_dangerous_ip(ipaddress.ip_address("127.0.0.1"))

    def test_loopback_ipv6(self):
        import ipaddress

        assert _is_dangerous_ip(ipaddress.ip_address("::1"))

    def test_private_10(self):
        import ipaddress

        assert _is_dangerous_ip(ipaddress.ip_address("10.0.0.1"))

    def test_private_172(self):
        import ipaddress

        assert _is_dangerous_ip(ipaddress.ip_address("172.16.0.1"))

    def test_private_192(self):
        import ipaddress

        assert _is_dangerous_ip(ipaddress.ip_address("192.168.1.1"))

    def test_link_local(self):
        import ipaddress

        assert _is_dangerous_ip(ipaddress.ip_address("169.254.169.254"))

    def test_public_ip(self):
        import ipaddress

        assert not _is_dangerous_ip(ipaddress.ip_address("8.8.8.8"))


class TestValidateUrlSafety:
    """Tests for _validate_url_safety (fast synchronous checks)."""

    def test_rejects_ftp_scheme(self):
        with pytest.raises(ValueError, match="Only http/https URLs are allowed"):
            _validate_url_safety("ftp://example.com/mcp")

    def test_rejects_no_hostname(self):
        with pytest.raises(ValueError, match="URL must have a valid hostname"):
            _validate_url_safety("http:///path")

    def test_rejects_localhost(self):
        with pytest.raises(ValueError, match="Cannot connect to reserved hostnames"):
            _validate_url_safety("https://localhost/mcp")

    def test_rejects_localhost_trailing_dot(self):
        with pytest.raises(ValueError, match="Cannot connect to reserved hostnames"):
            _validate_url_safety("https://localhost./mcp")

    def test_rejects_metadata_google(self):
        with pytest.raises(ValueError, match="Cannot connect to reserved hostnames"):
            _validate_url_safety("http://metadata.google.internal/computeMetadata")

    def test_rejects_loopback_ip(self):
        with pytest.raises(ValueError, match="Cannot connect to private/internal"):
            _validate_url_safety("http://127.0.0.1/mcp")

    def test_rejects_private_ip_10(self):
        with pytest.raises(ValueError, match="Cannot connect to private/internal"):
            _validate_url_safety("http://10.0.0.1/mcp")

    def test_rejects_private_ip_192(self):
        with pytest.raises(ValueError, match="Cannot connect to private/internal"):
            _validate_url_safety("http://192.168.1.1/mcp")

    def test_rejects_link_local_ip(self):
        with pytest.raises(ValueError, match="Cannot connect to private/internal"):
            _validate_url_safety("http://169.254.169.254/metadata")

    def test_rejects_ipv6_loopback(self):
        with pytest.raises(ValueError, match="Cannot connect to private/internal"):
            _validate_url_safety("http://[::1]/mcp")

    def test_accepts_public_url(self):
        result = _validate_url_safety("https://api.example.com/mcp")
        assert result == "https://api.example.com/mcp"

    def test_accepts_public_ip(self):
        result = _validate_url_safety("https://8.8.8.8/mcp")
        assert result == "https://8.8.8.8/mcp"

    def test_accepts_hostname_not_in_blocklist(self):
        # DNS hostnames pass fast validation (DNS check is async)
        result = _validate_url_safety("https://mcp.example.com/sse")
        assert result == "https://mcp.example.com/sse"


class TestValidateUrlDnsSafety:
    """Tests for validate_url_dns_safety (async DNS resolution)."""

    @pytest.mark.asyncio
    async def test_rejects_hostname_resolving_to_private_ip(self):
        mock_addrinfo = [(2, 1, 6, "", ("10.0.0.1", 0))]
        with patch("socket.getaddrinfo", return_value=mock_addrinfo):
            with pytest.raises(ValueError, match="Cannot connect to private/internal"):
                await validate_url_dns_safety("https://evil.example.com/mcp")

    @pytest.mark.asyncio
    async def test_rejects_hostname_resolving_to_loopback(self):
        mock_addrinfo = [(2, 1, 6, "", ("127.0.0.1", 0))]
        with patch("socket.getaddrinfo", return_value=mock_addrinfo):
            with pytest.raises(ValueError, match="Cannot connect to private/internal"):
                await validate_url_dns_safety("https://evil.example.com/mcp")

    @pytest.mark.asyncio
    async def test_rejects_unresolvable_hostname(self):
        import socket

        with patch("socket.getaddrinfo", side_effect=socket.gaierror("not found")):
            with pytest.raises(ValueError, match="Cannot resolve hostname"):
                await validate_url_dns_safety("https://doesnt-exist.invalid/mcp")

    @pytest.mark.asyncio
    async def test_rejects_unicode_error(self):
        with patch("socket.getaddrinfo", side_effect=UnicodeError("bad hostname")):
            with pytest.raises(ValueError, match="Cannot resolve hostname"):
                await validate_url_dns_safety("https://bad\x00host.com/mcp")

    @pytest.mark.asyncio
    async def test_accepts_hostname_resolving_to_public_ip(self):
        mock_addrinfo = [(2, 1, 6, "", ("93.184.216.34", 0))]
        with patch("socket.getaddrinfo", return_value=mock_addrinfo):
            await validate_url_dns_safety("https://example.com/mcp")  # should not raise

    @pytest.mark.asyncio
    async def test_skips_ip_literals(self):
        # IP literals are already validated by _validate_url_safety, DNS check is a no-op
        await validate_url_dns_safety("https://8.8.8.8/mcp")  # should not raise

    @pytest.mark.asyncio
    async def test_skips_blocked_hostnames(self):
        # Blocked hostnames are already rejected by _validate_url_safety
        await validate_url_dns_safety("https://localhost/mcp")  # should not raise

    @pytest.mark.asyncio
    async def test_checks_all_resolved_ips(self):
        # One safe IP + one dangerous IP = reject
        mock_addrinfo = [
            (2, 1, 6, "", ("93.184.216.34", 0)),
            (2, 1, 6, "", ("10.0.0.1", 0)),
        ]
        with patch("socket.getaddrinfo", return_value=mock_addrinfo):
            with pytest.raises(ValueError, match="Cannot connect to private/internal"):
                await validate_url_dns_safety("https://dual.example.com/mcp")


class TestMCPServerCreateSlug:
    """Tests for name slug validation."""

    def test_valid_slug(self):
        s = MCPServerCreate(
            name="salesforce",
            display_name="Salesforce",
            transport="http",
            url="https://api.example.com/mcp",
        )
        assert s.name == "salesforce"

    def test_valid_slug_with_hyphens(self):
        s = MCPServerCreate(
            name="my-mcp-1",
            display_name="My MCP",
            transport="http",
            url="https://api.example.com/mcp",
        )
        assert s.name == "my-mcp-1"

    def test_valid_slug_with_underscores(self):
        s = MCPServerCreate(
            name="my_mcp",
            display_name="My MCP",
            transport="http",
            url="https://api.example.com/mcp",
        )
        assert s.name == "my_mcp"

    def test_rejects_uppercase(self):
        with pytest.raises(ValidationError, match="slug"):
            MCPServerCreate(
                name="MyServer",
                display_name="My Server",
                transport="http",
                url="https://api.example.com/mcp",
            )

    def test_rejects_single_char(self):
        with pytest.raises(ValidationError):
            MCPServerCreate(
                name="a",
                display_name="A",
                transport="http",
                url="https://api.example.com/mcp",
            )

    def test_rejects_starts_with_number(self):
        with pytest.raises(ValidationError, match="slug"):
            MCPServerCreate(
                name="1server",
                display_name="Server",
                transport="http",
                url="https://api.example.com/mcp",
            )

    def test_rejects_ends_with_hyphen(self):
        with pytest.raises(ValidationError, match="slug"):
            MCPServerCreate(
                name="server-",
                display_name="Server",
                transport="http",
                url="https://api.example.com/mcp",
            )


class TestMCPServerCreateTransport:
    """Tests for transport/url/command cross-validation."""

    def test_http_requires_url(self):
        # Must pass url=None explicitly; Pydantic v2 skips field_validators for defaults
        with pytest.raises(ValidationError, match="URL is required"):
            MCPServerCreate(
                name="test-server",
                display_name="Test",
                transport="http",
                url=None,
            )

    def test_stdio_requires_command(self):
        with pytest.raises(ValidationError, match="Command is required"):
            MCPServerCreate(
                name="test-server",
                display_name="Test",
                transport="stdio",
                command=None,
            )

    def test_http_with_url_valid(self):
        s = MCPServerCreate(
            name="test-server",
            display_name="Test",
            transport="http",
            url="https://api.example.com/mcp",
        )
        assert s.url == "https://api.example.com/mcp"

    def test_stdio_with_command_valid(self):
        s = MCPServerCreate(
            name="test-server",
            display_name="Test",
            transport="stdio",
            command=["npx", "-y", "some-mcp-server"],
        )
        assert s.command == ["npx", "-y", "some-mcp-server"]


class TestMCPServerCreateAuth:
    """Tests for auth_type/credentials validation and credential shape."""

    def test_api_key_requires_credentials(self):
        with pytest.raises(ValidationError, match="Credentials are required"):
            MCPServerCreate(
                name="test-server",
                display_name="Test",
                transport="http",
                url="https://api.example.com/mcp",
                auth_type="api_key",
            )

    def test_none_rejects_credentials(self):
        with pytest.raises(ValidationError, match="should not be provided"):
            MCPServerCreate(
                name="test-server",
                display_name="Test",
                transport="http",
                url="https://api.example.com/mcp",
                auth_type="none",
                credentials={"api_key": "sk-123"},
            )

    def test_api_key_with_valid_credentials(self):
        s = MCPServerCreate(
            name="test-server",
            display_name="Test",
            transport="http",
            url="https://api.example.com/mcp",
            auth_type="api_key",
            credentials={"api_key": "sk-123"},
        )
        assert s.credentials == {"api_key": "sk-123"}

    def test_api_key_with_wrong_credential_shape(self):
        with pytest.raises(ValidationError, match="api_key auth requires"):
            MCPServerCreate(
                name="test-server",
                display_name="Test",
                transport="http",
                url="https://api.example.com/mcp",
                auth_type="api_key",
                credentials={"key": "sk-123"},  # wrong key name
            )

    def test_bearer_token_requires_token_key(self):
        with pytest.raises(ValidationError, match="bearer_token auth requires"):
            MCPServerCreate(
                name="test-server",
                display_name="Test",
                transport="http",
                url="https://api.example.com/mcp",
                auth_type="bearer_token",
                credentials={"bearer": "tok-123"},  # wrong key name
            )

    def test_bearer_token_with_valid_credentials(self):
        s = MCPServerCreate(
            name="test-server",
            display_name="Test",
            transport="http",
            url="https://api.example.com/mcp",
            auth_type="bearer_token",
            credentials={"token": "tok-123"},
        )
        assert s.credentials == {"token": "tok-123"}


class TestMCPServerTestResponse:
    """Tests for MCPServerTestResponse consistency validator."""

    def test_failure_requires_error(self):
        with pytest.raises(ValidationError, match="error is required"):
            MCPServerTestResponse(success=False)

    def test_success_requires_matching_tool_count(self):
        with pytest.raises(ValidationError, match="tools_discovered must equal"):
            MCPServerTestResponse(
                success=True,
                tools_discovered=2,
                tool_names=["a"],
            )

    def test_valid_success(self):
        r = MCPServerTestResponse(
            success=True,
            tools_discovered=2,
            tool_names=["a", "b"],
        )
        assert r.tools_discovered == 2

    def test_valid_failure(self):
        r = MCPServerTestResponse(success=False, error="Connection refused")
        assert r.error == "Connection refused"


class TestMCPServerTestRequestAuth:
    """Tests for MCPServerTestRequest credential shape validation."""

    def test_api_key_with_wrong_shape(self):
        with pytest.raises(ValidationError, match="api_key auth requires"):
            MCPServerTestRequest(
                transport="http",
                url="https://api.example.com/mcp",
                auth_type="api_key",
                credentials={"wrong": "value"},
            )

    def test_api_key_with_valid_shape(self):
        r = MCPServerTestRequest(
            transport="http",
            url="https://api.example.com/mcp",
            auth_type="api_key",
            credentials={"api_key": "sk-123"},
        )
        assert r.credentials == {"api_key": "sk-123"}
