"""
Unit tests for EmailCapability.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from empla.capabilities.base import (
    CAPABILITY_EMAIL,
    Action,
    CapabilityConfig,
)
from empla.capabilities.email import EmailCapability, EmailConfig
from empla.integrations.base import AdapterResult
from empla.integrations.email.factory import UnknownEmailProviderError
from empla.integrations.email.types import Email, EmailPriority, EmailProvider

# Test EmailConfig


def test_email_config_defaults():
    """Test EmailConfig initialization with defaults"""
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={"client_id": "123"},
    )

    assert config.provider == EmailProvider.MICROSOFT_GRAPH
    assert config.email_address == "test@example.com"
    assert config.check_interval_seconds == 60
    assert config.monitor_folders == ["inbox", "sent"]
    assert config.auto_triage is True
    assert config.auto_respond is False
    assert config.signature is None

    # Check default priority keywords
    assert EmailPriority.URGENT in config.priority_keywords
    assert "urgent" in config.priority_keywords[EmailPriority.URGENT]
    assert "asap" in config.priority_keywords[EmailPriority.URGENT]


def test_email_config_custom():
    """Test EmailConfig with custom settings"""
    config = EmailConfig(
        provider=EmailProvider.GMAIL,
        email_address="custom@example.com",
        credentials={"token": "abc"},
        check_interval_seconds=120,
        monitor_folders=["inbox"],
        auto_triage=False,
        auto_respond=True,
        signature="Best regards,\nTest User",
        priority_keywords={
            EmailPriority.HIGH: ["important", "priority"],
        },
    )

    assert config.provider == EmailProvider.GMAIL
    assert config.check_interval_seconds == 120
    assert config.monitor_folders == ["inbox"]
    assert config.auto_triage is False
    assert config.auto_respond is True
    assert "Test User" in config.signature
    assert config.priority_keywords[EmailPriority.HIGH] == [
        "important",
        "priority",
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_adapter(
    send_result: AdapterResult | None = None,
    reply_result: AdapterResult | None = None,
    forward_result: AdapterResult | None = None,
    mark_read_result: AdapterResult | None = None,
    archive_result: AdapterResult | None = None,
    fetch_emails_result: list[Email] | None = None,
) -> MagicMock:
    """Create a mock EmailAdapter with sensible defaults."""
    adapter = MagicMock()
    adapter.initialize = AsyncMock()
    adapter.send = AsyncMock(
        return_value=send_result or AdapterResult(success=True, data={"message_id": "msg123"})
    )
    adapter.reply = AsyncMock(
        return_value=reply_result or AdapterResult(success=True, data={"message_id": "reply123"})
    )
    adapter.forward = AsyncMock(
        return_value=forward_result or AdapterResult(success=True, data={"message_id": "fwd123"})
    )
    adapter.mark_read = AsyncMock(return_value=mark_read_result or AdapterResult(success=True))
    adapter.archive = AsyncMock(return_value=archive_result or AdapterResult(success=True))
    adapter.fetch_emails = AsyncMock(return_value=fetch_emails_result or [])
    adapter.shutdown = AsyncMock()
    return adapter


def _make_gmail_capability(
    provider: EmailProvider = EmailProvider.GMAIL,
    signature: str | None = None,
) -> EmailCapability:
    """Create an EmailCapability with default config."""
    config = EmailConfig(
        provider=provider,
        email_address="test@gmail.com",
        credentials={"access_token": "tok", "refresh_token": "ref"},
        signature=signature,
    )
    return EmailCapability(uuid4(), uuid4(), config)


async def _init_with_mock_adapter(
    capability: EmailCapability,
    adapter: MagicMock | None = None,
) -> MagicMock:
    """Set up capability with a mock adapter (bypasses real factory)."""
    mock_adapter = adapter or _make_mock_adapter()
    capability._adapter = mock_adapter
    capability._initialized = True
    return mock_adapter


# ---------------------------------------------------------------------------
# Test EmailCapability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_capability_initialization():
    """Test EmailCapability initialization via adapter factory."""
    capability = _make_gmail_capability()

    assert capability.capability_type == CAPABILITY_EMAIL
    assert capability._initialized is False
    assert capability._adapter is None

    mock_adapter = _make_mock_adapter()
    with patch(
        "empla.integrations.email.factory.create_email_adapter",
        return_value=mock_adapter,
    ):
        await capability.initialize()

    assert capability._initialized is True
    assert capability.is_healthy() is True
    mock_adapter.initialize.assert_called_once()


@pytest.mark.asyncio
async def test_email_capability_invalid_provider():
    """Test EmailCapability with invalid provider raises error"""
    tenant_id = uuid4()
    employee_id = uuid4()

    config = CapabilityConfig()
    config.provider = "invalid_provider"
    config.email_address = "test@example.com"
    config.credentials = {}

    capability = EmailCapability(tenant_id, employee_id, config)

    with pytest.raises((UnknownEmailProviderError, NotImplementedError)):
        await capability.initialize()


@pytest.mark.asyncio
async def test_email_capability_perception_not_initialized():
    """Test perception returns empty when not initialized"""
    capability = _make_gmail_capability()

    observations = await capability.perceive()
    assert len(observations) == 0


@pytest.mark.asyncio
async def test_email_capability_perception_no_emails():
    """Test perception with no new emails"""
    capability = _make_gmail_capability()
    await _init_with_mock_adapter(capability)

    observations = await capability.perceive()

    assert len(observations) == 0
    assert capability._last_check is not None


@pytest.mark.asyncio
async def test_email_triage_urgent():
    """Test email triage classifies urgent emails correctly"""
    capability = _make_gmail_capability()
    await _init_with_mock_adapter(capability)

    email = Email(
        id="1",
        thread_id=None,
        from_addr="customer@example.com",
        to_addrs=["test@example.com"],
        cc_addrs=[],
        subject="URGENT: System down",
        body="Our production system is completely down!",
        html_body=None,
        timestamp=datetime.now(UTC),
        attachments=[],
        in_reply_to=None,
        labels=[],
        is_read=False,
    )

    priority = await capability._triage_email(email)
    assert priority == EmailPriority.URGENT


@pytest.mark.asyncio
async def test_email_triage_high():
    """Test email triage classifies high priority emails"""
    capability = _make_gmail_capability()
    await _init_with_mock_adapter(capability)

    email = Email(
        id="2",
        thread_id=None,
        from_addr="lead@prospect.com",
        to_addrs=["test@example.com"],
        cc_addrs=[],
        subject="Important question about your product",
        body="I have an important question about pricing.",
        html_body=None,
        timestamp=datetime.now(UTC),
        attachments=[],
        in_reply_to=None,
        labels=[],
        is_read=False,
    )

    priority = await capability._triage_email(email)
    assert priority == EmailPriority.HIGH


@pytest.mark.asyncio
async def test_email_triage_medium_default():
    """Test email triage defaults to medium priority"""
    capability = _make_gmail_capability()
    await _init_with_mock_adapter(capability)

    email = Email(
        id="3",
        thread_id=None,
        from_addr="colleague@example.com",
        to_addrs=["test@example.com"],
        cc_addrs=[],
        subject="Weekly update",
        body="Here's the weekly update on project status.",
        html_body=None,
        timestamp=datetime.now(UTC),
        attachments=[],
        in_reply_to=None,
        labels=[],
        is_read=False,
    )

    priority = await capability._triage_email(email)
    assert priority == EmailPriority.MEDIUM


@pytest.mark.asyncio
async def test_email_requires_response_question():
    """Test requires_response identifies questions"""
    capability = _make_gmail_capability()
    await _init_with_mock_adapter(capability)

    email = Email(
        id="4",
        thread_id=None,
        from_addr="customer@example.com",
        to_addrs=["test@example.com"],
        cc_addrs=[],
        subject="Question",
        body="Can you help me with this issue?",
        html_body=None,
        timestamp=datetime.now(UTC),
        attachments=[],
        in_reply_to=None,
        labels=[],
        is_read=False,
    )

    assert await capability._requires_response(email) is True


@pytest.mark.asyncio
async def test_email_requires_response_request():
    """Test requires_response identifies requests"""
    capability = _make_gmail_capability()
    await _init_with_mock_adapter(capability)

    email = Email(
        id="5",
        thread_id=None,
        from_addr="manager@example.com",
        to_addrs=["test@example.com"],
        cc_addrs=[],
        subject="Request",
        body="Please send me the report by end of day.",
        html_body=None,
        timestamp=datetime.now(UTC),
        attachments=[],
        in_reply_to=None,
        labels=[],
        is_read=False,
    )

    assert await capability._requires_response(email) is True


@pytest.mark.asyncio
async def test_email_requires_response_fyi():
    """Test requires_response identifies FYIs"""
    capability = _make_gmail_capability()
    await _init_with_mock_adapter(capability)

    email = Email(
        id="6",
        thread_id=None,
        from_addr="colleague@example.com",
        to_addrs=["test@example.com"],
        cc_addrs=[],
        subject="FYI: Meeting rescheduled",
        body="The meeting has been moved to next week.",
        html_body=None,
        timestamp=datetime.now(UTC),
        attachments=[],
        in_reply_to=None,
        labels=[],
        is_read=False,
    )

    assert await capability._requires_response(email) is False


def test_priority_to_int():
    """Test priority to int conversion"""
    capability = _make_gmail_capability()

    assert capability._priority_to_int(EmailPriority.URGENT) == 10
    assert capability._priority_to_int(EmailPriority.HIGH) == 7
    assert capability._priority_to_int(EmailPriority.MEDIUM) == 5
    assert capability._priority_to_int(EmailPriority.LOW) == 2
    assert capability._priority_to_int(EmailPriority.SPAM) == 1


# Test Email Actions


@pytest.mark.asyncio
async def test_email_action_send():
    """Test sending email action"""
    capability = _make_gmail_capability()
    mock_adapter = await _init_with_mock_adapter(capability)

    action = Action(
        capability="email",
        operation="send_email",
        parameters={
            "to": ["recipient@example.com"],
            "subject": "Test email",
            "body": "This is a test email.",
        },
    )

    result = await capability.execute_action(action)

    assert result.success is True
    assert "sent_at" in result.metadata
    assert result.metadata["message_id"] == "msg123"
    mock_adapter.send.assert_called_once()


@pytest.mark.asyncio
async def test_email_action_send_with_signature():
    """Test sending email with signature"""
    capability = _make_gmail_capability(signature="Best regards,\nTest User")
    mock_adapter = await _init_with_mock_adapter(capability)

    action = Action(
        capability="email",
        operation="send_email",
        parameters={
            "to": ["recipient@example.com"],
            "subject": "Test",
            "body": "Email body",
        },
    )

    result = await capability.execute_action(action)

    assert result.success is True
    # Verify signature was appended to body
    call_args = mock_adapter.send.call_args
    body_arg = call_args[0][2]  # positional arg: to, subject, body
    assert "Best regards" in body_arg


@pytest.mark.asyncio
async def test_email_action_send_with_attachments():
    """Test sending email with attachments is rejected."""
    capability = _make_gmail_capability()
    mock_adapter = await _init_with_mock_adapter(capability)

    action = Action(
        capability="email",
        operation="send_email",
        parameters={
            "to": ["recipient@example.com"],
            "subject": "Test with attachment",
            "body": "See attached.",
            "attachments": [{"filename": "file.txt", "content": "data"}],
        },
    )

    result = await capability.execute_action(action)

    assert result.success is False
    assert "not yet supported" in result.error
    mock_adapter.send.assert_not_called()


@pytest.mark.asyncio
async def test_email_action_reply():
    """Test replying to email action"""
    capability = _make_gmail_capability()
    mock_adapter = await _init_with_mock_adapter(capability)

    action = Action(
        capability="email",
        operation="reply_to_email",
        parameters={
            "email_id": "123",
            "body": "Thank you for your email.",
        },
    )

    result = await capability.execute_action(action)

    assert result.success is True
    assert "replied_at" in result.metadata
    mock_adapter.reply.assert_called_once()


@pytest.mark.asyncio
async def test_email_action_forward():
    """Test forwarding email action"""
    capability = _make_gmail_capability()
    mock_adapter = await _init_with_mock_adapter(capability)

    action = Action(
        capability="email",
        operation="forward_email",
        parameters={
            "email_id": "123",
            "to": ["colleague@example.com"],
            "comment": "FYI",
        },
    )

    result = await capability.execute_action(action)

    assert result.success is True
    assert "forwarded_at" in result.metadata
    mock_adapter.forward.assert_called_once()


@pytest.mark.asyncio
async def test_email_action_mark_read():
    """Test marking email as read"""
    capability = _make_gmail_capability()
    mock_adapter = await _init_with_mock_adapter(capability)

    action = Action(
        capability="email",
        operation="mark_read",
        parameters={"email_id": "123"},
    )

    result = await capability.execute_action(action)

    assert result.success is True
    mock_adapter.mark_read.assert_called_once_with("123")


@pytest.mark.asyncio
async def test_email_action_archive():
    """Test archiving email"""
    capability = _make_gmail_capability()
    mock_adapter = await _init_with_mock_adapter(capability)

    action = Action(
        capability="email",
        operation="archive",
        parameters={"email_id": "123"},
    )

    result = await capability.execute_action(action)

    assert result.success is True
    mock_adapter.archive.assert_called_once_with("123")


@pytest.mark.asyncio
async def test_email_action_send_failure():
    """Test send failure returns error from adapter"""
    capability = _make_gmail_capability()
    adapter = _make_mock_adapter(
        send_result=AdapterResult(success=False, error="Gmail send failed: quota exceeded")
    )
    await _init_with_mock_adapter(capability, adapter)

    action = Action(
        capability="email",
        operation="send_email",
        parameters={
            "to": ["recipient@example.com"],
            "subject": "Test",
            "body": "Test body",
        },
    )

    result = await capability.execute_action(action)

    assert result.success is False
    assert "Gmail send failed" in result.error


@pytest.mark.asyncio
async def test_email_action_unknown_operation():
    """Test unknown operation returns error"""
    capability = _make_gmail_capability()
    await _init_with_mock_adapter(capability)

    action = Action(
        capability="email",
        operation="unknown_operation",
        parameters={},
    )

    result = await capability.execute_action(action)

    assert result.success is False
    assert "Unknown operation" in result.error


@pytest.mark.asyncio
async def test_email_action_no_adapter():
    """Test actions fail gracefully when adapter is not set"""
    capability = _make_gmail_capability()
    capability._initialized = True  # Bypass init check but no adapter

    action = Action(
        capability="email",
        operation="send_email",
        parameters={
            "to": ["a@example.com"],
            "subject": "Test",
            "body": "Body",
        },
    )

    result = await capability.execute_action(action)
    assert result.success is False
    assert "not initialized" in result.error


# Test PII Redaction


def test_pii_redaction_hash_value():
    """Test _hash_value produces stable SHA256 hashes"""
    capability = _make_gmail_capability()

    hash1 = capability._hash_value("test@example.com")
    hash2 = capability._hash_value("test@example.com")
    assert hash1 == hash2
    assert len(hash1) == 8

    hash3 = capability._hash_value("different@example.com")
    assert hash1 != hash3


def test_pii_redaction_extract_domains():
    """Test _extract_domains extracts unique domains from email addresses"""
    capability = _make_gmail_capability()

    domains = capability._extract_domains(["user1@example.com"])
    assert domains == ["example.com"]

    domains = capability._extract_domains(["user1@example.com", "user2@example.com"])
    assert domains == ["example.com"]

    domains = capability._extract_domains(
        [
            "user1@example.com",
            "user2@test.com",
            "user3@example.com",
            "user4@another.org",
        ]
    )
    assert sorted(domains) == ["another.org", "example.com", "test.com"]

    domains = capability._extract_domains([])
    assert domains == []


def test_pii_redaction_redact_email_address():
    """Test _redact_email_address returns domain only"""
    capability = _make_gmail_capability()

    redacted = capability._redact_email_address("user@example.com")
    assert redacted == "example.com"

    redacted = capability._redact_email_address("notanemail")
    assert redacted == "[redacted]"


def test_pii_redaction_redact_email_id():
    """Test _redact_email_id returns 8-char hash"""
    capability = _make_gmail_capability()

    redacted = capability._redact_email_id("message-id-12345")
    assert len(redacted) == 8
    assert redacted == capability._hash_value("message-id-12345")


def test_pii_redaction_redact_subject():
    """Test _redact_subject returns 8-char hash"""
    capability = _make_gmail_capability()

    redacted = capability._redact_subject("Confidential meeting notes")
    assert len(redacted) == 8
    assert redacted == capability._hash_value("Confidential meeting notes")


def test_email_config_log_pii_default():
    """Test EmailConfig defaults to log_pii=False"""
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )
    assert config.log_pii is False


def test_email_config_log_pii_explicit():
    """Test EmailConfig can enable log_pii=True"""
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
        log_pii=True,
    )
    assert config.log_pii is True


def test_email_capability_repr():
    """Test EmailCapability string representation"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)

    repr_str = repr(capability)
    assert "EmailCapability" in repr_str
    assert "email" in repr_str
    assert str(employee_id) in repr_str
    assert "initialized=False" in repr_str


# ==========================================
# Perception with adapter
# ==========================================


@pytest.mark.asyncio
async def test_perception_with_emails():
    """Test perception creates observations from adapter emails."""
    capability = _make_gmail_capability()

    test_emails = [
        Email(
            id="msg1",
            thread_id="t1",
            from_addr="customer@example.com",
            to_addrs=["test@gmail.com"],
            cc_addrs=[],
            subject="URGENT help needed",
            body="System is down!",
            html_body=None,
            timestamp=datetime.now(UTC),
            attachments=[],
            in_reply_to=None,
            labels=[],
            is_read=False,
        ),
    ]
    adapter = _make_mock_adapter(fetch_emails_result=test_emails)
    await _init_with_mock_adapter(capability, adapter)

    observations = await capability.perceive()

    assert len(observations) == 1
    assert observations[0].content["email_id"] == "msg1"
    assert observations[0].content["priority"] == EmailPriority.URGENT
    adapter.fetch_emails.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_new_emails_passes_structured_params():
    """Test _fetch_new_emails passes structured parameters to adapter."""
    capability = _make_gmail_capability()
    adapter = _make_mock_adapter()
    await _init_with_mock_adapter(capability, adapter)

    await capability._fetch_new_emails()

    call_args = adapter.fetch_emails.call_args
    assert call_args.kwargs["unread_only"] is True
    assert call_args.kwargs["since"] is None
    assert call_args.kwargs["max_results"] == 50


@pytest.mark.asyncio
async def test_fetch_new_emails_passes_since_after_first_check():
    """Test _fetch_new_emails passes last_check as since parameter."""
    capability = _make_gmail_capability()
    adapter = _make_mock_adapter()
    await _init_with_mock_adapter(capability, adapter)

    # Simulate a previous check
    check_time = datetime.now(UTC)
    capability._last_check = check_time

    await capability._fetch_new_emails()

    call_args = adapter.fetch_emails.call_args
    assert call_args.kwargs["since"] is check_time


@pytest.mark.asyncio
async def test_fetch_new_emails_no_adapter():
    """Test _fetch_new_emails returns empty when no adapter."""
    capability = _make_gmail_capability()
    result = await capability._fetch_new_emails()
    assert result == []


# ==========================================
# Forward with signature
# ==========================================


@pytest.mark.asyncio
async def test_email_forward_with_signature_no_comment():
    """Test forward appends signature even when comment is None."""
    capability = _make_gmail_capability(signature="Best regards,\nTest User")
    mock_adapter = await _init_with_mock_adapter(capability)

    action = Action(
        capability="email",
        operation="forward_email",
        parameters={
            "email_id": "123",
            "to": ["colleague@example.com"],
        },
    )

    result = await capability.execute_action(action)

    assert result.success is True
    # Signature should be passed as body to adapter
    call_args = mock_adapter.forward.call_args
    body_arg = call_args[0][2]  # positional arg: message_id, to, body
    assert "Best regards" in body_arg


@pytest.mark.asyncio
async def test_email_forward_with_signature_and_comment():
    """Test forward appends signature after comment."""
    capability = _make_gmail_capability(signature="Best regards,\nTest User")
    mock_adapter = await _init_with_mock_adapter(capability)

    action = Action(
        capability="email",
        operation="forward_email",
        parameters={
            "email_id": "123",
            "to": ["colleague@example.com"],
            "comment": "FYI - take a look",
        },
    )

    result = await capability.execute_action(action)

    assert result.success is True
    call_args = mock_adapter.forward.call_args
    body_arg = call_args[0][2]
    assert "FYI - take a look" in body_arg
    assert "Best regards" in body_arg
    # Comment should appear before signature
    assert body_arg.index("FYI") < body_arg.index("Best regards")


# ==========================================
# Shutdown
# ==========================================


@pytest.mark.asyncio
async def test_email_capability_shutdown():
    """Test shutdown calls adapter shutdown and clears state."""
    capability = _make_gmail_capability()
    mock_adapter = await _init_with_mock_adapter(capability)

    assert capability._initialized is True
    assert capability._adapter is not None

    await capability.shutdown()

    mock_adapter.shutdown.assert_called_once()
    assert capability._adapter is None
    assert capability._initialized is False


@pytest.mark.asyncio
async def test_email_capability_shutdown_no_adapter():
    """Test shutdown is safe when no adapter is set."""
    capability = _make_gmail_capability()
    # No adapter set — should not raise
    await capability.shutdown()
    assert capability._initialized is False


# ==========================================
# Error resilience
# ==========================================


@pytest.mark.asyncio
async def test_perception_error_returns_empty_list():
    """Perceive returns empty list (not raises) when adapter fails."""
    capability = _make_gmail_capability()
    adapter = _make_mock_adapter()
    adapter.fetch_emails = AsyncMock(side_effect=Exception("API timeout"))
    await _init_with_mock_adapter(capability, adapter)

    observations = await capability.perceive()

    assert observations == []
    # last_check should NOT be updated on failure
    assert capability._last_check is None


@pytest.mark.asyncio
async def test_initialize_no_credentials_raises():
    """Initialize raises RuntimeError when no credentials are available."""
    config = EmailConfig(
        provider=EmailProvider.GMAIL,
        email_address="test@gmail.com",
        use_integration_service=False,
        credentials=None,
    )
    capability = EmailCapability(uuid4(), uuid4(), config)
    with pytest.raises(RuntimeError, match="No credentials available"):
        await capability.initialize()
