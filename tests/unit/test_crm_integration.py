"""Tests for CRM integration tools (native @tool pattern)."""

from collections.abc import AsyncIterator

import pytest

from empla.integrations.crm.tools import router


@pytest.fixture(autouse=True)
async def _init_crm_router() -> AsyncIterator[None]:
    """Initialize CRM router with test adapter for each test."""
    await router.initialize({"provider": "test"})
    yield
    await router.shutdown()


class TestCRMToolRegistration:
    def test_tools_registered(self) -> None:
        tool_names = [t["name"] for t in router._tools]
        assert "crm.get_pipeline_metrics" in tool_names
        assert "crm.get_deals" in tool_names
        assert "crm.create_deal" in tool_names
        assert "crm.update_deal" in tool_names
        assert "crm.get_contacts" in tool_names
        assert "crm.create_contact" in tool_names
        assert "crm.search_contacts" in tool_names

    def test_tool_count(self) -> None:
        assert len(router._tools) == 7


class TestPipelineMetrics:
    @pytest.mark.asyncio
    async def test_empty_pipeline(self) -> None:
        result = await router.execute_tool("crm.get_pipeline_metrics", {})
        assert result["coverage"] == 0.0
        assert result["deal_count"] == 0
        assert result["total_value"] == 0

    @pytest.mark.asyncio
    async def test_pipeline_with_deals(self) -> None:
        await router.execute_tool("crm.create_deal", {"name": "Acme", "value": 50000})
        await router.execute_tool("crm.create_deal", {"name": "Beta", "value": 30000})
        result = await router.execute_tool("crm.get_pipeline_metrics", {})
        assert result["coverage"] == 0.8  # 80k / 100k
        assert result["deal_count"] == 2
        assert result["total_value"] == 80000


class TestDeals:
    @pytest.mark.asyncio
    async def test_create_and_get_deal(self) -> None:
        deal = await router.execute_tool("crm.create_deal", {"name": "Test Deal", "value": 25000})
        assert deal["name"] == "Test Deal"
        assert deal["value"] == 25000
        assert deal["stage"] == "prospecting"
        assert "id" in deal

    @pytest.mark.asyncio
    async def test_filter_deals_by_stage(self) -> None:
        await router.execute_tool(
            "crm.create_deal", {"name": "D1", "value": 10000, "stage": "prospecting"}
        )
        await router.execute_tool(
            "crm.create_deal", {"name": "D2", "value": 20000, "stage": "negotiation"}
        )

        prospecting = await router.execute_tool("crm.get_deals", {"stage": "prospecting"})
        assert len(prospecting) == 1
        assert prospecting[0]["name"] == "D1"

    @pytest.mark.asyncio
    async def test_update_deal_stage(self) -> None:
        deal = await router.execute_tool("crm.create_deal", {"name": "D1", "value": 10000})
        updated = await router.execute_tool(
            "crm.update_deal", {"deal_id": deal["id"], "stage": "won"}
        )
        assert updated["stage"] == "won"

    @pytest.mark.asyncio
    async def test_update_nonexistent_deal(self) -> None:
        with pytest.raises(KeyError, match="not found"):
            await router.execute_tool("crm.update_deal", {"deal_id": "nonexistent"})

    @pytest.mark.asyncio
    async def test_update_deal_value(self) -> None:
        deal = await router.execute_tool("crm.create_deal", {"name": "D1", "value": 10000})
        updated = await router.execute_tool(
            "crm.update_deal", {"deal_id": deal["id"], "value": 25000}
        )
        assert updated["value"] == 25000

    @pytest.mark.asyncio
    async def test_won_deals_excluded_from_pipeline(self) -> None:
        """Won/lost deals should not count toward pipeline coverage."""
        await router.execute_tool("crm.create_deal", {"name": "Active", "value": 50000})
        won_deal = await router.execute_tool("crm.create_deal", {"name": "Won", "value": 30000})
        await router.execute_tool("crm.update_deal", {"deal_id": won_deal["id"], "stage": "won"})

        metrics = await router.execute_tool("crm.get_pipeline_metrics", {})
        assert metrics["deal_count"] == 1  # Only active deal
        assert metrics["total_value"] == 50000  # Won deal excluded


class TestContacts:
    @pytest.mark.asyncio
    async def test_create_and_get_contact(self) -> None:
        contact = await router.execute_tool(
            "crm.create_contact",
            {"name": "Jane Doe", "email": "jane@acme.com", "company": "Acme"},
        )
        assert contact["name"] == "Jane Doe"
        assert contact["email"] == "jane@acme.com"

        contacts = await router.execute_tool("crm.get_contacts", {})
        assert len(contacts) == 1

    @pytest.mark.asyncio
    async def test_search_contacts(self) -> None:
        await router.execute_tool(
            "crm.create_contact", {"name": "Alice", "email": "alice@acme.com", "company": "Acme"}
        )
        await router.execute_tool(
            "crm.create_contact", {"name": "Bob", "email": "bob@beta.com", "company": "Beta"}
        )

        results = await router.execute_tool("crm.search_contacts", {"query": "acme"})
        assert len(results) == 1
        assert results[0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_search_no_results(self) -> None:
        results = await router.execute_tool("crm.search_contacts", {"query": "nonexistent"})
        assert len(results) == 0
