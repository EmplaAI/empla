"""
Tests for event-driven triggers (webhooks → wake).

Covers:
- HealthServer POST /wake endpoint
- HealthServer drain_events()
- EmployeeManager.wake_employee()
- Webhook API endpoint
- _check_pending_events in execution loop
- Provider-specific parsers
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

# ============================================================================
# HealthServer Tests
# ============================================================================


class TestHealthServerWake:
    """Tests for the HealthServer POST /wake endpoint."""

    def _make_server(self, wake_callback=None):
        from empla.runner.health import HealthServer

        return HealthServer(
            employee_id=uuid4(),
            port=0,  # Won't bind in these tests
            wake_callback=wake_callback,
        )

    def test_drain_events_empty(self):
        """drain_events returns empty list when no events pending."""
        server = self._make_server()
        assert server.drain_events() == []

    def test_drain_events_clears_queue(self):
        """drain_events returns events and clears the queue."""
        server = self._make_server()
        server._pending_events = [{"provider": "hubspot"}, {"provider": "google"}]

        events = server.drain_events()
        assert len(events) == 2
        assert server.drain_events() == []  # Queue cleared

    def test_drain_events_returns_original_list(self):
        """drain_events returns the actual list, not a copy (for efficiency)."""
        server = self._make_server()
        original = [{"provider": "test"}]
        server._pending_events = original

        result = server.drain_events()
        assert result is original

    @pytest.mark.asyncio
    async def test_wake_endpoint_stores_event(self):
        """POST /wake should store event in pending_events."""
        server = self._make_server()
        await server.start()

        try:
            # Send a wake request
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            event = {"provider": "hubspot", "event_type": "deal.updated"}
            body = json.dumps(event).encode()
            request = (
                f"POST /wake HTTP/1.1\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Content-Type: application/json\r\n"
                f"\r\n"
            ).encode() + body

            writer.write(request)
            await writer.drain()

            # Read response
            response = await asyncio.wait_for(reader.read(4096), timeout=2.0)
            writer.close()
            await writer.wait_closed()

            assert b"200 OK" in response
            assert b"accepted" in response

            # Event should be in pending_events
            events = server.drain_events()
            assert len(events) == 1
            assert events[0]["provider"] == "hubspot"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_wake_endpoint_calls_callback(self):
        """POST /wake should call the wake_callback."""
        callback = Mock()
        server = self._make_server(wake_callback=callback)
        await server.start()

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            body = json.dumps({"provider": "test"}).encode()
            request = (
                f"POST /wake HTTP/1.1\r\nContent-Length: {len(body)}\r\n\r\n"
            ).encode() + body

            writer.write(request)
            await writer.drain()
            await asyncio.wait_for(reader.read(4096), timeout=2.0)
            writer.close()
            await writer.wait_closed()

            callback.assert_called_once()
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_wake_endpoint_invalid_json(self):
        """POST /wake with invalid JSON should return 400."""
        server = self._make_server()
        await server.start()

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            body = b"not json"
            request = (
                f"POST /wake HTTP/1.1\r\nContent-Length: {len(body)}\r\n\r\n"
            ).encode() + body

            writer.write(request)
            await writer.drain()
            response = await asyncio.wait_for(reader.read(4096), timeout=2.0)
            writer.close()
            await writer.wait_closed()

            assert b"400" in response
            assert b"invalid JSON" in response
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_wake_endpoint_empty_body(self):
        """POST /wake with empty body should accept as empty dict."""
        server = self._make_server()
        await server.start()

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            request = b"POST /wake HTTP/1.1\r\nContent-Length: 0\r\n\r\n"

            writer.write(request)
            await writer.drain()
            response = await asyncio.wait_for(reader.read(4096), timeout=2.0)
            writer.close()
            await writer.wait_closed()

            assert b"200 OK" in response
            events = server.drain_events()
            assert len(events) == 1
            assert events[0] == {}
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_wake_endpoint_non_dict_json(self):
        """POST /wake with non-dict JSON (e.g. array) should return 400."""
        server = self._make_server()
        await server.start()

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            body = b"[1, 2, 3]"
            request = (
                f"POST /wake HTTP/1.1\r\nContent-Length: {len(body)}\r\n\r\n"
            ).encode() + body

            writer.write(request)
            await writer.drain()
            response = await asyncio.wait_for(reader.read(4096), timeout=2.0)
            writer.close()
            await writer.wait_closed()

            assert b"400" in response
            assert b"JSON object" in response
            assert server.drain_events() == []
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_queue_overflow_drops_oldest(self):
        """When queue is full, POST /wake should drop oldest and accept new."""
        from empla.runner.health import _MAX_PENDING_EVENTS

        server = self._make_server()
        await server.start()

        try:
            # Fill queue to max
            for i in range(_MAX_PENDING_EVENTS):
                server._pending_events.append({"provider": "fill", "index": i})

            assert len(server._pending_events) == _MAX_PENDING_EVENTS

            # Send one more event via actual endpoint
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            body = json.dumps({"provider": "new", "index": 999}).encode()
            request = (
                f"POST /wake HTTP/1.1\r\nContent-Length: {len(body)}\r\n\r\n"
            ).encode() + body

            writer.write(request)
            await writer.drain()
            response = await asyncio.wait_for(reader.read(4096), timeout=2.0)
            writer.close()
            await writer.wait_closed()

            assert b"200 OK" in response
            # Queue still at max
            assert len(server._pending_events) == _MAX_PENDING_EVENTS
            # Oldest (index=0) was dropped, newest is last
            assert server._pending_events[0]["index"] == 1
            assert server._pending_events[-1]["index"] == 999
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_oversized_payload_returns_400(self):
        """POST /wake with body exceeding max size should return 400."""
        server = self._make_server()
        await server.start()

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            # Claim a very large body
            request = b"POST /wake HTTP/1.1\r\nContent-Length: 999999\r\n\r\n"

            writer.write(request)
            await writer.drain()
            response = await asyncio.wait_for(reader.read(4096), timeout=2.0)
            writer.close()
            await writer.wait_closed()

            assert b"400" in response
            assert server.drain_events() == []
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_health_endpoint_shows_pending_count(self):
        """GET /health should include pending_events count."""
        server = self._make_server()
        server._pending_events = [{"a": 1}, {"b": 2}]
        await server.start()

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            writer.write(b"GET /health HTTP/1.1\r\n\r\n")
            await writer.drain()
            response = await asyncio.wait_for(reader.read(4096), timeout=2.0)
            writer.close()
            await writer.wait_closed()

            assert b'"pending_events": 2' in response
        finally:
            await server.stop()


# ============================================================================
# Execution Loop — _check_pending_events Tests
# ============================================================================


class TestCheckPendingEvents:
    """Tests for _check_pending_events in the execution loop."""

    def _make_loop(self):
        from empla.core.loop.execution import ProactiveExecutionLoop
        from empla.core.loop.models import LoopConfig
        from empla.models.employee import Employee

        employee = Mock(spec=Employee)
        employee.id = uuid4()
        employee.name = "Test"
        employee.status = "active"
        employee.role = "sales_ae"
        employee.tenant_id = uuid4()

        memory = Mock()
        memory.working = Mock()
        memory.working.add_item = AsyncMock()

        loop = ProactiveExecutionLoop(
            employee=employee,
            beliefs=Mock(),
            goals=Mock(),
            intentions=Mock(),
            memory=memory,
            config=LoopConfig(cycle_interval_seconds=1),
        )
        return loop  # noqa: RET504

    @pytest.mark.asyncio
    async def test_no_health_server_is_noop(self):
        """Without health_server set, _check_pending_events does nothing."""
        loop = self._make_loop()
        assert loop._health_server is None
        await loop._check_pending_events()
        loop.memory.working.add_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_injects_events_as_observations(self):
        """Events from health server should be injected as working memory observations."""
        loop = self._make_loop()

        mock_health = Mock()
        mock_health.drain_events.return_value = [
            {
                "provider": "hubspot",
                "event_type": "deal.updated",
                "summary": "Acme Corp deal moved to negotiation",
                "payload": {"objectId": "123"},
                "received_at": "2026-04-05T12:00:00+00:00",
            }
        ]
        loop._health_server = mock_health

        await loop._check_pending_events()

        loop.memory.working.add_item.assert_called_once()
        call_kwargs = loop.memory.working.add_item.call_args.kwargs
        assert call_kwargs["item_type"] == "observation"
        assert call_kwargs["importance"] == 0.9
        assert "EVENT: hubspot deal.updated" in call_kwargs["content"]["description"]
        assert "Acme Corp" in call_kwargs["content"]["description"]
        assert call_kwargs["content"]["subtype"] == "external_event"

    @pytest.mark.asyncio
    async def test_multiple_events(self):
        """Multiple events should all be injected."""
        loop = self._make_loop()

        mock_health = Mock()
        mock_health.drain_events.return_value = [
            {"provider": "hubspot", "event_type": "deal.updated", "summary": ""},
            {
                "provider": "google_calendar",
                "event_type": "event.created",
                "summary": "Meeting added",
            },
        ]
        loop._health_server = mock_health

        await loop._check_pending_events()

        assert loop.memory.working.add_item.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_events_is_noop(self):
        """Empty drain should not add any items."""
        loop = self._make_loop()

        mock_health = Mock()
        mock_health.drain_events.return_value = []
        loop._health_server = mock_health

        await loop._check_pending_events()
        loop.memory.working.add_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_error_gracefully(self):
        """Errors should not crash the loop."""
        loop = self._make_loop()

        mock_health = Mock()
        mock_health.drain_events.side_effect = Exception("oops")
        loop._health_server = mock_health

        await loop._check_pending_events()  # Should not raise

    @pytest.mark.asyncio
    async def test_no_working_memory_is_noop(self):
        """If memory has no working attribute, skip."""
        loop = self._make_loop()
        loop.memory = Mock(spec=[])  # No working attribute

        mock_health = Mock()
        mock_health.drain_events.return_value = [{"provider": "test"}]
        loop._health_server = mock_health

        await loop._check_pending_events()  # Should not raise

    @pytest.mark.asyncio
    async def test_event_without_summary(self):
        """Event without summary should still produce clean description."""
        loop = self._make_loop()

        mock_health = Mock()
        mock_health.drain_events.return_value = [
            {"provider": "hubspot", "event_type": "contact.created"}
        ]
        loop._health_server = mock_health

        await loop._check_pending_events()

        call_kwargs = loop.memory.working.add_item.call_args.kwargs
        desc = call_kwargs["content"]["description"]
        assert desc == "EVENT: hubspot contact.created"
        assert " — " not in desc  # No trailing separator


# ============================================================================
# Provider Parser Tests
# ============================================================================


class TestProviderParsers:
    """Tests for provider-specific webhook payload parsers."""

    def test_hubspot_parser(self):
        from empla.integrations.hubspot.webhook import parse_hubspot_webhook

        event_type, summary = parse_hubspot_webhook(
            [{"subscriptionType": "deal.propertyChange", "objectId": 12345}]
        )
        assert event_type == "deal.propertyChange"
        assert "12345" in summary

    def test_hubspot_parser_empty(self):
        from empla.integrations.hubspot.webhook import parse_hubspot_webhook

        event_type, _summary = parse_hubspot_webhook([])
        assert event_type == "unknown"

    def test_hubspot_parser_dict_payload(self):
        """HubSpot sometimes sends a single dict instead of array."""
        from empla.integrations.hubspot.webhook import parse_hubspot_webhook

        event_type, _summary = parse_hubspot_webhook(
            {"subscriptionType": "contact.creation", "objectId": 99}
        )
        assert event_type == "contact.creation"

    def test_google_parser(self):
        from empla.integrations.google_calendar.webhook import parse_google_webhook

        event_type, _summary = parse_google_webhook(
            {"resourceType": "calendar", "changeType": "updated"}
        )
        assert event_type == "calendar.updated"

    def test_generic_parser(self):
        from empla.integrations.webhooks import _parse_generic

        event_type, summary = _parse_generic(
            {"event_type": "custom.event", "summary": "Something happened"}
        )
        assert event_type == "custom.event"
        assert summary == "Something happened"

    def test_generic_parser_defaults(self):
        from empla.integrations.webhooks import _parse_generic

        event_type, summary = _parse_generic({})
        assert event_type == "unknown"
        assert summary == ""

    def test_registry_lookup(self):
        """get_webhook_parser should return registered parsers or generic fallback."""
        from empla.integrations.webhooks import _parse_generic, get_webhook_parser

        # Registered providers return their parser
        parser = get_webhook_parser("hubspot")
        assert parser is not _parse_generic

        # Unknown provider returns generic fallback
        parser = get_webhook_parser("unknown_provider")
        assert parser is _parse_generic

    def test_list_registered_providers(self):
        """list_registered_providers should include registered integrations."""
        from empla.integrations.webhooks import list_registered_providers

        providers = list_registered_providers()
        assert "hubspot" in providers
        assert "google_calendar" in providers


# ============================================================================
# EmployeeManager.wake_employee Tests
# ============================================================================


class TestWakeEmployee:
    """Tests for EmployeeManager.wake_employee()."""

    def _make_manager(self):
        from empla.services.employee_manager import EmployeeManager

        return EmployeeManager()

    @pytest.mark.asyncio
    async def test_no_port_returns_false(self):
        """wake_employee returns False when employee has no health port."""
        manager = self._make_manager()
        result = await manager.wake_employee(uuid4(), {"provider": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_successful_wake(self):
        """wake_employee should POST to health port and return True."""
        from empla.runner.health import HealthServer

        emp_id = uuid4()
        server = HealthServer(employee_id=emp_id, port=0)
        await server.start()

        try:
            manager = self._make_manager()
            manager._health_ports[emp_id] = server.port

            event = {"provider": "hubspot", "event_type": "deal.updated"}
            result = await manager.wake_employee(emp_id, event)

            assert result is True
            events = server.drain_events()
            assert len(events) == 1
            assert events[0]["provider"] == "hubspot"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_connection_refused_returns_false(self):
        """wake_employee returns False when subprocess is unreachable."""
        import socket

        # Find an ephemeral port that's guaranteed not in use
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            unused_port = s.getsockname()[1]

        manager = self._make_manager()
        emp_id = uuid4()
        manager._health_ports[emp_id] = unused_port

        result = await manager.wake_employee(emp_id, {"provider": "test"})
        assert result is False


# ============================================================================
# Webhook API Endpoint Tests
# ============================================================================


class TestWebhookEndpoint:
    """Tests for the webhook receiver API endpoint."""

    def _make_app(self):
        from empla.api.deps import get_db
        from empla.api.main import create_app

        app = create_app()

        # Override DB dependency with a mock session
        async def mock_get_db():
            yield AsyncMock()

        app.dependency_overrides[get_db] = mock_get_db
        return app

    @pytest.mark.asyncio
    async def test_missing_token_header_returns_422(self):
        """Request without X-Webhook-Token header should get 422."""
        from httpx import ASGITransport, AsyncClient

        app = self._make_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/webhooks/hubspot",
                json={"subscriptionType": "deal.updated"},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self):
        """Request with invalid webhook token should get 401."""
        from httpx import ASGITransport, AsyncClient

        from empla.api.v1.endpoints import webhooks

        app = self._make_app()
        transport = ASGITransport(app=app)

        with patch.object(
            webhooks,
            "_find_tenant_by_webhook_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/webhooks/hubspot",
                    headers={"X-Webhook-Token": "invalid-token"},
                    json={"subscriptionType": "deal.updated"},
                )
            assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_webhook_flow(self):
        """Full flow: valid token → find employees → wake."""
        from httpx import ASGITransport, AsyncClient

        from empla.api.v1.endpoints import webhooks

        tenant_id = uuid4()
        emp_id = uuid4()

        app = self._make_app()
        transport = ASGITransport(app=app)

        with (
            patch.object(
                webhooks,
                "_find_tenant_by_webhook_token",
                new_callable=AsyncMock,
                return_value=tenant_id,
            ),
            patch.object(
                webhooks,
                "_find_employees_for_provider",
                new_callable=AsyncMock,
                return_value=[emp_id],
            ),
            patch("empla.api.v1.endpoints.webhooks.get_employee_manager") as mock_get_mgr,
        ):
            mock_manager = Mock()
            mock_manager.wake_employee = AsyncMock(return_value=True)
            mock_get_mgr.return_value = mock_manager

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/webhooks/hubspot",
                    headers={"X-Webhook-Token": "valid-token"},
                    json=[{"subscriptionType": "deal.updated", "objectId": 123}],
                )

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["employees_notified"] == 1

            # Verify wake was called with correct event structure
            wake_call = mock_manager.wake_employee.call_args
            assert wake_call[0][0] == emp_id
            event_dict = wake_call[0][1]
            assert event_dict["provider"] == "hubspot"

    @pytest.mark.asyncio
    async def test_no_active_employees(self):
        """Valid token but no active employees should return 0 notified."""
        from httpx import ASGITransport, AsyncClient

        from empla.api.v1.endpoints import webhooks

        app = self._make_app()
        transport = ASGITransport(app=app)

        with (
            patch.object(
                webhooks,
                "_find_tenant_by_webhook_token",
                new_callable=AsyncMock,
                return_value=uuid4(),
            ),
            patch.object(
                webhooks,
                "_find_employees_for_provider",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/webhooks/hubspot",
                    headers={"X-Webhook-Token": "valid-token"},
                    json={"subscriptionType": "deal.updated"},
                )

            assert resp.status_code == 200
            assert resp.json()["employees_notified"] == 0

    @pytest.mark.asyncio
    async def test_all_employees_unreachable_returns_503(self):
        """When employees exist but all wake attempts fail, return 503."""
        from httpx import ASGITransport, AsyncClient

        from empla.api.v1.endpoints import webhooks

        app = self._make_app()
        transport = ASGITransport(app=app)

        with (
            patch.object(
                webhooks,
                "_find_tenant_by_webhook_token",
                new_callable=AsyncMock,
                return_value=uuid4(),
            ),
            patch.object(
                webhooks,
                "_find_employees_for_provider",
                new_callable=AsyncMock,
                return_value=[uuid4()],
            ),
            patch("empla.api.v1.endpoints.webhooks.get_employee_manager") as mock_get_mgr,
        ):
            mock_manager = Mock()
            mock_manager.wake_employee = AsyncMock(return_value=False)
            mock_get_mgr.return_value = mock_manager

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/webhooks/hubspot",
                    headers={"X-Webhook-Token": "valid-token"},
                    json={"subscriptionType": "deal.updated"},
                )

            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_partial_wake_failures(self):
        """Some employees unreachable should still report partial success."""
        from httpx import ASGITransport, AsyncClient

        from empla.api.v1.endpoints import webhooks

        emp_ids = [uuid4(), uuid4(), uuid4()]

        app = self._make_app()
        transport = ASGITransport(app=app)

        with (
            patch.object(
                webhooks,
                "_find_tenant_by_webhook_token",
                new_callable=AsyncMock,
                return_value=uuid4(),
            ),
            patch.object(
                webhooks,
                "_find_employees_for_provider",
                new_callable=AsyncMock,
                return_value=emp_ids,
            ),
            patch("empla.api.v1.endpoints.webhooks.get_employee_manager") as mock_get_mgr,
        ):
            mock_manager = Mock()
            # First two succeed, third fails
            mock_manager.wake_employee = AsyncMock(side_effect=[True, True, False])
            mock_get_mgr.return_value = mock_manager

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/webhooks/hubspot",
                    headers={"X-Webhook-Token": "valid-token"},
                    json={"subscriptionType": "deal.updated"},
                )

            assert resp.status_code == 200
            assert resp.json()["employees_notified"] == 2
