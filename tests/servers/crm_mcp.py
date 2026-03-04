"""
CRM MCP Server - In-memory CRM for E2E testing.

Implements MCP tools for CRM operations (deals, contacts, pipeline metrics).

Usage:
    python -m tests.servers.crm_mcp --http --port 9102
"""

import argparse
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# In-memory state
deals: dict[str, dict[str, Any]] = {}
contacts: dict[str, dict[str, Any]] = {}


def _reset() -> None:
    deals.clear()
    contacts.clear()


def get_pipeline_metrics() -> dict[str, Any]:
    """Get pipeline metrics (coverage, total value, deal count)."""
    active_deals = [d for d in deals.values() if d["stage"] not in ("won", "lost")]
    total_value = sum(d["value"] for d in active_deals)
    # Pipeline coverage = total pipeline / quarterly target (assume $100k target)
    quarterly_target = 100000.0
    coverage = total_value / quarterly_target if quarterly_target > 0 else 0.0
    return {
        "coverage": round(coverage, 2),
        "total_value": total_value,
        "deal_count": len(active_deals),
        "quarterly_target": quarterly_target,
        "stages": _stage_breakdown(),
    }


def _stage_breakdown() -> dict[str, int]:
    breakdown: dict[str, int] = {}
    for d in deals.values():
        breakdown[d["stage"]] = breakdown.get(d["stage"], 0) + 1
    return breakdown


def get_deals(stage: str | None = None) -> list[dict[str, Any]]:
    """Get deals, optionally filtered by stage."""
    if stage:
        return [d for d in deals.values() if d["stage"] == stage]
    return list(deals.values())


def create_deal(
    name: str,
    value: float,
    stage: str = "prospecting",
    contact_id: str | None = None,
) -> dict[str, Any]:
    """Create a new deal."""
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
    deals[deal_id] = deal
    return deal


def update_deal(
    deal_id: str,
    stage: str | None = None,
    value: float | None = None,
) -> dict[str, Any]:
    """Update a deal's stage or value."""
    if deal_id not in deals:
        raise ValueError(f"Deal {deal_id} not found")
    deal = deals[deal_id]
    if stage is not None:
        deal["stage"] = stage
    if value is not None:
        deal["value"] = value
    deal["updated_at"] = datetime.now(UTC).isoformat()
    return deal


def get_contacts() -> list[dict[str, Any]]:
    """Get all contacts."""
    return list(contacts.values())


def add_contact(
    name: str,
    email: str,
    company: str | None = None,
) -> dict[str, Any]:
    """Add a new contact."""
    contact_id = str(uuid4())
    contact = {
        "id": contact_id,
        "name": name,
        "email": email,
        "company": company,
        "created_at": datetime.now(UTC).isoformat(),
    }
    contacts[contact_id] = contact
    return contact


def get_at_risk_customers() -> list[dict[str, Any]]:
    """Get at-risk customers (deals in late stages with low activity)."""
    at_risk = []
    for deal in deals.values():
        if deal["stage"] in ("negotiation", "proposal") and deal["value"] > 10000:
            at_risk.append(
                {
                    "deal_id": deal["id"],
                    "name": deal["name"],
                    "value": deal["value"],
                    "stage": deal["stage"],
                    "risk_reason": "High-value deal in late stage",
                }
            )
    return at_risk


# MCP tool definitions
TOOLS = [
    {
        "name": "get_pipeline_metrics",
        "description": "Get CRM pipeline metrics including coverage ratio, total value, and deal count.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_deals",
        "description": "Get all deals, optionally filtered by stage (prospecting, qualification, proposal, negotiation, won, lost).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stage": {"type": "string", "description": "Filter by deal stage"},
            },
        },
    },
    {
        "name": "create_deal",
        "description": "Create a new deal in the CRM.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Deal name"},
                "value": {"type": "number", "description": "Deal value in dollars"},
                "stage": {"type": "string", "default": "prospecting", "description": "Deal stage"},
                "contact_id": {"type": "string", "description": "Associated contact ID"},
            },
            "required": ["name", "value"],
        },
    },
    {
        "name": "update_deal",
        "description": "Update a deal's stage or value.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string", "description": "Deal ID to update"},
                "stage": {"type": "string", "description": "New stage"},
                "value": {"type": "number", "description": "New value"},
            },
            "required": ["deal_id"],
        },
    },
    {
        "name": "get_contacts",
        "description": "Get all contacts in the CRM.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_contact",
        "description": "Add a new contact to the CRM.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Contact name"},
                "email": {"type": "string", "description": "Contact email"},
                "company": {"type": "string", "description": "Company name"},
            },
            "required": ["name", "email"],
        },
    },
    {
        "name": "get_at_risk_customers",
        "description": "Get customers/deals at risk of churning or stalling.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def handle_tool_call(name: str, arguments: dict[str, Any]) -> Any:
    """Route MCP tool call to implementation."""
    handlers = {
        "get_pipeline_metrics": lambda args: get_pipeline_metrics(),
        "get_deals": lambda args: get_deals(stage=args.get("stage")),
        "create_deal": lambda args: create_deal(
            name=args["name"],
            value=args["value"],
            stage=args.get("stage", "prospecting"),
            contact_id=args.get("contact_id"),
        ),
        "update_deal": lambda args: update_deal(
            deal_id=args["deal_id"],
            stage=args.get("stage"),
            value=args.get("value"),
        ),
        "get_contacts": lambda args: get_contacts(),
        "add_contact": lambda args: add_contact(
            name=args["name"],
            email=args["email"],
            company=args.get("company"),
        ),
        "get_at_risk_customers": lambda args: get_at_risk_customers(),
    }
    handler = handlers.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")
    return handler(arguments)


# ============================================================================
# HTTP transport
# ============================================================================


def create_http_app() -> Any:
    """Create FastAPI app with MCP-compatible endpoints."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    mcp_app = FastAPI(title="empla Test CRM MCP")

    @mcp_app.get("/tools")
    async def list_tools() -> JSONResponse:
        return JSONResponse(content=TOOLS)

    @mcp_app.post("/tools/{tool_name}")
    async def call_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> JSONResponse:
        result = handle_tool_call(tool_name, arguments or {})
        return JSONResponse(content={"result": result})

    @mcp_app.post("/reset")
    async def reset() -> JSONResponse:
        _reset()
        return JSONResponse(content={"status": "reset"})

    @mcp_app.post("/scenario/load")
    async def load_scenario(data: dict[str, Any]) -> JSONResponse:
        for deal_data in data.get("deals", []):
            if "id" not in deal_data:
                deal_data["id"] = str(uuid4())
            deals[deal_data["id"]] = deal_data
        for contact_data in data.get("contacts", []):
            if "id" not in contact_data:
                contact_data["id"] = str(uuid4())
            contacts[contact_data["id"]] = contact_data
        return JSONResponse(
            content={
                "loaded_deals": len(data.get("deals", [])),
                "loaded_contacts": len(data.get("contacts", [])),
            }
        )

    @mcp_app.get("/state")
    async def get_state() -> JSONResponse:
        return JSONResponse(
            content={
                "deals": list(deals.values()),
                "contacts": list(contacts.values()),
                "metrics": get_pipeline_metrics(),
            }
        )

    return mcp_app


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="empla Test CRM MCP Server")
    parser.add_argument("--http", action="store_true", help="Run as HTTP server")
    parser.add_argument("--port", type=int, default=9102)
    args = parser.parse_args()

    if args.http:
        app = create_http_app()
        uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")
    else:
        import sys

        for line in sys.stdin:
            try:
                msg = json.loads(line.strip())
                if msg.get("method") == "tools/list":
                    result = {"tools": TOOLS}
                elif msg.get("method") == "tools/call":
                    params = msg.get("params", {})
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    handle_tool_call(params["name"], params.get("arguments", {}))
                                ),
                            }
                        ]
                    }
                else:
                    result = {}
                response = {"jsonrpc": "2.0", "id": msg.get("id"), "result": result}
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            except Exception as e:
                sys.stderr.write(f"Error: {e}\n")
