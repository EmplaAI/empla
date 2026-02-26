"""
Unit tests for GmailEmailAdapter.

All tests mock asyncio.to_thread and the Google API client — no real API calls.
"""

import base64
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from empla.integrations.email.gmail import GmailEmailAdapter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter() -> GmailEmailAdapter:
    """Create a GmailEmailAdapter with test email address."""
    return GmailEmailAdapter(email_address="test@gmail.com")


@pytest.fixture
def initialized_adapter(adapter: GmailEmailAdapter) -> GmailEmailAdapter:
    """Adapter with a mocked Gmail client already set."""
    mock_service = MagicMock()
    mock_users = MagicMock()
    mock_messages = MagicMock()
    mock_service.users.return_value = mock_users
    mock_users.messages.return_value = mock_messages
    adapter._client = mock_service
    return adapter


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
) -> dict:
    """Build a mock Gmail API message response."""
    headers = [
        {"name": "From", "value": from_addr},
        {"name": "To", "value": to_addr},
        {"name": "Subject", "value": subject},
    ]
    if cc_addr:
        headers.append({"name": "Cc", "value": cc_addr})

    encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

    if has_parts:
        payload = {
            "headers": headers,
            "parts": [
                {"mimeType": "text/plain", "body": {"data": encoded_body}},
                {
                    "mimeType": "text/html",
                    "body": {
                        "data": base64.urlsafe_b64encode(f"<p>{body_text}</p>".encode()).decode()
                    },
                },
            ],
        }
    else:
        payload = {
            "headers": headers,
            "body": {"data": encoded_body},
        }

    return {
        "id": msg_id,
        "threadId": thread_id,
        "payload": payload,
        "labelIds": label_ids if label_ids is not None else ["INBOX", "UNREAD"],
        "internalDate": str(int(datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).timestamp() * 1000)),
    }


# ---------------------------------------------------------------------------
# TestGmailInitialize
# ---------------------------------------------------------------------------


class TestGmailInitialize:
    @pytest.mark.asyncio
    async def test_success(self, adapter: GmailEmailAdapter):
        """Initialize succeeds with valid credentials."""
        mock_service = MagicMock()
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            await adapter.initialize({"access_token": "tok", "refresh_token": "ref"})
            assert adapter._client is mock_service

    @pytest.mark.asyncio
    async def test_missing_dependencies(self, adapter: GmailEmailAdapter):
        """Initialize raises RuntimeError when google libs missing."""
        with patch.dict("sys.modules", {"google.oauth2.credentials": None}):
            with pytest.raises(RuntimeError, match="Gmail dependencies"):
                await adapter.initialize({"access_token": "t", "refresh_token": "r"})

    @pytest.mark.asyncio
    async def test_build_failure(self, adapter: GmailEmailAdapter):
        """Initialize raises RuntimeError on build failure."""
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=Exception("build error"),
        ):
            with pytest.raises(RuntimeError, match="Gmail initialization failed"):
                await adapter.initialize({"access_token": "t", "refresh_token": "r"})

    @pytest.mark.asyncio
    async def test_missing_access_token(self, adapter: GmailEmailAdapter):
        """Initialize raises ValueError when access_token is missing."""
        with pytest.raises(ValueError, match="access_token"):
            await adapter.initialize({"refresh_token": "r"})

    @pytest.mark.asyncio
    async def test_missing_refresh_token(self, adapter: GmailEmailAdapter):
        """Initialize raises ValueError when refresh_token is missing."""
        with pytest.raises(ValueError, match="refresh_token"):
            await adapter.initialize({"access_token": "t"})

    @pytest.mark.asyncio
    async def test_empty_credentials(self, adapter: GmailEmailAdapter):
        """Initialize raises ValueError when credentials dict is empty."""
        with pytest.raises(ValueError, match="access_token"):
            await adapter.initialize({})

    @pytest.mark.asyncio
    async def test_credentials_not_a_dict(self, adapter: GmailEmailAdapter):
        """Initialize raises TypeError when credentials is not a dict."""
        with pytest.raises(TypeError, match="credentials must be a dict"):
            await adapter.initialize("not-a-dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TestGmailFetchEmails
# ---------------------------------------------------------------------------


class TestGmailFetchEmails:
    @pytest.mark.asyncio
    async def test_empty_inbox(self, initialized_adapter: GmailEmailAdapter):
        """Returns empty list when no messages."""
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value={"messages": []},
        ):
            emails = await initialized_adapter.fetch_emails()
            assert emails == []

    @pytest.mark.asyncio
    async def test_no_messages_key(self, initialized_adapter: GmailEmailAdapter):
        """Returns empty list when API returns no messages key."""
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value={},
        ):
            emails = await initialized_adapter.fetch_emails()
            assert emails == []

    @pytest.mark.asyncio
    async def test_multiple_emails(self, initialized_adapter: GmailEmailAdapter):
        """Fetches multiple emails successfully."""
        call_count = [0]

        async def mock_to_thread(func):
            call_count[0] += 1
            if call_count[0] == 1:  # List call
                return {
                    "messages": [
                        {"id": "msg1", "threadId": "t1"},
                        {"id": "msg2", "threadId": "t2"},
                    ]
                }
            # Get calls
            msg_id = "msg1" if call_count[0] == 2 else "msg2"
            return _make_gmail_message(msg_id=msg_id, thread_id=f"t{call_count[0] - 1}")

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            emails = await initialized_adapter.fetch_emails()
            assert len(emails) == 2
            assert emails[0].id == "msg1"
            assert emails[1].id == "msg2"

    @pytest.mark.asyncio
    async def test_builds_gmail_query_from_params(self, initialized_adapter: GmailEmailAdapter):
        """Builds Gmail search query from structured parameters."""
        since = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        epoch = int(since.timestamp())

        mock_list = MagicMock()
        mock_list.execute.return_value = {"messages": []}
        initialized_adapter._client.users().messages().list.return_value = mock_list

        # Use real to_thread so the inner function actually runs against the mock
        emails = await initialized_adapter.fetch_emails(
            unread_only=True, since=since, max_results=10
        )
        assert emails == []

        call_kwargs = initialized_adapter._client.users().messages().list.call_args[1]
        assert "is:unread" in call_kwargs["q"]
        assert f"after:{epoch}" in call_kwargs["q"]
        assert call_kwargs["maxResults"] == 10

    @pytest.mark.asyncio
    async def test_unread_false_omits_filter(self, initialized_adapter: GmailEmailAdapter):
        """When unread_only=False, 'is:unread' is not in the query."""
        mock_list = MagicMock()
        mock_list.execute.return_value = {"messages": []}
        initialized_adapter._client.users().messages().list.return_value = mock_list

        emails = await initialized_adapter.fetch_emails(unread_only=False)
        assert emails == []

        call_kwargs = initialized_adapter._client.users().messages().list.call_args[1]
        # No query should be passed when no filters apply
        assert "q" not in call_kwargs

    @pytest.mark.asyncio
    async def test_partial_failure_returns_successful_messages(
        self, initialized_adapter: GmailEmailAdapter
    ):
        """If one message fetch fails, other messages are still returned."""
        call_count = [0]

        async def mock_to_thread(func):
            call_count[0] += 1
            if call_count[0] == 1:  # List call
                return {"messages": [{"id": "msg1"}, {"id": "msg2"}, {"id": "msg3"}]}
            if call_count[0] == 3:  # msg2 fetch fails
                raise Exception("Corrupted message")
            return _make_gmail_message(msg_id=f"msg{call_count[0] - 1}")

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            emails = await initialized_adapter.fetch_emails()
            assert len(emails) == 2

    @pytest.mark.asyncio
    async def test_error_propagates(self, initialized_adapter: GmailEmailAdapter):
        """API errors propagate to caller (perceive handles them)."""
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            with pytest.raises(Exception, match="API error"):
                await initialized_adapter.fetch_emails()

    @pytest.mark.asyncio
    async def test_client_not_initialized(self, adapter: GmailEmailAdapter):
        """Returns empty list when client is None."""
        emails = await adapter.fetch_emails()
        assert emails == []

    @pytest.mark.asyncio
    async def test_to_thread_timeout_propagates(self, initialized_adapter: GmailEmailAdapter):
        """Timeout from _run_in_thread propagates to caller."""
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=TimeoutError(),
        ):
            with pytest.raises(TimeoutError):
                await initialized_adapter.fetch_emails()


# ---------------------------------------------------------------------------
# TestGmailFetchMessage
# ---------------------------------------------------------------------------


class TestGmailFetchMessage:
    @pytest.mark.asyncio
    async def test_full_parse(self, initialized_adapter: GmailEmailAdapter):
        """Parses all fields from Gmail message."""
        msg = _make_gmail_message(
            msg_id="msg123",
            thread_id="thread456",
            from_addr="sender@example.com",
            to_addr="test@gmail.com",
            subject="Test Subject",
            body_text="Test body content",
            label_ids=["INBOX", "UNREAD"],
        )
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=msg,
        ):
            email = await initialized_adapter.fetch_message("msg123")

            assert email is not None
            assert email.id == "msg123"
            assert email.thread_id == "thread456"
            assert email.from_addr == "sender@example.com"
            assert "test@gmail.com" in email.to_addrs
            assert email.subject == "Test Subject"
            assert email.body == "Test body content"
            assert email.is_read is False

    @pytest.mark.asyncio
    async def test_multipart_message(self, initialized_adapter: GmailEmailAdapter):
        """Parses multipart messages with text and HTML."""
        msg = _make_gmail_message(body_text="Plain text", has_parts=True)
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=msg,
        ):
            email = await initialized_adapter.fetch_message("msg123")

            assert email is not None
            assert email.body == "Plain text"
            assert email.html_body is not None
            assert "<p>Plain text</p>" in email.html_body

    @pytest.mark.asyncio
    async def test_read_message(self, initialized_adapter: GmailEmailAdapter):
        """Message without UNREAD label is marked as read."""
        msg = _make_gmail_message(label_ids=["INBOX"])
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=msg,
        ):
            email = await initialized_adapter.fetch_message("msg123")
            assert email is not None
            assert email.is_read is True

    @pytest.mark.asyncio
    async def test_client_not_initialized(self, adapter: GmailEmailAdapter):
        """Returns None when client is not initialized."""
        result = await adapter.fetch_message("msg123")
        assert result is None


# ---------------------------------------------------------------------------
# TestGmailSend
# ---------------------------------------------------------------------------


class TestGmailSend:
    @pytest.mark.asyncio
    async def test_success(self, initialized_adapter: GmailEmailAdapter):
        """Send returns success with message_id."""
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value={"id": "sent123"},
        ):
            result = await initialized_adapter.send(
                to=["recipient@example.com"],
                subject="Test",
                body="Body",
            )
            assert result.success is True
            assert result.data["message_id"] == "sent123"

    @pytest.mark.asyncio
    async def test_with_cc(self, initialized_adapter: GmailEmailAdapter):
        """Send with CC recipients succeeds."""
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value={"id": "sent123"},
        ):
            result = await initialized_adapter.send(
                to=["a@example.com"],
                subject="Test",
                body="Body",
                cc=["b@example.com"],
            )
            assert result.success is True

    @pytest.mark.asyncio
    async def test_client_not_initialized(self, adapter: GmailEmailAdapter):
        """Send fails when client is not initialized."""
        result = await adapter.send(to=["a@example.com"], subject="Test", body="Body")
        assert result.success is False
        assert "not initialized" in result.error

    @pytest.mark.asyncio
    async def test_api_error(self, initialized_adapter: GmailEmailAdapter):
        """Send returns error on API failure."""
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=Exception("API quota exceeded"),
        ):
            result = await initialized_adapter.send(
                to=["a@example.com"], subject="Test", body="Body"
            )
            assert result.success is False
            assert "Gmail send failed" in result.error


# ---------------------------------------------------------------------------
# TestGmailReply
# ---------------------------------------------------------------------------


class TestGmailReply:
    @pytest.mark.asyncio
    async def test_success(self, initialized_adapter: GmailEmailAdapter):
        """Reply to existing email succeeds."""
        call_count = [0]

        async def mock_to_thread(func):
            call_count[0] += 1
            if call_count[0] == 1:  # Fetch original
                return _make_gmail_message(
                    msg_id="orig123",
                    thread_id="thread123",
                    subject="Original Subject",
                )
            # Send reply
            return {"id": "reply123", "threadId": "thread123"}

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            result = await initialized_adapter.reply(
                message_id="orig123",
                body="Thanks!",
            )
            assert result.success is True
            assert result.data["message_id"] == "reply123"

    @pytest.mark.asyncio
    async def test_subject_prefixing(self, initialized_adapter: GmailEmailAdapter):
        """Reply adds Re: prefix when not already present."""
        call_count = [0]

        async def mock_to_thread(func):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_gmail_message(subject="Hello")
            return {"id": "reply123"}

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            result = await initialized_adapter.reply(message_id="msg123", body="Reply")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_existing_re_prefix(self, initialized_adapter: GmailEmailAdapter):
        """Reply does not double Re: prefix."""
        call_count = [0]

        async def mock_to_thread(func):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_gmail_message(subject="Re: Hello")
            return {"id": "reply123"}

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            result = await initialized_adapter.reply(message_id="msg123", body="Reply")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_original_not_found(self, initialized_adapter: GmailEmailAdapter):
        """Reply fails when original message not found."""
        with patch.object(
            initialized_adapter, "fetch_message", new_callable=AsyncMock, return_value=None
        ):
            result = await initialized_adapter.reply(message_id="missing", body="Reply")
            assert result.success is False
            assert "Original email not found" in result.error

    @pytest.mark.asyncio
    async def test_with_cc(self, initialized_adapter: GmailEmailAdapter):
        """Reply with CC recipients."""
        call_count = [0]

        async def mock_to_thread(func):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_gmail_message()
            return {"id": "reply123"}

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            result = await initialized_adapter.reply(
                message_id="msg123",
                body="Reply",
                cc=["cc@example.com"],
            )
            assert result.success is True

    @pytest.mark.asyncio
    async def test_client_not_initialized(self, adapter: GmailEmailAdapter):
        """Reply fails when client not initialized."""
        result = await adapter.reply(message_id="msg123", body="Reply")
        assert result.success is False
        assert "not initialized" in result.error

    @pytest.mark.asyncio
    async def test_api_error(self, initialized_adapter: GmailEmailAdapter):
        """Reply returns error on send API failure."""
        call_count = [0]

        async def mock_to_thread(func):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_gmail_message()
            raise Exception("Send quota exceeded")

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            result = await initialized_adapter.reply(message_id="msg123", body="Reply")
            assert result.success is False
            assert "Gmail reply failed" in result.error


# ---------------------------------------------------------------------------
# TestGmailForward
# ---------------------------------------------------------------------------


class TestGmailForward:
    @pytest.mark.asyncio
    async def test_success(self, initialized_adapter: GmailEmailAdapter):
        """Forward email succeeds."""
        call_count = [0]

        async def mock_to_thread(func):
            call_count[0] += 1
            if call_count[0] == 1:  # Fetch original
                return _make_gmail_message(subject="Important Update")
            return {"id": "fwd123"}

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            result = await initialized_adapter.forward(
                message_id="msg123",
                to=["colleague@example.com"],
                body="FYI",
            )
            assert result.success is True
            assert result.data["message_id"] == "fwd123"

    @pytest.mark.asyncio
    async def test_without_comment(self, initialized_adapter: GmailEmailAdapter):
        """Forward without comment uses empty string."""
        call_count = [0]

        async def mock_to_thread(func):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_gmail_message()
            return {"id": "fwd123"}

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            result = await initialized_adapter.forward(
                message_id="msg123",
                to=["a@example.com"],
            )
            assert result.success is True

    @pytest.mark.asyncio
    async def test_original_not_found(self, initialized_adapter: GmailEmailAdapter):
        """Forward fails when original not found."""
        with patch.object(
            initialized_adapter, "fetch_message", new_callable=AsyncMock, return_value=None
        ):
            result = await initialized_adapter.forward(
                message_id="missing",
                to=["a@example.com"],
            )
            assert result.success is False
            assert "Original email not found" in result.error

    @pytest.mark.asyncio
    async def test_api_error(self, initialized_adapter: GmailEmailAdapter):
        """Forward returns error on API failure."""
        call_count = [0]

        async def mock_to_thread(func):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_gmail_message()
            raise Exception("Send failed")

        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            result = await initialized_adapter.forward(
                message_id="msg123",
                to=["a@example.com"],
            )
            assert result.success is False
            assert "Gmail forward failed" in result.error


# ---------------------------------------------------------------------------
# TestGmailMarkRead
# ---------------------------------------------------------------------------


class TestGmailMarkRead:
    @pytest.mark.asyncio
    async def test_success(self, initialized_adapter: GmailEmailAdapter):
        """Mark read succeeds."""
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value={"id": "msg123", "labelIds": ["INBOX"]},
        ):
            result = await initialized_adapter.mark_read("msg123")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_client_not_initialized(self, adapter: GmailEmailAdapter):
        """Mark read fails when client not initialized."""
        result = await adapter.mark_read("msg123")
        assert result.success is False
        assert "not initialized" in result.error

    @pytest.mark.asyncio
    async def test_api_error(self, initialized_adapter: GmailEmailAdapter):
        """Mark read returns error on API failure."""
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            result = await initialized_adapter.mark_read("msg123")
            assert result.success is False
            assert "Gmail mark_read failed" in result.error


# ---------------------------------------------------------------------------
# TestGmailArchive
# ---------------------------------------------------------------------------


class TestGmailArchive:
    @pytest.mark.asyncio
    async def test_success(self, initialized_adapter: GmailEmailAdapter):
        """Archive succeeds."""
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value={"id": "msg123", "labelIds": []},
        ):
            result = await initialized_adapter.archive("msg123")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_client_not_initialized(self, adapter: GmailEmailAdapter):
        """Archive fails when client not initialized."""
        result = await adapter.archive("msg123")
        assert result.success is False
        assert "not initialized" in result.error

    @pytest.mark.asyncio
    async def test_api_error(self, initialized_adapter: GmailEmailAdapter):
        """Archive returns error on API failure."""
        with patch(
            "empla.integrations.email.gmail.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            result = await initialized_adapter.archive("msg123")
            assert result.success is False
            assert "Gmail archive failed" in result.error


# ---------------------------------------------------------------------------
# TestGmailShutdown
# ---------------------------------------------------------------------------


class TestGmailShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_clears_client(self, initialized_adapter: GmailEmailAdapter):
        """Shutdown sets client to None."""
        assert initialized_adapter._client is not None
        await initialized_adapter.shutdown()
        assert initialized_adapter._client is None
