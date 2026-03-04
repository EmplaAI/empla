"""
Test email adapter that talks to the test email server.

For E2E testing — implements EmailAdapter by hitting the in-memory
test email server via httpx.

Example:
    >>> adapter = TestEmailAdapter("bot@test.empla.ai", base_url="http://localhost:9100")
    >>> await adapter.initialize({})
    >>> emails = await adapter.fetch_emails(unread_only=True)
"""

import logging
from datetime import datetime
from typing import Any

import httpx

from empla.integrations.base import AdapterResult
from empla.integrations.email.base import EmailAdapter
from empla.integrations.email.types import Email

logger = logging.getLogger(__name__)


class TestEmailAdapter(EmailAdapter):
    """Email adapter backed by the test email server.

    Args:
        email_address: Sender email address (From header).
        base_url: URL of the test email server.
    """

    def __init__(
        self,
        email_address: str,
        base_url: str = "http://localhost:9100",
    ) -> None:
        self._email_address = email_address
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def initialize(self, credentials: dict[str, Any]) -> None:
        """Initialize HTTP client (no real auth needed for test server)."""
        if self._client is not None:
            await self._client.aclose()
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("TestEmailAdapter not initialized — call initialize() first")
        return self._client

    async def fetch_emails(
        self,
        *,
        unread_only: bool = True,
        since: datetime | None = None,
        max_results: int = 50,
    ) -> list[Email]:
        """Fetch emails from test server."""
        params: dict[str, Any] = {"max_results": max_results}
        if unread_only:
            params["unread"] = "true"
        if since is not None:
            params["since"] = since.isoformat()

        resp = await self.client.get("/emails", params=params)
        resp.raise_for_status()
        data = resp.json()

        return [
            Email(
                id=e["id"],
                thread_id=e.get("thread_id"),
                from_addr=e["from_addr"],
                to_addrs=e.get("to_addrs", []),
                cc_addrs=e.get("cc_addrs", []),
                subject=e.get("subject", ""),
                body=e.get("body", ""),
                html_body=e.get("html_body"),
                timestamp=datetime.fromisoformat(e["timestamp"]),
                is_read=e.get("is_read", False),
            )
            for e in data
        ]

    async def fetch_message(self, message_id: str) -> Email | None:
        """Fetch a single email by ID."""
        resp = await self.client.get(f"/emails/{message_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        e = resp.json()
        return Email(
            id=e["id"],
            thread_id=e.get("thread_id"),
            from_addr=e["from_addr"],
            to_addrs=e.get("to_addrs", []),
            cc_addrs=e.get("cc_addrs", []),
            subject=e.get("subject", ""),
            body=e.get("body", ""),
            timestamp=datetime.fromisoformat(e["timestamp"]),
            is_read=e.get("is_read", False),
        )

    async def send(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
    ) -> AdapterResult:
        """Send email via test server."""
        payload = {
            "to": to,
            "subject": subject,
            "body": body,
            "cc": cc,
            "from_addr": self._email_address,
        }
        resp = await self.client.post("/emails/send", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return AdapterResult(success=True, data={"message_id": data["message_id"]})

    async def reply(
        self,
        message_id: str,
        body: str,
        cc: list[str] | None = None,
    ) -> AdapterResult:
        """Reply to email via test server."""
        payload = {"body": body, "cc": cc, "from_addr": self._email_address}
        resp = await self.client.post(f"/emails/{message_id}/reply", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return AdapterResult(success=True, data={"message_id": data["message_id"]})

    async def forward(
        self,
        message_id: str,
        to: list[str],
        body: str | None = None,
    ) -> AdapterResult:
        """Forward not yet implemented in test server — send as new email."""
        email = await self.fetch_message(message_id)
        if not email:
            return AdapterResult(success=False, data={}, error=f"Email {message_id} not found")
        fwd_subject = f"Fwd: {email.subject}"
        fwd_body = f"{body or ''}\n\n--- Forwarded ---\n{email.body}"
        return await self.send(to, fwd_subject, fwd_body)

    async def mark_read(self, message_id: str) -> AdapterResult:
        """Mark email as read."""
        resp = await self.client.patch(f"/emails/{message_id}", json={"is_read": True})
        if resp.status_code == 404:
            return AdapterResult(success=False, data={}, error=f"Email {message_id} not found")
        resp.raise_for_status()
        return AdapterResult(success=True, data={})

    async def archive(self, message_id: str) -> AdapterResult:
        """Archive email."""
        resp = await self.client.patch(f"/emails/{message_id}", json={"is_archived": True})
        if resp.status_code == 404:
            return AdapterResult(success=False, data={}, error=f"Email {message_id} not found")
        resp.raise_for_status()
        return AdapterResult(success=True, data={})

    async def shutdown(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
