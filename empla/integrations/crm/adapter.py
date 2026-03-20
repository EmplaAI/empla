"""
empla.integrations.crm.adapter - CRM Adapter Layer

Abstracts CRM provider differences behind a common interface.
Swap providers by changing the config — tool code stays the same.

Supported providers:
- "test" — In-memory CRM for development and testing
- "hubspot" — HubSpot CRM (future, requires OAuth)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

logger = logging.getLogger(__name__)


class CRMAdapter(Protocol):
    """Protocol for CRM adapters."""

    async def get_pipeline_metrics(self) -> dict[str, Any]: ...
    async def get_deals(
        self, stage: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]: ...
    async def create_deal(
        self, name: str, value: float, stage: str = "prospecting", contact_id: str | None = None
    ) -> dict[str, Any]: ...
    async def update_deal(
        self, deal_id: str, stage: str | None = None, value: float | None = None
    ) -> dict[str, Any]: ...
    async def get_contacts(self, limit: int = 50) -> list[dict[str, Any]]: ...
    async def create_contact(
        self, name: str, email: str, company: str | None = None, phone: str | None = None
    ) -> dict[str, Any]: ...
    async def search_contacts(self, query: str, limit: int = 10) -> list[dict[str, Any]]: ...
    async def shutdown(self) -> None: ...


class InMemoryCRMAdapter:
    """In-memory CRM for development and testing."""

    def __init__(self) -> None:
        self._deals: dict[str, dict[str, Any]] = {}
        self._contacts: dict[str, dict[str, Any]] = {}

    async def get_pipeline_metrics(self) -> dict[str, Any]:
        active = [d for d in self._deals.values() if d["stage"] not in ("won", "lost")]
        total_value = sum(d["value"] for d in active)
        quarterly_target = 100_000.0
        coverage = round(total_value / quarterly_target, 2) if quarterly_target else 0.0
        return {
            "coverage": coverage,
            "total_value": total_value,
            "deal_count": len(active),
            "quarterly_target": quarterly_target,
            "stages": self._stage_breakdown(),
        }

    def _stage_breakdown(self) -> dict[str, int]:
        breakdown: dict[str, int] = {}
        for d in self._deals.values():
            breakdown[d["stage"]] = breakdown.get(d["stage"], 0) + 1
        return breakdown

    async def get_deals(self, stage: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        deals = list(self._deals.values())
        if stage:
            deals = [d for d in deals if d["stage"] == stage]
        return deals[:limit]

    async def create_deal(
        self, name: str, value: float, stage: str = "prospecting", contact_id: str | None = None
    ) -> dict[str, Any]:
        deal_id = str(uuid4())
        deal = {
            "id": deal_id,
            "name": name,
            "value": value,
            "stage": stage,
            "contact_id": contact_id,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._deals[deal_id] = deal
        return deal

    async def update_deal(
        self, deal_id: str, stage: str | None = None, value: float | None = None
    ) -> dict[str, Any]:
        if deal_id not in self._deals:
            raise KeyError(f"Deal {deal_id} not found")
        deal = self._deals[deal_id]
        if stage is not None:
            deal["stage"] = stage
        if value is not None:
            deal["value"] = value
        deal["updated_at"] = datetime.now(UTC).isoformat()
        return deal

    async def get_contacts(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._contacts.values())[:limit]

    async def create_contact(
        self, name: str, email: str, company: str | None = None, phone: str | None = None
    ) -> dict[str, Any]:
        contact_id = str(uuid4())
        contact = {
            "id": contact_id,
            "name": name,
            "email": email,
            "company": company,
            "phone": phone,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._contacts[contact_id] = contact
        return contact

    async def search_contacts(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        q = query.lower()
        matches = [
            c
            for c in self._contacts.values()
            if q in c.get("name", "").lower()
            or q in c.get("email", "").lower()
            or q in (c.get("company") or "").lower()
        ]
        return matches[:limit]

    async def shutdown(self) -> None:
        pass


def create_crm_adapter(**config: Any) -> CRMAdapter:
    """Factory for CRM adapters based on config."""
    provider = config.get("provider", "test")
    if provider == "test":
        return InMemoryCRMAdapter()
    # Future: HubSpot, Salesforce adapters
    raise ValueError(f"Unknown CRM provider: '{provider}'. Supported: 'test'")
