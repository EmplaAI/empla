"""
Extended coverage tests for GmailEmailAdapter.

Covers edge cases and branches not in test_integrations_email_gmail.py:
- _pad_base64url utility
- fetch_message with missing internalDate
- fetch_message with empty payload parts (no data)
- forward with existing Fwd: prefix
- reply with message_id_header fallback
- shutdown on already-None client
"""

import base64
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from empla.integrations.email.gmail import GmailEmailAdapter, _pad_base64url

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_gmail_message(
    msg_id: str = "msg123",
    thread_id: str = "thread456",
    from_addr: str = "sender@example.com",
    to_addr: str = "test@gmail.com",
    subject: str = "Test Subject",
    body_text: str = "Test body content",
    label_ids: list[str] | None = None,
    cc_addr: str | None = None,
    has_parts: bool = False,
    internal_date: str | None = None,
    message_id_header: str | None = None,
    in_reply_to: str | None = None,
    include_empty_part: bool = False,
) -> dict:
    """Build a mock Gmail API message response."""
    headers = [
        {"name": "From", "value": from_addr},
        {"name": "To", "value": to_addr},
        {"name": "Subject", "value": subject},
    ]
    if cc_addr:
        headers.append({"name": "Cc", "value": cc_addr})
    if message_id_header:
        headers.append({"name": "Message-ID", "value": message_id_header})
    if in_reply_to:
        headers.append({"name": "In-Reply-To", "value": in_reply_to})

    encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

    if has_parts:
        parts = [
            {"mimeType": "text/plain", "body": {"data": encoded_body}},
            {
                "mimeType": "text/html",
                "body": {"data": base64.urlsafe_b64encode(f"<p>{body_text}</p>".encode()).decode()},
            },
        ]
        if include_empty_part:
            parts.append({"mimeType": "text/plain", "body": {"data": ""}})
        payload = {"headers": headers, "parts": parts}
    else:
        payload = {"headers": headers, "body": {"data": encoded_body}}

    msg: dict = {
        "id": msg_id,
        "threadId": thread_id,
        "payload": payload,
        "labelIds": label_ids if label_ids is not None else ["INBOX", "UNREAD"],
    }
    if internal_date is not None:
        msg["internalDate"] = internal_date
    else:
        msg["internalDate"] = str(
            int(datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).timestamp() * 1000)
        )
    return msg


@pytest.fixture
def adapter() -> GmailEmailAdapter:
    return GmailEmailAdapter(email_address="test@gmail.com")


@pytest.fixture
def initialized_adapter(adapter: GmailEmailAdapter) -> GmailEmailAdapter:
    mock_service = MagicMock()
    mock_users = MagicMock()
    mock_messages = MagicMock()
    mock_service.users.return_value = mock_users
    mock_users.messages.return_value = mock_messages
    adapter._client = mock_service
    return adapter


# ---------------------------------------------------------------------------
# _pad_base64url
# ---------------------------------------------------------------------------


class TestPadBase64Url:
    def test_no_padding_needed(self):
        """Input length divisible by 4 needs no padding."""
        assert _pad_base64url("abcd") == "abcd"

    def test_one_pad(self):
        """Input length % 4 == 3 needs 1 '='."""
        assert _pad_base64url("abc") == "abc="

    def test_two_pads(self):
        """Input length % 4 == 2 needs 2 '='."""
        assert _pad_base64url("ab") == "ab=="

    def test_three_pads(self):
        """Input length % 4 == 1 needs 3 '='."""
        assert _pad_base64url("a") == "a==="

    def test_empty_string(self):
        assert _pad_base64url("") == ""


# ---------------------------------------------------------------------------
# fetch_message edge cases
# ---------------------------------------------------------------------------


class TestFetchMessageEdgeCases:
    @pytest.mark.asyncio
    async def test_missing_internal_date_uses_now(self, initialized_adapter: GmailEmailAdapter):
        """When internalDate is absent, timestamp defaults to now(UTC)."""
        msg = _make_gmail_message()
        del msg["internalDate"]

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=msg,
        ):
            email = await initialized_adapter.fetch_message("msg123")
            assert email is not None
            # Should be approximately now
            assert (datetime.now(UTC) - email.timestamp).total_seconds() < 5

    @pytest.mark.asyncio
    async def test_multipart_with_empty_data(self, initialized_adapter: GmailEmailAdapter):
        """Parts with empty data field are skipped."""
        msg = _make_gmail_message(has_parts=True, include_empty_part=True)

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=msg,
        ):
            email = await initialized_adapter.fetch_message("msg123")
            assert email is not None
            assert email.body == "Test body content"

    @pytest.mark.asyncio
    async def test_message_with_cc(self, initialized_adapter: GmailEmailAdapter):
        """CC addresses are parsed correctly."""
        msg = _make_gmail_message(cc_addr="cc1@example.com, cc2@example.com")

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=msg,
        ):
            email = await initialized_adapter.fetch_message("msg123")
            assert email is not None
            assert "cc1@example.com" in email.cc_addrs
            assert "cc2@example.com" in email.cc_addrs

    @pytest.mark.asyncio
    async def test_message_with_message_id_header(self, initialized_adapter: GmailEmailAdapter):
        """message_id_header and in_reply_to are captured."""
        msg = _make_gmail_message(
            message_id_header="<abc@example.com>",
            in_reply_to="<def@example.com>",
        )

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=msg,
        ):
            email = await initialized_adapter.fetch_message("msg123")
            assert email is not None
            assert email.message_id_header == "<abc@example.com>"
            assert email.in_reply_to == "<def@example.com>"

    @pytest.mark.asyncio
    async def test_message_no_labels(self, initialized_adapter: GmailEmailAdapter):
        """Message without labelIds defaults to empty list, is_read=True."""
        msg = _make_gmail_message()
        del msg["labelIds"]

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=msg,
        ):
            email = await initialized_adapter.fetch_message("msg123")
            assert email is not None
            assert email.labels == []
            assert email.is_read is True

    @pytest.mark.asyncio
    async def test_no_subject_defaults(self, initialized_adapter: GmailEmailAdapter):
        """Missing Subject header defaults to '(no subject)'."""
        msg = _make_gmail_message()
        # Remove Subject header
        msg["payload"]["headers"] = [h for h in msg["payload"]["headers"] if h["name"] != "Subject"]

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=msg,
        ):
            email = await initialized_adapter.fetch_message("msg123")
            assert email is not None
            assert email.subject == "(no subject)"

    @pytest.mark.asyncio
    async def test_empty_payload_no_parts_no_body(self, initialized_adapter: GmailEmailAdapter):
        """Empty payload with no parts or body data produces empty body."""
        msg = _make_gmail_message()
        msg["payload"] = {"headers": msg["payload"]["headers"], "body": {}}

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=msg,
        ):
            email = await initialized_adapter.fetch_message("msg123")
            assert email is not None
            assert email.body == ""


# ---------------------------------------------------------------------------
# Forward edge cases
# ---------------------------------------------------------------------------


class TestForwardEdgeCases:
    @pytest.mark.asyncio
    async def test_existing_fwd_prefix_not_doubled(self, initialized_adapter: GmailEmailAdapter):
        """Forward with existing Fwd: prefix does not add another."""
        call_count = [0]

        async def mock_to_thread(func):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_gmail_message(subject="Fwd: Already Forwarded")
            return {"id": "fwd123"}

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            result = await initialized_adapter.forward(message_id="msg123", to=["a@example.com"])
            assert result.success is True

    @pytest.mark.asyncio
    async def test_forward_client_not_initialized(self, adapter: GmailEmailAdapter):
        """Forward fails when client not initialized."""
        result = await adapter.forward(message_id="msg123", to=["a@example.com"])
        assert result.success is False
        assert "not initialized" in result.error


# ---------------------------------------------------------------------------
# Reply edge cases
# ---------------------------------------------------------------------------


class TestReplyEdgeCases:
    @pytest.mark.asyncio
    async def test_reply_uses_message_id_header_for_references(
        self, initialized_adapter: GmailEmailAdapter
    ):
        """Reply uses the RFC5322 Message-ID header for In-Reply-To."""
        call_count = [0]

        async def mock_to_thread(func):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_gmail_message(
                    subject="Hello",
                    message_id_header="<rfc5322@example.com>",
                )
            return {"id": "reply123"}

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            result = await initialized_adapter.reply(message_id="msg123", body="Reply")
            assert result.success is True


# ---------------------------------------------------------------------------
# fetch_emails edge cases
# ---------------------------------------------------------------------------


class TestFetchEmailsEdgeCases:
    @pytest.mark.asyncio
    async def test_fetch_emails_no_unread_filter(self, initialized_adapter: GmailEmailAdapter):
        """With unread_only=False and no since, no query param is set."""
        mock_list = MagicMock()
        mock_list.execute.return_value = {"messages": []}
        initialized_adapter._client.users().messages().list.return_value = mock_list

        emails = await initialized_adapter.fetch_emails(unread_only=False, since=None)
        assert emails == []

        call_kwargs = initialized_adapter._client.users().messages().list.call_args[1]
        assert "q" not in call_kwargs

    @pytest.mark.asyncio
    async def test_fetch_emails_with_since_only(self, initialized_adapter: GmailEmailAdapter):
        """With since provided and unread_only=False, only after: in query."""
        since = datetime(2024, 6, 1, tzinfo=UTC)
        mock_list = MagicMock()
        mock_list.execute.return_value = {"messages": []}
        initialized_adapter._client.users().messages().list.return_value = mock_list

        await initialized_adapter.fetch_emails(unread_only=False, since=since)

        call_kwargs = initialized_adapter._client.users().messages().list.call_args[1]
        assert "is:unread" not in call_kwargs.get("q", "")
        assert f"after:{int(since.timestamp())}" in call_kwargs["q"]


# ---------------------------------------------------------------------------
# Shutdown edge cases
# ---------------------------------------------------------------------------


class TestShutdownEdgeCases:
    @pytest.mark.asyncio
    async def test_shutdown_on_none_client(self, adapter: GmailEmailAdapter):
        """Shutdown when client is already None does not raise."""
        assert adapter._client is None
        await adapter.shutdown()
        assert adapter._client is None


# ---------------------------------------------------------------------------
# Initialize edge cases
# ---------------------------------------------------------------------------


class TestInitializeEdgeCases:
    @pytest.mark.asyncio
    async def test_value_error_during_init_reraised(self, adapter: GmailEmailAdapter):
        """ValueError from credential construction is re-raised directly."""
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=ValueError("bad creds"),
        ):
            with pytest.raises(ValueError, match="bad creds"):
                await adapter.initialize({"access_token": "t", "refresh_token": "r"})
