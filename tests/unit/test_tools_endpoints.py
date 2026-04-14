"""
Unit tests for empla.api.v1.endpoints.tools and the runner-side
HealthServer tool handlers.

The API proxies via EmployeeManager.get_health_port + httpx. Tests cover:
- _verify_employee 404 / cross-tenant
- 503 when runner not running (no port)
- 502 when runner returns non-200
- Happy-path proxy of the three runner endpoints
- HealthServer handler outputs (catalog, health, blocked) with a stub
  tool_router so we don't depend on a full BDI stack.
- Tools introspection disabled (tool_router=None) → 503 from the runner
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException

from empla.api.v1.endpoints import tools as tools_ep
from empla.runner.health import HealthServer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth(tenant_id: UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        role="member",
    )


def _request() -> SimpleNamespace:
    """Minimal stand-in for fastapi.Request — only `.app.state` is touched."""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))


def _request_with_client(client) -> SimpleNamespace:
    """Request stub that injects a shared httpx-like client onto app.state."""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runner_proxy_client=client)))


class _StubClient:
    """Mimics the relevant httpx.AsyncClient surface the proxy uses."""

    def __init__(self, *, get_impl):
        self._get = get_impl

    async def get(self, *args, **kwargs):
        return await self._get(*args, **kwargs)

    async def aclose(self):
        return None


def _verify_db(hit: bool) -> AsyncMock:
    db = AsyncMock()
    result = Mock()
    result.scalar_one_or_none.return_value = uuid4() if hit else None
    db.execute = AsyncMock(return_value=result)
    return db


def _stub_tool_router() -> SimpleNamespace:
    """Build a stub that quacks like ToolRouter for HealthServer's needs."""
    trust = SimpleNamespace(
        get_audit_log=Mock(
            return_value=[
                SimpleNamespace(
                    allowed=False,
                    tool_name="admin.delete_tenant",
                    reason="globally denied (destructive)",
                    employee_role="sales_ae",
                    timestamp=1234567890.0,
                ),
                SimpleNamespace(
                    allowed=True,
                    tool_name="email.send",
                    reason="allowed",
                    employee_role="sales_ae",
                    timestamp=1234567891.0,
                ),
            ]
        ),
        get_cycle_stats=Mock(
            return_value={
                "total_decisions": 2,
                "allowed": 1,
                "denied": 1,
                "tainted": False,
                "cycle_calls": 2,
                "max_calls_per_cycle": 50,
            }
        ),
    )
    return SimpleNamespace(
        get_all_tool_schemas=Mock(
            return_value=[
                {"name": "email.send", "description": "Send an email", "parameters": {}},
                {"name": "crm.update_deal", "description": "Update a CRM deal", "parameters": {}},
                {"name": "web_search", "description": "Search the web", "parameters": {}},
            ]
        ),
        get_enabled_capabilities=Mock(return_value=["email", "crm"]),
        get_integration_health=Mock(
            return_value={
                "name": "email",
                "status": "healthy",
                "success_count": 10,
                "failure_count": 0,
                "timeout_count": 0,
                "total_calls": 10,
                "avg_latency_ms": 120.5,
                "error_rate": 0.0,
                "last_error": None,
            }
        ),
        _trust=trust,
    )


# ---------------------------------------------------------------------------
# _verify_employee
# ---------------------------------------------------------------------------


class TestVerifyEmployee:
    @pytest.mark.asyncio
    async def test_missing_returns_404(self):
        with pytest.raises(HTTPException) as exc:
            await tools_ep._verify_employee(_verify_db(False), uuid4(), uuid4())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_hit_does_not_raise(self):
        await tools_ep._verify_employee(_verify_db(True), uuid4(), uuid4())


# ---------------------------------------------------------------------------
# _proxy_runner_get
# ---------------------------------------------------------------------------


class TestProxyRunnerGet:
    @pytest.mark.asyncio
    async def test_no_health_port_returns_503(self):
        with patch.object(tools_ep, "get_employee_manager") as mock_get_mgr:
            mgr = Mock()
            mgr.get_health_port = Mock(return_value=None)
            mock_get_mgr.return_value = mgr

            with pytest.raises(HTTPException) as exc:
                await tools_ep._proxy_runner_get(_request(), uuid4(), "/tools")
            assert exc.value.status_code == 503
            assert "not running" in exc.value.detail

    @pytest.mark.asyncio
    async def test_connect_refused_returns_503(self):
        with patch.object(tools_ep, "get_employee_manager") as mock_get_mgr:
            mgr = Mock()
            mgr.get_health_port = Mock(return_value=12345)
            mgr.get_health_token = Mock(return_value="t")
            mock_get_mgr.return_value = mgr

            async def _boom(*a, **kw):
                raise httpx.ConnectError("refused")

            with pytest.raises(HTTPException) as exc:
                await tools_ep._proxy_runner_get(
                    _request_with_client(_StubClient(get_impl=_boom)), uuid4(), "/tools"
                )
            assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_runner_503_propagates_as_503(self):
        """Runner says 'tools introspection not enabled' → API surfaces 503."""
        with patch.object(tools_ep, "get_employee_manager") as mock_get_mgr:
            mgr = Mock()
            mgr.get_health_port = Mock(return_value=12345)
            mgr.get_health_token = Mock(return_value="t")
            mock_get_mgr.return_value = mgr

            resp = Mock()
            resp.status_code = 503

            async def _get(*a, **kw):
                return resp

            with pytest.raises(HTTPException) as exc:
                await tools_ep._proxy_runner_get(
                    _request_with_client(_StubClient(get_impl=_get)), uuid4(), "/tools"
                )
            assert exc.value.status_code == 503
            assert "introspection" in exc.value.detail

    @pytest.mark.asyncio
    async def test_runner_other_error_returns_502(self):
        with patch.object(tools_ep, "get_employee_manager") as mock_get_mgr:
            mgr = Mock()
            mgr.get_health_port = Mock(return_value=12345)
            mgr.get_health_token = Mock(return_value="t")
            mock_get_mgr.return_value = mgr

            resp = Mock()
            resp.status_code = 500
            resp.json = Mock(return_value={})

            async def _get(*a, **kw):
                return resp

            with pytest.raises(HTTPException) as exc:
                await tools_ep._proxy_runner_get(
                    _request_with_client(_StubClient(get_impl=_get)), uuid4(), "/tools"
                )
            assert exc.value.status_code == 502

    @pytest.mark.asyncio
    async def test_happy_path_returns_payload(self):
        with patch.object(tools_ep, "get_employee_manager") as mock_get_mgr:
            mgr = Mock()
            mgr.get_health_port = Mock(return_value=12345)
            mgr.get_health_token = Mock(return_value="t")
            mock_get_mgr.return_value = mgr

            resp = Mock()
            resp.status_code = 200
            resp.json = Mock(return_value={"items": [], "total": 0, "integrations": []})

            async def _get(*a, **kw):
                return resp

            payload = await tools_ep._proxy_runner_get(
                _request_with_client(_StubClient(get_impl=_get)), uuid4(), "/tools"
            )
            assert payload == {"items": [], "total": 0, "integrations": []}


# ---------------------------------------------------------------------------
# Endpoint integration (verify + proxy)
# ---------------------------------------------------------------------------


class TestEndpoints:
    @pytest.mark.asyncio
    async def test_list_tools_404_on_missing_employee(self):
        db = _verify_db(False)
        with pytest.raises(HTTPException) as exc:
            await tools_ep.list_tools(request=_request(), db=db, auth=_auth(), employee_id=uuid4())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_tools_proxies_runner(self):
        db = _verify_db(True)
        runner_payload = {
            "items": [{"name": "email.send", "description": "send", "integration": "email"}],
            "total": 1,
            "integrations": ["email"],
        }
        with patch.object(
            tools_ep, "_proxy_runner_get", new_callable=AsyncMock, return_value=runner_payload
        ):
            resp = await tools_ep.list_tools(
                request=_request(), db=db, auth=_auth(), employee_id=uuid4()
            )
            assert resp.total == 1
            assert resp.items[0].name == "email.send"
            assert resp.integrations == ["email"]

    @pytest.mark.asyncio
    async def test_get_tool_health_rejects_path_traversal(self):
        db = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await tools_ep.get_tool_health(
                request=_request(),
                db=db,
                auth=_auth(),
                employee_id=uuid4(),
                tool_name="../../etc/passwd",
            )
        assert exc.value.status_code == 400
        # DB must not be touched on rejection
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_tool_health_proxies(self):
        db = _verify_db(True)
        runner_payload = {
            "name": "email",
            "status": "healthy",
            "success_count": 5,
            "failure_count": 0,
            "timeout_count": 0,
            "total_calls": 5,
            "avg_latency_ms": 100.0,
            "error_rate": 0.0,
            "last_error": None,
        }
        with patch.object(
            tools_ep, "_proxy_runner_get", new_callable=AsyncMock, return_value=runner_payload
        ):
            resp = await tools_ep.get_tool_health(
                request=_request(), db=db, auth=_auth(), employee_id=uuid4(), tool_name="email.send"
            )
            assert resp.name == "email"
            assert resp.status == "healthy"

    @pytest.mark.asyncio
    async def test_list_blocked_tools_proxies(self):
        db = _verify_db(True)
        runner_payload = {
            "items": [
                {
                    "tool_name": "admin.delete_tenant",
                    "reason": "globally denied",
                    "employee_role": "sales_ae",
                    "timestamp": 1234567890.0,
                }
            ],
            "total": 1,
            "stats": {
                "total_decisions": 5,
                "allowed": 4,
                "denied": 1,
                "tainted": False,
                "cycle_calls": 5,
                "max_calls_per_cycle": 50,
            },
        }
        with patch.object(
            tools_ep, "_proxy_runner_get", new_callable=AsyncMock, return_value=runner_payload
        ):
            resp = await tools_ep.list_blocked_tools(
                request=_request(), db=db, auth=_auth(), employee_id=uuid4()
            )
            assert resp.total == 1
            assert resp.items[0].tool_name == "admin.delete_tenant"
            assert resp.stats.denied == 1


# ---------------------------------------------------------------------------
# HealthServer handler unit tests (no network — call directly)
# ---------------------------------------------------------------------------


class TestHealthServerToolHandlers:
    def _server(self, tool_router=None) -> HealthServer:
        return HealthServer(employee_id=uuid4(), port=0, tool_router=tool_router)

    def test_tools_list_503_when_no_router(self):
        body, code = self._server(tool_router=None)._handle_tools_list()
        assert code == 503
        assert "introspection" in body.lower()

    def test_tools_blocked_503_when_no_router(self):
        _body, code = self._server(tool_router=None)._handle_tools_blocked()
        assert code == 503

    def test_tool_health_503_when_no_router(self):
        _body, code = self._server(tool_router=None)._handle_tool_health("/tools/email.send/health")
        assert code == 503

    def test_tools_list_returns_catalog(self):
        srv = self._server(tool_router=_stub_tool_router())
        body, code = srv._handle_tools_list()
        assert code == 200
        data = json.loads(body)
        assert data["total"] == 3
        names = [t["name"] for t in data["items"]]
        assert "email.send" in names
        assert "web_search" in names
        # web_search has no dot, so integration is None
        web = next(t for t in data["items"] if t["name"] == "web_search")
        assert web["integration"] is None
        # email.send is namespaced
        email = next(t for t in data["items"] if t["name"] == "email.send")
        assert email["integration"] == "email"
        assert "email" in data["integrations"]

    def test_tool_health_returns_integration_status(self):
        srv = self._server(tool_router=_stub_tool_router())
        body, code = srv._handle_tool_health("/tools/email.send/health")
        assert code == 200
        data = json.loads(body)
        assert data["name"] == "email"
        assert data["status"] == "healthy"

    def test_tool_health_400_on_empty_name(self):
        srv = self._server(tool_router=_stub_tool_router())
        _, code = srv._handle_tool_health("/tools//health")
        assert code == 400

    def test_tool_description_truncated_to_500_chars(self):
        """MCP-discovered tool descriptions are length-capped (security)."""
        from empla.runner import health as health_mod

        long_desc = "A" * 1000
        stub = SimpleNamespace(
            get_all_tool_schemas=Mock(
                return_value=[{"name": "evil.tool", "description": long_desc}]
            ),
            get_enabled_capabilities=Mock(return_value=["evil"]),
            get_integration_health=Mock(return_value={}),
            _trust=None,
        )
        srv = self._server(tool_router=stub)
        body, code = srv._handle_tools_list()
        assert code == 200
        data = json.loads(body)
        assert len(data["items"][0]["description"]) == health_mod._MAX_DESCRIPTION_CHARS

    def test_tools_blocked_returns_only_denied(self):
        srv = self._server(tool_router=_stub_tool_router())
        body, code = srv._handle_tools_blocked()
        assert code == 200
        data = json.loads(body)
        assert data["total"] == 1
        assert data["items"][0]["tool_name"] == "admin.delete_tenant"
        assert data["stats"]["denied"] == 1

    def test_tools_list_embeds_health_map(self):
        """N+1 fix: the catalog response includes per-integration health."""
        srv = self._server(tool_router=_stub_tool_router())
        body, code = srv._handle_tools_list()
        assert code == 200
        data = json.loads(body)
        assert "health" in data
        assert "email" in data["health"]
        assert data["health"]["email"]["status"] == "healthy"


# ---------------------------------------------------------------------------
# Runner-side auth gate (PR #80 review fix)
# ---------------------------------------------------------------------------


class TestRunnerAuth:
    """
    Non-/health endpoints require the X-Runner-Token header. /health stays
    unauthenticated so liveness probes work.
    """

    @pytest.mark.asyncio
    async def test_health_unauthenticated_passes(self):
        import asyncio

        srv = HealthServer(employee_id=uuid4(), port=0, auth_token="secret-abc")
        await srv.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", srv.port)
            writer.write(b"GET /health HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
            await writer.drain()
            data = await asyncio.wait_for(reader.read(4096), timeout=2.0)
            writer.close()
            await writer.wait_closed()
            assert b"200 OK" in data
        finally:
            await srv.stop()

    @pytest.mark.asyncio
    async def test_tools_endpoints_require_token(self):
        import asyncio

        srv = HealthServer(
            employee_id=uuid4(),
            port=0,
            tool_router=_stub_tool_router(),
            auth_token="secret-abc",
        )
        await srv.start()
        try:
            # No token → 401
            reader, writer = await asyncio.open_connection("127.0.0.1", srv.port)
            writer.write(b"GET /tools HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
            await writer.drain()
            data = await asyncio.wait_for(reader.read(4096), timeout=2.0)
            writer.close()
            await writer.wait_closed()
            assert b"401 Unauthorized" in data

            # Wrong token → 401
            reader, writer = await asyncio.open_connection("127.0.0.1", srv.port)
            writer.write(
                b"GET /tools HTTP/1.1\r\nHost: x\r\nX-Runner-Token: nope\r\nConnection: close\r\n\r\n"
            )
            await writer.drain()
            data = await asyncio.wait_for(reader.read(4096), timeout=2.0)
            writer.close()
            await writer.wait_closed()
            assert b"401 Unauthorized" in data

            # Correct token → 200
            reader, writer = await asyncio.open_connection("127.0.0.1", srv.port)
            writer.write(
                b"GET /tools HTTP/1.1\r\nHost: x\r\nX-Runner-Token: secret-abc\r\nConnection: close\r\n\r\n"
            )
            await writer.drain()
            data = await asyncio.wait_for(reader.read(4096), timeout=2.0)
            writer.close()
            await writer.wait_closed()
            assert b"200 OK" in data
        finally:
            await srv.stop()

    @pytest.mark.asyncio
    async def test_no_auth_token_disables_gate(self):
        """auth_token=None preserves dev-frictionless behavior."""
        import asyncio

        srv = HealthServer(
            employee_id=uuid4(),
            port=0,
            tool_router=_stub_tool_router(),
            auth_token=None,
        )
        await srv.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", srv.port)
            writer.write(b"GET /tools HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
            await writer.drain()
            data = await asyncio.wait_for(reader.read(4096), timeout=2.0)
            writer.close()
            await writer.wait_closed()
            assert b"200 OK" in data
        finally:
            await srv.stop()


# ---------------------------------------------------------------------------
# last_error redaction
# ---------------------------------------------------------------------------


class TestRedaction:
    def test_redact_strips_bearer(self):
        from empla.runner.health import _redact

        assert "[REDACTED]" in (_redact("Authorization: Bearer abc.def.ghi") or "")

    def test_redact_strips_query_token(self):
        from empla.runner.health import _redact

        result = _redact("https://api.example.com/v1?token=xyz123abc&foo=bar") or ""
        assert "[REDACTED]" in result
        assert "xyz123abc" not in result

    def test_redact_strips_api_key(self):
        from empla.runner.health import _redact

        # Build the test fixture so the literal doesn't appear in source
        # (avoids tripping GitHub's Stripe-key secret-scanning pattern on
        # legitimate test data).
        fake_key = "sk" + "_" + "test" + "_" + ("X" * 24)
        result = _redact(f"Bad request: {fake_key}") or ""
        assert "[REDACTED_KEY]" in result

    def test_redact_strips_email(self):
        from empla.runner.health import _redact

        result = _redact("Permission denied for user@example.com") or ""
        assert "[REDACTED_EMAIL]" in result
        assert "user@example.com" not in result

    def test_redact_caps_length(self):
        from empla.runner.health import _redact

        long_msg = "x" * 1000
        result = _redact(long_msg) or ""
        assert len(result) <= 520

    def test_redact_handles_none(self):
        from empla.runner.health import _redact

        assert _redact(None) is None
        assert _redact("") == ""


# ---------------------------------------------------------------------------
# Tenant isolation (mirrors PR #79 memory tests)
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """
    `_verify_employee` filters by both employee_id AND tenant_id. Cross-tenant
    requests must 404 — never leak existence.
    """

    @pytest.mark.asyncio
    async def test_cross_tenant_returns_404_list_tools(self):
        db = _verify_db(False)
        with pytest.raises(HTTPException) as exc:
            await tools_ep.list_tools(request=_request(), db=db, auth=_auth(), employee_id=uuid4())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_tenant_returns_404_get_tool_health(self):
        db = _verify_db(False)
        with pytest.raises(HTTPException) as exc:
            await tools_ep.get_tool_health(
                request=_request(), db=db, auth=_auth(), employee_id=uuid4(), tool_name="email.send"
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_tenant_returns_404_list_blocked_tools(self):
        db = _verify_db(False)
        with pytest.raises(HTTPException) as exc:
            await tools_ep.list_blocked_tools(
                request=_request(), db=db, auth=_auth(), employee_id=uuid4()
            )
        assert exc.value.status_code == 404

    def test_verify_employee_query_filters_by_tenant_id(self):
        """Compiled SQL must include both tenant_id and employee_id in WHERE."""
        from sqlalchemy import select

        from empla.models.employee import Employee

        tenant_id = uuid4()
        employee_id = uuid4()
        q = select(Employee.id).where(
            Employee.id == employee_id,
            Employee.tenant_id == tenant_id,
            Employee.deleted_at.is_(None),
        )
        sql = str(q.compile(compile_kwargs={"literal_binds": False}))
        assert "tenant_id" in sql.lower()
        assert "deleted_at" in sql.lower()


# ---------------------------------------------------------------------------
# Proxy error coverage gaps
# ---------------------------------------------------------------------------


class TestProxyErrorPaths:
    @pytest.mark.asyncio
    async def test_timeout_returns_504(self):
        with patch.object(tools_ep, "get_employee_manager") as mock_get_mgr:
            mgr = Mock()
            mgr.get_health_port = Mock(return_value=12345)
            mgr.get_health_token = Mock(return_value="t")
            mock_get_mgr.return_value = mgr

            async def _slow(*a, **kw):
                raise httpx.TimeoutException("slow")

            with pytest.raises(HTTPException) as exc:
                await tools_ep._proxy_runner_get(
                    _request_with_client(_StubClient(get_impl=_slow)), uuid4(), "/tools"
                )
            assert exc.value.status_code == 504

    @pytest.mark.asyncio
    async def test_malformed_json_returns_502(self):
        with patch.object(tools_ep, "get_employee_manager") as mock_get_mgr:
            mgr = Mock()
            mgr.get_health_port = Mock(return_value=12345)
            mgr.get_health_token = Mock(return_value="t")
            mock_get_mgr.return_value = mgr

            resp = Mock()
            resp.status_code = 200
            resp.json = Mock(side_effect=ValueError("bad"))

            async def _get(*a, **kw):
                return resp

            with pytest.raises(HTTPException) as exc:
                await tools_ep._proxy_runner_get(
                    _request_with_client(_StubClient(get_impl=_get)), uuid4(), "/tools"
                )
            assert exc.value.status_code == 502
            assert "malformed" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_runner_401_returns_502(self):
        """Token mismatch (shouldn't happen in production) → 502 not 503."""
        with patch.object(tools_ep, "get_employee_manager") as mock_get_mgr:
            mgr = Mock()
            mgr.get_health_port = Mock(return_value=12345)
            mgr.get_health_token = Mock(return_value="bad")
            mock_get_mgr.return_value = mgr

            resp = Mock()
            resp.status_code = 401

            async def _get(*a, **kw):
                return resp

            with pytest.raises(HTTPException) as exc:
                await tools_ep._proxy_runner_get(
                    _request_with_client(_StubClient(get_impl=_get)), uuid4(), "/tools"
                )
            assert exc.value.status_code == 502
            assert "token" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# Strict tool_name validation (security)
# ---------------------------------------------------------------------------


class TestToolNameValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_name",
        [
            "../../etc/passwd",
            "foo/bar",
            "foo\\bar",
            "foo?bar",
            "foo#bar",
            "foo%2Fbar",
            "",
            "   ",
            "blocked",  # reserved — collides with /tools/blocked
            "foo bar",  # whitespace
            "foo\x00bar",  # null byte
        ],
    )
    async def test_strict_tool_name_rejection(self, bad_name):
        db = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await tools_ep.get_tool_health(
                request=_request(), db=db, auth=_auth(), employee_id=uuid4(), tool_name=bad_name
            )
        assert exc.value.status_code == 400
        # DB must not be touched on rejection
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("good_name", ["email.send", "crm.update_deal", "web_search", "a-b"])
    async def test_strict_tool_name_acceptance(self, good_name):
        db = _verify_db(True)
        with patch.object(
            tools_ep,
            "_proxy_runner_get",
            new_callable=AsyncMock,
            return_value={
                "name": "email",
                "status": "healthy",
                "success_count": 0,
                "failure_count": 0,
                "timeout_count": 0,
                "total_calls": 0,
                "avg_latency_ms": 0.0,
                "error_rate": 0.0,
                "last_error": None,
            },
        ):
            resp = await tools_ep.get_tool_health(
                request=_request(), db=db, auth=_auth(), employee_id=uuid4(), tool_name=good_name
            )
            assert resp.name == "email"


# ---------------------------------------------------------------------------
# Real HTTP path test — proves dispatch works end-to-end
# (catches the route-ordering bug where /tools/blocked could shadow
# /tools/blocked/health, which the API now reserves anyway but the runner
# should also dispatch correctly under a real socket round-trip)
# ---------------------------------------------------------------------------


class TestHealthServerHTTPDispatch:
    @pytest.mark.asyncio
    async def test_real_http_dispatch_routes_correctly(self):
        """
        Spin up a real HealthServer on an ephemeral port, hit each of the 3
        new routes via a real socket, and confirm the response matches.
        """
        import asyncio

        srv = HealthServer(employee_id=uuid4(), port=0, tool_router=_stub_tool_router())
        await srv.start()
        try:
            port = srv.port

            async def _get(path: str) -> tuple[int, bytes]:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.write(
                    f"GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode()
                )
                await writer.drain()
                data = await asyncio.wait_for(reader.read(8192), timeout=2.0)
                writer.close()
                await writer.wait_closed()
                # Parse status line
                status_line, _, body_bytes = data.partition(b"\r\n\r\n")
                status_code = int(status_line.split(b" ")[1])
                return status_code, body_bytes

            # /tools list
            code, body = await _get("/tools")
            assert code == 200
            assert b'"items"' in body
            assert b"email.send" in body

            # /tools/blocked
            code, body = await _get("/tools/blocked")
            assert code == 200
            assert b"admin.delete_tenant" in body

            # /tools/email.send/health
            code, body = await _get("/tools/email.send/health")
            assert code == 200
            assert b'"name"' in body
            assert b"email" in body

            # /tools/blocked/health — the route ordering bug would have
            # mis-routed this to _handle_tools_blocked. The fixed dispatcher
            # routes it to _handle_tool_health (where integration="blocked"
            # has no health record → returns the empty-default integration).
            # Either way it must NOT return the blocked-list shape.
            code, body = await _get("/tools/blocked/health")
            assert code == 200
            assert b'"items"' not in body  # blocked-list shape would have items[]

            # Unknown path → 404
            code, _ = await _get("/tools/blocked/extra")
            assert code == 404
        finally:
            await srv.stop()
