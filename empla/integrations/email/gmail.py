"""
Gmail email adapter.

Implements EmailAdapter using the Gmail API (google-api-python-client).
"""

import asyncio
import base64
import logging
from datetime import UTC, datetime
from email.mime.text import MIMEText
from typing import Any

from empla.integrations.base import AdapterResult
from empla.integrations.email.base import EmailAdapter
from empla.integrations.email.types import Email

logger = logging.getLogger(__name__)

# Timeout for individual Gmail API calls (seconds).
# asyncio.wait_for cancels the coroutine on timeout; the underlying thread
# may still complete, but the caller is unblocked.
_API_TIMEOUT_SECONDS = 30


def _pad_base64url(data: str) -> str:
    """Add padding to base64url-encoded string if missing.

    Gmail API returns base64url without padding.  Python's
    ``base64.urlsafe_b64decode`` may fail on certain inputs when
    padding is absent, so we normalise here.
    """
    return data + "=" * (-len(data) % 4)


class GmailEmailAdapter(EmailAdapter):
    """Gmail API adapter.

    Wraps synchronous Google API calls with asyncio.to_thread.
    """

    def __init__(self, email_address: str) -> None:
        self._email_address = email_address
        self._client: Any = None

    async def _run_in_thread(self, func: Any) -> Any:
        """Run *func* in a thread with a timeout guard."""
        return await asyncio.wait_for(
            asyncio.to_thread(func),
            timeout=_API_TIMEOUT_SECONDS,
        )

    async def initialize(self, credentials: dict[str, Any]) -> None:
        """Initialize Gmail API service from OAuth credentials."""
        if not isinstance(credentials, dict):
            raise TypeError("credentials must be a dict")

        # Validate required credential fields
        if not credentials.get("access_token"):
            raise ValueError("credentials must include a non-empty 'access_token'")
        if not credentials.get("refresh_token"):
            raise ValueError("credentials must include a non-empty 'refresh_token'")

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = Credentials(
                token=credentials["access_token"],
                refresh_token=credentials["refresh_token"],
                token_uri="https://oauth2.googleapis.com/token",
            )

            def _build_service() -> Any:
                return build("gmail", "v1", credentials=creds, cache_discovery=False)

            self._client = await self._run_in_thread(_build_service)

        except ImportError as e:
            raise RuntimeError(
                "Gmail dependencies not installed. "
                "Run: pip install google-api-python-client google-auth"
            ) from e
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"Gmail initialization failed: {e}") from e

    async def fetch_emails(
        self,
        *,
        unread_only: bool = True,
        since: datetime | None = None,
        max_results: int = 50,
    ) -> list[Email]:
        """Fetch emails from Gmail matching the criteria.

        Translates structured parameters into Gmail search operators.
        Raises on API errors — callers (e.g. perceive()) handle retries.
        """
        if not self._client:
            logger.warning("fetch_emails called before client initialized")
            return []

        # Build Gmail search query from structured params
        query_parts: list[str] = []
        if unread_only:
            query_parts.append("is:unread")
        if since:
            epoch = int(since.timestamp())
            query_parts.append(f"after:{epoch}")
        q = " ".join(query_parts) if query_parts else None

        def _list_messages() -> dict[str, Any]:
            kwargs: dict[str, Any] = {
                "userId": "me",
                "maxResults": max_results,
            }
            if q:
                kwargs["q"] = q
            return self._client.users().messages().list(**kwargs).execute()

        result = await self._run_in_thread(_list_messages)
        messages = result.get("messages", [])

        if not messages:
            return []

        emails: list[Email] = []
        for msg_info in messages:
            try:
                email = await self.fetch_message(msg_info["id"])
                if email:
                    emails.append(email)
            except Exception:
                logger.warning(
                    "Failed to fetch message %s",
                    msg_info["id"],
                    exc_info=True,
                )

        return emails

    async def fetch_message(self, message_id: str) -> Email | None:
        """Fetch a single Gmail message by ID."""
        if not self._client:
            logger.warning("fetch_message called before client initialized")
            return None

        def _get_message() -> dict[str, Any]:
            return (
                self._client.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

        msg = await self._run_in_thread(_get_message)

        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}

        body = ""
        html_body = None
        payload = msg.get("payload", {})

        if "parts" in payload:
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")
                data = part.get("body", {}).get("data", "")
                if data:
                    decoded = base64.urlsafe_b64decode(_pad_base64url(data)).decode(
                        "utf-8", errors="replace"
                    )
                    if mime_type == "text/plain":
                        body = decoded
                    elif mime_type == "text/html":
                        html_body = decoded
        elif "body" in payload and payload["body"].get("data"):
            body = base64.urlsafe_b64decode(_pad_base64url(payload["body"]["data"])).decode(
                "utf-8", errors="replace"
            )

        internal_date = msg.get("internalDate")
        timestamp = (
            datetime.fromtimestamp(int(internal_date) / 1000, tz=UTC)
            if internal_date
            else datetime.now(UTC)
        )

        from_addr = headers.get("from", "")
        to_addrs = [addr.strip() for addr in headers.get("to", "").split(",") if addr.strip()]
        cc_addrs = [addr.strip() for addr in headers.get("cc", "").split(",") if addr.strip()]

        return Email(
            id=message_id,
            thread_id=msg.get("threadId"),
            from_addr=from_addr,
            to_addrs=to_addrs,
            cc_addrs=cc_addrs,
            subject=headers.get("subject", "(no subject)"),
            body=body,
            html_body=html_body,
            timestamp=timestamp,
            attachments=[],
            in_reply_to=headers.get("in-reply-to"),
            labels=msg.get("labelIds", []),
            is_read="UNREAD" not in msg.get("labelIds", []),
        )

    async def send(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
    ) -> AdapterResult:
        """Send email via Gmail API."""
        if not self._client:
            logger.warning("send called before client initialized")
            return AdapterResult(success=False, error="Gmail client not initialized")

        try:
            message = MIMEText(body)
            message["to"] = ", ".join(to)
            message["from"] = self._email_address
            message["subject"] = subject
            if cc:
                message["cc"] = ", ".join(cc)

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

            def _send() -> dict[str, Any]:
                return (
                    self._client.users().messages().send(userId="me", body={"raw": raw}).execute()
                )

            result = await self._run_in_thread(_send)
            message_id = result.get("id", "")

            return AdapterResult(success=True, data={"message_id": message_id})

        except Exception as e:
            return AdapterResult(success=False, error=f"Gmail send failed: {e}")

    async def reply(
        self,
        message_id: str,
        body: str,
        cc: list[str] | None = None,
    ) -> AdapterResult:
        """Reply to email via Gmail API."""
        if not self._client:
            logger.warning("reply called before client initialized")
            return AdapterResult(success=False, error="Gmail client not initialized")

        try:
            original = await self.fetch_message(message_id)
            if not original:
                return AdapterResult(success=False, error="Original email not found")

            message = MIMEText(body)
            message["to"] = original.from_addr
            message["from"] = self._email_address
            message["subject"] = (
                f"Re: {original.subject}"
                if not original.subject.startswith("Re:")
                else original.subject
            )
            message["In-Reply-To"] = message_id
            message["References"] = message_id
            if cc:
                message["cc"] = ", ".join(cc)

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

            def _send() -> dict[str, Any]:
                return (
                    self._client.users()
                    .messages()
                    .send(
                        userId="me",
                        body={"raw": raw, "threadId": original.thread_id},
                    )
                    .execute()
                )

            result = await self._run_in_thread(_send)
            reply_id = result.get("id", "")

            return AdapterResult(success=True, data={"message_id": reply_id})

        except Exception as e:
            return AdapterResult(success=False, error=f"Gmail reply failed: {e}")

    async def forward(
        self,
        message_id: str,
        to: list[str],
        body: str | None = None,
    ) -> AdapterResult:
        """Forward email via Gmail API."""
        if not self._client:
            logger.warning("forward called before client initialized")
            return AdapterResult(success=False, error="Gmail client not initialized")

        try:
            original = await self.fetch_message(message_id)
            if not original:
                return AdapterResult(success=False, error="Original email not found")

            forward_header = (
                f"\n\n---------- Forwarded message ----------\n"
                f"From: {original.from_addr}\n"
                f"Date: {original.timestamp.isoformat() if original.timestamp else 'Unknown'}\n"
                f"Subject: {original.subject}\n"
                f"To: {', '.join(original.to_addrs)}\n\n"
            )
            full_body = (body or "") + forward_header + (original.body or "")

            message = MIMEText(full_body)
            message["to"] = ", ".join(to)
            message["from"] = self._email_address
            message["subject"] = (
                f"Fwd: {original.subject}"
                if not original.subject.startswith("Fwd:")
                else original.subject
            )

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

            def _send() -> dict[str, Any]:
                return (
                    self._client.users().messages().send(userId="me", body={"raw": raw}).execute()
                )

            result = await self._run_in_thread(_send)
            fwd_id = result.get("id", "")

            return AdapterResult(success=True, data={"message_id": fwd_id})

        except Exception as e:
            return AdapterResult(success=False, error=f"Gmail forward failed: {e}")

    async def mark_read(self, message_id: str) -> AdapterResult:
        """Mark email as read by removing UNREAD label."""
        if not self._client:
            logger.warning("mark_read called before client initialized")
            return AdapterResult(success=False, error="Gmail client not initialized")

        try:

            def _modify() -> dict[str, Any]:
                return (
                    self._client.users()
                    .messages()
                    .modify(
                        userId="me",
                        id=message_id,
                        body={"removeLabelIds": ["UNREAD"]},
                    )
                    .execute()
                )

            await self._run_in_thread(_modify)
            return AdapterResult(success=True)

        except Exception as e:
            return AdapterResult(success=False, error=f"Gmail mark_read failed: {e}")

    async def archive(self, message_id: str) -> AdapterResult:
        """Archive email by removing INBOX label."""
        if not self._client:
            logger.warning("archive called before client initialized")
            return AdapterResult(success=False, error="Gmail client not initialized")

        try:

            def _modify() -> dict[str, Any]:
                return (
                    self._client.users()
                    .messages()
                    .modify(
                        userId="me",
                        id=message_id,
                        body={"removeLabelIds": ["INBOX"]},
                    )
                    .execute()
                )

            await self._run_in_thread(_modify)
            return AdapterResult(success=True)

        except Exception as e:
            return AdapterResult(success=False, error=f"Gmail archive failed: {e}")

    async def shutdown(self) -> None:
        """Clean up Gmail client resources."""
        self._client = None
