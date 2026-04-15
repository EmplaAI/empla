"""
empla.integrations.hubspot.tools - HubSpot CRM Tools

Direct HubSpot API v3 integration via httpx. OAuth token from config at init.

API docs: https://developers.hubspot.com/docs/api/crm

Example:
    >>> from empla.integrations.hubspot.tools import router
    >>> await router.initialize({"access_token": "pat-xxx"})
    >>> metrics = await router.execute_tool("hubspot.get_pipeline_metrics", {})
"""

import logging
from typing import Any
from urllib.parse import quote

import httpx

from empla.integrations.router import IntegrationRouter

logger = logging.getLogger(__name__)

HUBSPOT_API = "https://api.hubapi.com"

# Module-level state set during initialize().
# NOTE: Single-tenant per process. Multi-tenant requires separate worker processes
# per employee (which is the current runner architecture — one process per employee).
_client: httpx.AsyncClient | None = None

# PR #83: Quarterly target read from Tenant.settings.sales.quarterly_target_usd
# at _hubspot_init time, via a ``tenant_settings`` key in the init config.
# NOTE: The runner doesn't currently invoke ``IntegrationRouter.initialize``
# for in-process integrations (only MCP servers are wired end-to-end today).
# The read path below is correct; when a future PR wires
# ``tool_router.initialize_integrations({"hubspot": {"access_token": ...,
# "tenant_settings": tenant.settings}})`` at runner startup, the value flows
# through without further changes. Until then, ``_quarterly_target`` stays
# at the 100k default in production. The hardcoded literal in
# ``get_pipeline_metrics`` is gone either way — that's the real TODO
# retired here.
_quarterly_target: float = 100_000.0


def _api() -> httpx.AsyncClient:
    """Get the initialized HTTP client. Raises if not initialized."""
    if _client is None:
        raise RuntimeError("HubSpot integration not initialized. Call router.initialize() first.")
    return _client


async def _call(method: str, path: str, operation: str, **kwargs: Any) -> dict[str, Any]:
    """Make an API call with error handling, logging, and context wrapping.

    All HubSpot tool functions should use this instead of calling _api() directly.
    Catches httpx exceptions and wraps them with integration context.
    """
    logger.debug("hubspot.%s: %s %s", operation, method.upper(), path)
    try:
        client = _api()
        resp = await getattr(client, method)(path, **kwargs)
        if resp.status_code >= 400:
            # Log status + path only — response body may contain PII
            logger.error(
                "HubSpot API error in %s: %s %s",
                operation,
                resp.status_code,
                path,
                extra={"operation": operation, "status": resp.status_code},
            )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError:
        raise  # Already logged above, let ToolRouter handle
    except httpx.TimeoutException as e:
        logger.error("HubSpot timeout in %s: %s", operation, e, extra={"operation": operation})
        raise
    except httpx.ConnectError as e:
        logger.error("HubSpot unreachable in %s: %s", operation, e, extra={"operation": operation})
        raise
    except Exception as e:
        logger.error("HubSpot unexpected error in %s: %s", operation, e, exc_info=True)
        raise


async def _hubspot_init(**config: Any) -> None:
    global _client, _quarterly_target  # noqa: PLW0603
    # Close previous client if re-initializing (e.g., token refresh)
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            logger.debug("Previous HubSpot client close failed (may already be closed)")
    token = config.get("access_token")
    if not token:
        raise ValueError("HubSpot requires 'access_token' in config")
    _client = httpx.AsyncClient(
        base_url=HUBSPOT_API,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30.0,
    )

    # PR #83: pick up quarterly target from tenant settings if provided.
    # Runner passes ``tenant_settings`` through config at spawn time. Falls
    # back to the historical 100k default when the setting is blank.
    tenant_settings = config.get("tenant_settings") or {}
    sales_section = tenant_settings.get("sales") or {}
    candidate = sales_section.get("quarterly_target_usd")
    # bool is a subclass of int — exclude it so a stray True/False doesn't
    # silently coerce to 1.0/0.0 and override the default.
    if isinstance(candidate, int | float) and not isinstance(candidate, bool) and candidate >= 0:
        _quarterly_target = float(candidate)
    else:
        _quarterly_target = 100_000.0
    logger.info("HubSpot connector initialized (quarterly_target=%.0f)", _quarterly_target)


async def _hubspot_shutdown() -> None:
    global _client  # noqa: PLW0603
    if _client:
        try:
            await _client.aclose()
        except Exception:
            logger.debug("HubSpot client close failed during shutdown")
        finally:
            _client = None
        logger.info("HubSpot connector shut down")


router = IntegrationRouter("hubspot", on_init=_hubspot_init, on_shutdown=_hubspot_shutdown)


def _format_contact(c: dict[str, Any]) -> dict[str, Any]:
    """Format a HubSpot contact response into a consistent dict."""
    props = c.get("properties", {})
    return {
        "id": c["id"],
        "name": f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
        "email": props.get("email", ""),
        "company": props.get("company", ""),
    }


# ============================================================================
# Deals
# ============================================================================


@router.tool()
async def get_pipeline_metrics() -> dict[str, Any]:
    """Get pipeline metrics: total deals, total value, coverage ratio.

    Paginates through all deals (up to 1000) to ensure accurate metrics.
    """
    deals: list[dict] = []
    after: str | None = None
    for _ in range(10):  # Max 10 pages x 100 = 1000 deals
        params: dict[str, Any] = {"limit": 100}
        if after:
            params["after"] = after
        data = await _call("get", "/crm/v3/objects/deals", "get_pipeline_metrics", params=params)
        deals.extend(data.get("results", []))
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break

    active_stages = {
        "appointmentscheduled",
        "qualifiedtobuy",
        "presentationscheduled",
        "decisionmakerboughtin",
        "contractsent",
    }
    active = [d for d in deals if d.get("properties", {}).get("dealstage") in active_stages]
    total_value = sum(float(d.get("properties", {}).get("amount") or 0) for d in active)
    # Read from module-level state set by _hubspot_init from tenant settings.
    quarterly_target = _quarterly_target

    return {
        "coverage": round(total_value / quarterly_target, 2) if quarterly_target else 0.0,
        "total_value": total_value,
        "deal_count": len(active),
        "total_deals": len(deals),
        "quarterly_target": quarterly_target,
    }


@router.tool()
async def get_deals(stage: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Get deals from HubSpot, optionally filtered by stage."""
    if stage:
        body = {
            "filterGroups": [
                {"filters": [{"propertyName": "dealstage", "operator": "EQ", "value": stage}]}
            ],
            "limit": min(limit, 100),
        }
        data = await _call("post", "/crm/v3/objects/deals/search", "get_deals", json=body)
    else:
        data = await _call(
            "get", "/crm/v3/objects/deals", "get_deals", params={"limit": min(limit, 100)}
        )

    return [
        {
            "id": d["id"],
            "name": d.get("properties", {}).get("dealname", ""),
            "stage": d.get("properties", {}).get("dealstage", ""),
            "amount": float(d.get("properties", {}).get("amount") or 0),
            "close_date": d.get("properties", {}).get("closedate"),
        }
        for d in data.get("results", [])
    ]


@router.tool()
async def create_deal(
    name: str, amount: float, stage: str = "appointmentscheduled"
) -> dict[str, Any]:
    """Create a new deal in HubSpot."""
    data = await _call(
        "post",
        "/crm/v3/objects/deals",
        "create_deal",
        json={"properties": {"dealname": name, "amount": str(amount), "dealstage": stage}},
    )
    return {"id": data["id"], "name": name, "amount": amount, "stage": stage}


@router.tool()
async def update_deal(
    deal_id: str, stage: str | None = None, amount: float | None = None
) -> dict[str, Any]:
    """Update a deal's stage or amount."""
    props: dict[str, str] = {}
    if stage is not None:
        props["dealstage"] = stage
    if amount is not None:
        props["amount"] = str(amount)
    if not props:
        raise ValueError("No properties to update")

    safe_id = quote(deal_id, safe="")
    await _call(
        "patch",
        f"/crm/v3/objects/deals/{safe_id}",
        "update_deal",
        json={"properties": props},
    )
    return {"id": deal_id, "updated": list(props.keys())}


# ============================================================================
# Contacts
# ============================================================================


@router.tool()
async def get_contacts(limit: int = 50) -> list[dict[str, Any]]:
    """Get contacts from HubSpot."""
    data = await _call(
        "get", "/crm/v3/objects/contacts", "get_contacts", params={"limit": min(limit, 100)}
    )
    return [_format_contact(c) for c in data.get("results", [])]


@router.tool()
async def create_contact(
    email: str, first_name: str = "", last_name: str = "", company: str = ""
) -> dict[str, Any]:
    """Create a new contact in HubSpot."""
    props = {"email": email}
    if first_name:
        props["firstname"] = first_name
    if last_name:
        props["lastname"] = last_name
    if company:
        props["company"] = company

    data = await _call(
        "post", "/crm/v3/objects/contacts", "create_contact", json={"properties": props}
    )
    return {"id": data["id"], "email": email}


@router.tool()
async def search_contacts(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search contacts by name, email, or company."""
    data = await _call(
        "post",
        "/crm/v3/objects/contacts/search",
        "search_contacts",
        json={"query": query, "limit": min(limit, 100)},
    )
    return [_format_contact(c) for c in data.get("results", [])]
