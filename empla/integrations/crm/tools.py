"""
empla.integrations.crm.tools - CRM Integration Tools

Defines CRM tools using the IntegrationRouter pattern.
Provides deal management, contact management, and pipeline metrics.

The adapter is injected at initialization — swap between HubSpot,
Salesforce, or the in-memory test adapter without changing tool code.

Example:
    >>> from empla.integrations.crm.tools import router
    >>> await router.initialize({"provider": "test"})
    >>> result = await router.execute_tool("crm.get_pipeline_metrics", {})
"""

from empla.integrations.crm.adapter import create_crm_adapter
from empla.integrations.router import IntegrationRouter

router = IntegrationRouter("crm", adapter_factory=create_crm_adapter)


@router.tool()
async def get_pipeline_metrics() -> dict:
    """Get pipeline metrics including coverage ratio, total value, and deal count."""
    return await router.adapter.get_pipeline_metrics()


@router.tool()
async def get_deals(stage: str | None = None, limit: int = 50) -> list[dict]:
    """Get deals, optionally filtered by stage (prospecting, negotiation, won, lost)."""
    return await router.adapter.get_deals(stage=stage, limit=limit)


@router.tool()
async def create_deal(
    name: str,
    value: float,
    stage: str = "prospecting",
    contact_id: str | None = None,
) -> dict:
    """Create a new deal in the pipeline."""
    return await router.adapter.create_deal(
        name=name, value=value, stage=stage, contact_id=contact_id
    )


@router.tool()
async def update_deal(
    deal_id: str,
    stage: str | None = None,
    value: float | None = None,
) -> dict:
    """Update a deal's stage or value."""
    return await router.adapter.update_deal(deal_id=deal_id, stage=stage, value=value)


@router.tool()
async def get_contacts(limit: int = 50) -> list[dict]:
    """Get all contacts."""
    return await router.adapter.get_contacts(limit=limit)


@router.tool()
async def create_contact(
    name: str,
    email: str,
    company: str | None = None,
    phone: str | None = None,
) -> dict:
    """Create a new contact."""
    return await router.adapter.create_contact(name=name, email=email, company=company, phone=phone)


@router.tool()
async def search_contacts(query: str, limit: int = 10) -> list[dict]:
    """Search contacts by name, email, or company."""
    return await router.adapter.search_contacts(query=query, limit=limit)
