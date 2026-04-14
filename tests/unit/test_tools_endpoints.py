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
                await tools_ep._proxy_runner_get(uuid4(), "/tools")
            assert exc.value.status_code == 503
            assert "not running" in exc.value.detail

    @pytest.mark.asyncio
    async def test_connect_refused_returns_503(self):
        with patch.object(tools_ep, "get_employee_manager") as mock_get_mgr:
            mgr = Mock()
            mgr.get_health_port = Mock(return_value=12345)
            mock_get_mgr.return_value = mgr

            class _BoomClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    return False

                async def get(self, *a, **kw):
                    raise httpx.ConnectError("refused")

            with patch.object(tools_ep.httpx, "AsyncClient", _BoomClient):
                with pytest.raises(HTTPException) as exc:
                    await tools_ep._proxy_runner_get(uuid4(), "/tools")
                assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_runner_503_propagates_as_503(self):
        """Runner says 'tools introspection not enabled' → API surfaces 503."""
        with patch.object(tools_ep, "get_employee_manager") as mock_get_mgr:
            mgr = Mock()
            mgr.get_health_port = Mock(return_value=12345)
            mock_get_mgr.return_value = mgr

            resp = Mock()
            resp.status_code = 503

            class _Client:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    return False

                async def get(self, *a, **kw):
                    return resp

            with patch.object(tools_ep.httpx, "AsyncClient", _Client):
                with pytest.raises(HTTPException) as exc:
                    await tools_ep._proxy_runner_get(uuid4(), "/tools")
                assert exc.value.status_code == 503
                assert "introspection" in exc.value.detail

    @pytest.mark.asyncio
    async def test_runner_other_error_returns_502(self):
        with patch.object(tools_ep, "get_employee_manager") as mock_get_mgr:
            mgr = Mock()
            mgr.get_health_port = Mock(return_value=12345)
            mock_get_mgr.return_value = mgr

            resp = Mock()
            resp.status_code = 500
            resp.json = Mock(return_value={})

            class _Client:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    return False

                async def get(self, *a, **kw):
                    return resp

            with patch.object(tools_ep.httpx, "AsyncClient", _Client):
                with pytest.raises(HTTPException) as exc:
                    await tools_ep._proxy_runner_get(uuid4(), "/tools")
                assert exc.value.status_code == 502

    @pytest.mark.asyncio
    async def test_happy_path_returns_payload(self):
        with patch.object(tools_ep, "get_employee_manager") as mock_get_mgr:
            mgr = Mock()
            mgr.get_health_port = Mock(return_value=12345)
            mock_get_mgr.return_value = mgr

            resp = Mock()
            resp.status_code = 200
            resp.json = Mock(return_value={"items": [], "total": 0, "integrations": []})

            class _Client:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    return False

                async def get(self, *a, **kw):
                    return resp

            with patch.object(tools_ep.httpx, "AsyncClient", _Client):
                payload = await tools_ep._proxy_runner_get(uuid4(), "/tools")
                assert payload == {"items": [], "total": 0, "integrations": []}


# ---------------------------------------------------------------------------
# Endpoint integration (verify + proxy)
# ---------------------------------------------------------------------------


class TestEndpoints:
    @pytest.mark.asyncio
    async def test_list_tools_404_on_missing_employee(self):
        db = _verify_db(False)
        with pytest.raises(HTTPException) as exc:
            await tools_ep.list_tools(db=db, auth=_auth(), employee_id=uuid4())
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
            resp = await tools_ep.list_tools(db=db, auth=_auth(), employee_id=uuid4())
            assert resp.total == 1
            assert resp.items[0].name == "email.send"
            assert resp.integrations == ["email"]

    @pytest.mark.asyncio
    async def test_get_tool_health_rejects_path_traversal(self):
        db = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await tools_ep.get_tool_health(
                db=db, auth=_auth(), employee_id=uuid4(), tool_name="../../etc/passwd"
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
                db=db, auth=_auth(), employee_id=uuid4(), tool_name="email.send"
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
            resp = await tools_ep.list_blocked_tools(db=db, auth=_auth(), employee_id=uuid4())
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
        _body, code = self._server(tool_router=None)._handle_tool_health(
            "GET /tools/email.send/health HTTP/1.1"
        )
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
        body, code = srv._handle_tool_health("GET /tools/email.send/health HTTP/1.1")
        assert code == 200
        data = json.loads(body)
        assert data["name"] == "email"
        assert data["status"] == "healthy"

    def test_tool_health_400_on_bad_path(self):
        srv = self._server(tool_router=_stub_tool_router())
        # Missing /health suffix
        _, code = srv._handle_tool_health("GET /tools/email.send HTTP/1.1")
        assert code == 400

    def test_tool_health_400_on_empty_name(self):
        srv = self._server(tool_router=_stub_tool_router())
        _, code = srv._handle_tool_health("GET /tools//health HTTP/1.1")
        assert code == 400

    def test_tools_blocked_returns_only_denied(self):
        srv = self._server(tool_router=_stub_tool_router())
        body, code = srv._handle_tools_blocked()
        assert code == 200
        data = json.loads(body)
        assert data["total"] == 1
        assert data["items"][0]["tool_name"] == "admin.delete_tenant"
        assert data["stats"]["denied"] == 1
