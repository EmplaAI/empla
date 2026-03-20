"""Tests for HubSpot CRM connector — mocked HTTP calls."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from empla.integrations.hubspot import tools as hubspot_mod
from empla.integrations.hubspot.tools import router


def _mock_response(json_data: dict, status: int = 200) -> MagicMock:
    """Create a mock httpx Response."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.text = str(json_data)
    resp.raise_for_status = MagicMock()
    if status >= 400:
        request = MagicMock()
        request.url = "https://api.hubapi.com/test"
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status}", request=request, response=resp
        )
    return resp


@pytest.fixture(autouse=True)
async def _init_hubspot() -> AsyncIterator[None]:
    mock_client = AsyncMock()
    hubspot_mod._client = mock_client
    yield
    hubspot_mod._client = None


@pytest.fixture
def client() -> AsyncMock:
    assert hubspot_mod._client is not None
    return hubspot_mod._client


class TestInitialization:
    @pytest.mark.asyncio
    async def test_init_requires_access_token(self) -> None:
        hubspot_mod._client = None
        with pytest.raises(ValueError, match="access_token"):
            await router.initialize({})

    @pytest.mark.asyncio
    async def test_init_creates_client(self) -> None:
        hubspot_mod._client = None
        with patch("empla.integrations.hubspot.tools.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = AsyncMock()
            await router.initialize({"access_token": "test-token"})
            mock_cls.assert_called_once()
            assert hubspot_mod._client is not None


class TestDeals:
    @pytest.mark.asyncio
    async def test_get_pipeline_metrics(self, client: AsyncMock) -> None:
        client.get.return_value = _mock_response(
            {
                "results": [
                    {"id": "1", "properties": {"dealstage": "qualifiedtobuy", "amount": "50000"}},
                    {"id": "2", "properties": {"dealstage": "closedwon", "amount": "30000"}},
                ]
            }
        )
        result = await router.execute_tool("hubspot.get_pipeline_metrics", {})
        assert result["deal_count"] == 1
        assert result["total_value"] == 50000.0

    @pytest.mark.asyncio
    async def test_get_pipeline_metrics_paginates(self, client: AsyncMock) -> None:
        """Metrics should paginate through all deals, not just the first 100."""
        page1 = _mock_response(
            {
                "results": [
                    {"id": "1", "properties": {"dealstage": "qualifiedtobuy", "amount": "40000"}},
                ],
                "paging": {"next": {"after": "cursor1"}},
            }
        )
        page2 = _mock_response(
            {
                "results": [
                    {"id": "2", "properties": {"dealstage": "contractsent", "amount": "60000"}},
                ],
            }
        )
        client.get.side_effect = [page1, page2]

        result = await router.execute_tool("hubspot.get_pipeline_metrics", {})
        assert result["deal_count"] == 2
        assert result["total_value"] == 100000.0
        assert client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_get_deals(self, client: AsyncMock) -> None:
        client.get.return_value = _mock_response(
            {
                "results": [
                    {
                        "id": "1",
                        "properties": {
                            "dealname": "Acme",
                            "dealstage": "qualifiedtobuy",
                            "amount": "50000",
                            "closedate": "2026-04-01",
                        },
                    },
                ]
            }
        )
        deals = await router.execute_tool("hubspot.get_deals", {})
        assert len(deals) == 1
        assert deals[0]["name"] == "Acme"

    @pytest.mark.asyncio
    async def test_get_deals_filtered_uses_search_api(self, client: AsyncMock) -> None:
        client.post.return_value = _mock_response(
            {
                "results": [
                    {
                        "id": "1",
                        "properties": {
                            "dealname": "D1",
                            "dealstage": "contractsent",
                            "amount": "10000",
                        },
                    }
                ]
            }
        )
        await router.execute_tool("hubspot.get_deals", {"stage": "contractsent"})
        client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_deal(self, client: AsyncMock) -> None:
        client.post.return_value = _mock_response({"id": "new-deal-123"})
        deal = await router.execute_tool(
            "hubspot.create_deal", {"name": "New Deal", "amount": 25000}
        )
        assert deal["id"] == "new-deal-123"

    @pytest.mark.asyncio
    async def test_update_deal(self, client: AsyncMock) -> None:
        client.patch.return_value = _mock_response({"id": "deal-1"})
        result = await router.execute_tool(
            "hubspot.update_deal", {"deal_id": "deal-1", "stage": "closedwon"}
        )
        assert result["id"] == "deal-1"
        assert "dealstage" in result["updated"]

    @pytest.mark.asyncio
    async def test_update_deal_no_fields_raises(self) -> None:
        with pytest.raises(ValueError, match="No properties"):
            await router.execute_tool("hubspot.update_deal", {"deal_id": "x"})

    @pytest.mark.asyncio
    async def test_http_error_propagates(self, client: AsyncMock) -> None:
        """API errors (4xx/5xx) should propagate as httpx.HTTPStatusError."""
        client.get.return_value = _mock_response({"message": "Rate limit exceeded"}, status=429)
        with pytest.raises(httpx.HTTPStatusError):
            await router.execute_tool("hubspot.get_deals", {})


class TestContacts:
    @pytest.mark.asyncio
    async def test_get_contacts(self, client: AsyncMock) -> None:
        client.get.return_value = _mock_response(
            {
                "results": [
                    {
                        "id": "1",
                        "properties": {
                            "firstname": "Jane",
                            "lastname": "Doe",
                            "email": "jane@acme.com",
                            "company": "Acme",
                        },
                    },
                ]
            }
        )
        contacts = await router.execute_tool("hubspot.get_contacts", {})
        assert len(contacts) == 1
        assert contacts[0]["name"] == "Jane Doe"

    @pytest.mark.asyncio
    async def test_create_contact(self, client: AsyncMock) -> None:
        client.post.return_value = _mock_response({"id": "new-contact-1"})
        contact = await router.execute_tool(
            "hubspot.create_contact", {"email": "bob@beta.com", "first_name": "Bob"}
        )
        assert contact["id"] == "new-contact-1"

    @pytest.mark.asyncio
    async def test_search_contacts(self, client: AsyncMock) -> None:
        client.post.return_value = _mock_response(
            {
                "results": [
                    {
                        "id": "1",
                        "properties": {
                            "firstname": "Alice",
                            "lastname": "Smith",
                            "email": "alice@acme.com",
                            "company": "Acme",
                        },
                    },
                ]
            }
        )
        results = await router.execute_tool("hubspot.search_contacts", {"query": "acme"})
        assert len(results) == 1
        assert results[0]["name"] == "Alice Smith"
