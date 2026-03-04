"""
Test Email Server - In-memory REST API for E2E testing.

Simple FastAPI app that simulates an email server.
Stores all state in memory for fast, deterministic testing.

Usage:
    python -m tests.servers.email_server [--port 9100]

API:
    GET  /emails             List emails (?unread=true, ?max_results=10)
    GET  /emails/{id}        Get single email
    POST /emails/send        Send email → stored in sent[]
    POST /emails/{id}/reply  Reply to email
    PATCH /emails/{id}       Mark read/archive
    POST /scenario/load      Pre-populate with test data
    GET  /state              Full state snapshot (for assertions)
    POST /reset              Clear all state
"""

import argparse
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="empla Test Email Server")


# ============================================================================
# Models
# ============================================================================


class EmailMessage(BaseModel):
    id: str
    thread_id: str | None = None
    from_addr: str
    to_addrs: list[str]
    cc_addrs: list[str] = []
    subject: str
    body: str
    timestamp: str
    is_read: bool = False
    is_archived: bool = False
    in_reply_to: str | None = None
    labels: list[str] = []


class SendRequest(BaseModel):
    to: list[str]
    subject: str
    body: str
    cc: list[str] | None = None
    from_addr: str = "employee@test.empla.ai"


class ReplyRequest(BaseModel):
    body: str
    cc: list[str] | None = None
    from_addr: str = "employee@test.empla.ai"


class PatchRequest(BaseModel):
    is_read: bool | None = None
    is_archived: bool | None = None


class ScenarioRequest(BaseModel):
    emails: list[dict[str, Any]]


# ============================================================================
# In-memory state
# ============================================================================


class EmailStore:
    def __init__(self) -> None:
        self.inbox: dict[str, EmailMessage] = {}
        self.sent: list[EmailMessage] = []

    def reset(self) -> None:
        self.inbox.clear()
        self.sent.clear()

    def add_email(self, email: EmailMessage) -> None:
        self.inbox[email.id] = email

    def get_state(self) -> dict[str, Any]:
        return {
            "inbox": [e.model_dump() for e in self.inbox.values()],
            "sent": [e.model_dump() for e in self.sent],
            "inbox_count": len(self.inbox),
            "sent_count": len(self.sent),
            "unread_count": sum(1 for e in self.inbox.values() if not e.is_read),
        }


store = EmailStore()


# ============================================================================
# Endpoints
# ============================================================================


@app.get("/emails")
async def list_emails(
    unread: bool = False,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """List emails, optionally filtering by unread status."""
    emails = list(store.inbox.values())
    if unread:
        emails = [e for e in emails if not e.is_read]
    emails.sort(key=lambda e: e.timestamp, reverse=True)
    return [e.model_dump() for e in emails[:max_results]]


@app.get("/emails/{email_id}")
async def get_email(email_id: str) -> dict[str, Any]:
    """Get a single email by ID."""
    if email_id not in store.inbox:
        raise HTTPException(status_code=404, detail=f"Email {email_id} not found")
    return store.inbox[email_id].model_dump()


@app.post("/emails/send")
async def send_email(request: SendRequest) -> dict[str, Any]:
    """Send an email (stored in sent list)."""
    msg = EmailMessage(
        id=str(uuid4()),
        from_addr=request.from_addr,
        to_addrs=request.to,
        cc_addrs=request.cc or [],
        subject=request.subject,
        body=request.body,
        timestamp=datetime.now(UTC).isoformat(),
        is_read=True,
    )
    store.sent.append(msg)
    return {"success": True, "message_id": msg.id}


@app.post("/emails/{email_id}/reply")
async def reply_to_email(email_id: str, request: ReplyRequest) -> dict[str, Any]:
    """Reply to an existing email."""
    if email_id not in store.inbox:
        raise HTTPException(status_code=404, detail=f"Email {email_id} not found")

    original = store.inbox[email_id]
    reply = EmailMessage(
        id=str(uuid4()),
        thread_id=original.thread_id or original.id,
        from_addr=request.from_addr,
        to_addrs=[original.from_addr],
        cc_addrs=request.cc or [],
        subject=f"Re: {original.subject}",
        body=request.body,
        timestamp=datetime.now(UTC).isoformat(),
        is_read=True,
        in_reply_to=email_id,
    )
    store.sent.append(reply)
    return {"success": True, "message_id": reply.id}


@app.patch("/emails/{email_id}")
async def patch_email(email_id: str, request: PatchRequest) -> dict[str, Any]:
    """Update email flags (read, archived)."""
    if email_id not in store.inbox:
        raise HTTPException(status_code=404, detail=f"Email {email_id} not found")

    email = store.inbox[email_id]
    if request.is_read is not None:
        email.is_read = request.is_read
    if request.is_archived is not None:
        email.is_archived = request.is_archived
    return {"success": True}


@app.post("/scenario/load")
async def load_scenario(request: ScenarioRequest) -> dict[str, Any]:
    """Pre-populate with test data."""
    for email_data in request.emails:
        if "id" not in email_data:
            email_data["id"] = str(uuid4())
        if "timestamp" not in email_data:
            email_data["timestamp"] = datetime.now(UTC).isoformat()
        email = EmailMessage(**email_data)
        store.add_email(email)
    return {"loaded": len(request.emails)}


@app.get("/state")
async def get_state() -> dict[str, Any]:
    """Full state snapshot for test assertions."""
    return store.get_state()


@app.post("/reset")
async def reset_state() -> dict[str, str]:
    """Clear all state."""
    store.reset()
    return {"status": "reset"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="empla Test Email Server")
    parser.add_argument("--port", type=int, default=9100)
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")
