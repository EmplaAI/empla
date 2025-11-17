"""
Unit tests for EmailCapability.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from typing import List

from empla.capabilities.email import (
    EmailCapability,
    EmailConfig,
    EmailProvider,
    EmailPriority,
    Email,
)
from empla.capabilities.base import (
    CapabilityType,
    CapabilityConfig,
    Observation,
    Action,
    ActionResult,
)


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


# Test EmailCapability


@pytest.mark.asyncio
async def test_email_capability_initialization():
    """Test EmailCapability initialization"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)

    assert capability.tenant_id == tenant_id
    assert capability.employee_id == employee_id
    assert capability.config == config
    assert capability.capability_type == CapabilityType.EMAIL
    assert capability._initialized is False
    assert capability._last_check is None
    assert capability._client is None

    # Initialize
    await capability.initialize()

    assert capability._initialized is True
    assert capability.is_healthy() is True


@pytest.mark.asyncio
async def test_email_capability_gmail_initialization():
    """Test EmailCapability initialization with Gmail provider"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.GMAIL,
        email_address="test@gmail.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

    assert capability._initialized is True


@pytest.mark.asyncio
async def test_email_capability_invalid_provider():
    """Test EmailCapability with invalid provider raises error"""
    tenant_id = uuid4()
    employee_id = uuid4()

    # Manually create config with invalid provider
    config = CapabilityConfig()
    config.provider = "invalid_provider"
    config.email_address = "test@example.com"
    config.credentials = {}

    # Cast to EmailConfig type for EmailCapability
    capability = EmailCapability(tenant_id, employee_id, config)

    with pytest.raises(ValueError, match="Unsupported provider"):
        await capability.initialize()


@pytest.mark.asyncio
async def test_email_capability_perception_not_initialized():
    """Test perception returns empty when not initialized"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)

    # Don't initialize
    observations = await capability.perceive()

    assert len(observations) == 0


@pytest.mark.asyncio
async def test_email_capability_perception_no_emails():
    """Test perception with no new emails"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

    # _fetch_new_emails returns empty list (placeholder)
    observations = await capability.perceive()

    assert len(observations) == 0
    assert capability._last_check is not None


@pytest.mark.asyncio
async def test_email_triage_urgent():
    """Test email triage classifies urgent emails correctly"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

    # Create urgent email
    email = Email(
        id="1",
        thread_id=None,
        from_addr="customer@example.com",
        to_addrs=["test@example.com"],
        cc_addrs=[],
        subject="URGENT: System down",
        body="Our production system is completely down!",
        html_body=None,
        timestamp=datetime.now(timezone.utc),
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
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

    email = Email(
        id="2",
        thread_id=None,
        from_addr="lead@prospect.com",
        to_addrs=["test@example.com"],
        cc_addrs=[],
        subject="Important question about your product",
        body="I have an important question about pricing.",
        html_body=None,
        timestamp=datetime.now(timezone.utc),
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
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

    email = Email(
        id="3",
        thread_id=None,
        from_addr="colleague@example.com",
        to_addrs=["test@example.com"],
        cc_addrs=[],
        subject="Weekly update",
        body="Here's the weekly update on project status.",
        html_body=None,
        timestamp=datetime.now(timezone.utc),
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
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

    email = Email(
        id="4",
        thread_id=None,
        from_addr="customer@example.com",
        to_addrs=["test@example.com"],
        cc_addrs=[],
        subject="Question",
        body="Can you help me with this issue?",
        html_body=None,
        timestamp=datetime.now(timezone.utc),
        attachments=[],
        in_reply_to=None,
        labels=[],
        is_read=False,
    )

    requires_response = await capability._requires_response(email)

    assert requires_response is True


@pytest.mark.asyncio
async def test_email_requires_response_request():
    """Test requires_response identifies requests"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

    email = Email(
        id="5",
        thread_id=None,
        from_addr="manager@example.com",
        to_addrs=["test@example.com"],
        cc_addrs=[],
        subject="Request",
        body="Please send me the report by end of day.",
        html_body=None,
        timestamp=datetime.now(timezone.utc),
        attachments=[],
        in_reply_to=None,
        labels=[],
        is_read=False,
    )

    requires_response = await capability._requires_response(email)

    assert requires_response is True


@pytest.mark.asyncio
async def test_email_requires_response_fyi():
    """Test requires_response identifies FYIs"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

    email = Email(
        id="6",
        thread_id=None,
        from_addr="colleague@example.com",
        to_addrs=["test@example.com"],
        cc_addrs=[],
        subject="FYI: Meeting rescheduled",
        body="The meeting has been moved to next week.",
        html_body=None,
        timestamp=datetime.now(timezone.utc),
        attachments=[],
        in_reply_to=None,
        labels=[],
        is_read=False,
    )

    requires_response = await capability._requires_response(email)

    assert requires_response is False


def test_priority_to_int():
    """Test priority to int conversion"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)

    assert capability._priority_to_int(EmailPriority.URGENT) == 10
    assert capability._priority_to_int(EmailPriority.HIGH) == 7
    assert capability._priority_to_int(EmailPriority.MEDIUM) == 5
    assert capability._priority_to_int(EmailPriority.LOW) == 2
    assert capability._priority_to_int(EmailPriority.SPAM) == 1


# Test Email Actions


@pytest.mark.asyncio
async def test_email_action_send():
    """Test sending email action"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

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


@pytest.mark.asyncio
async def test_email_action_send_with_signature():
    """Test sending email with signature"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
        signature="Best regards,\nTest User",
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

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


@pytest.mark.asyncio
async def test_email_action_reply():
    """Test replying to email action"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

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


@pytest.mark.asyncio
async def test_email_action_forward():
    """Test forwarding email action"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

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


@pytest.mark.asyncio
async def test_email_action_mark_read():
    """Test marking email as read"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

    action = Action(
        capability="email",
        operation="mark_read",
        parameters={"email_id": "123"},
    )

    result = await capability.execute_action(action)

    assert result.success is True


@pytest.mark.asyncio
async def test_email_action_archive():
    """Test archiving email"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

    action = Action(
        capability="email",
        operation="archive",
        parameters={"email_id": "123"},
    )

    result = await capability.execute_action(action)

    assert result.success is True


@pytest.mark.asyncio
async def test_email_action_unknown_operation():
    """Test unknown operation returns error"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)
    await capability.initialize()

    action = Action(
        capability="email",
        operation="unknown_operation",
        parameters={},
    )

    result = await capability.execute_action(action)

    assert result.success is False
    assert "Unknown operation" in result.error


# Test PII Redaction


def test_pii_redaction_hash_value():
    """Test _hash_value produces stable SHA256 hashes"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)

    # Hash should be stable (same input = same output)
    hash1 = capability._hash_value("test@example.com")
    hash2 = capability._hash_value("test@example.com")
    assert hash1 == hash2

    # Hash should be 8 characters
    assert len(hash1) == 8

    # Different inputs should produce different hashes
    hash3 = capability._hash_value("different@example.com")
    assert hash1 != hash3


def test_pii_redaction_extract_domains():
    """Test _extract_domains extracts unique domains from email addresses"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)

    # Single domain
    domains = capability._extract_domains(["user1@example.com"])
    assert domains == ["example.com"]

    # Multiple addresses, same domain
    domains = capability._extract_domains(
        ["user1@example.com", "user2@example.com"]
    )
    assert domains == ["example.com"]

    # Multiple domains
    domains = capability._extract_domains(
        [
            "user1@example.com",
            "user2@test.com",
            "user3@example.com",
            "user4@another.org",
        ]
    )
    assert sorted(domains) == ["another.org", "example.com", "test.com"]

    # Empty list
    domains = capability._extract_domains([])
    assert domains == []


def test_pii_redaction_redact_email_address():
    """Test _redact_email_address returns domain only"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)

    # Normal email address
    redacted = capability._redact_email_address("user@example.com")
    assert redacted == "example.com"

    # Invalid email (no @)
    redacted = capability._redact_email_address("notanemail")
    assert redacted == "[redacted]"


def test_pii_redaction_redact_email_id():
    """Test _redact_email_id returns 8-char hash"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)

    redacted = capability._redact_email_id("message-id-12345")
    assert len(redacted) == 8
    assert redacted == capability._hash_value("message-id-12345")


def test_pii_redaction_redact_subject():
    """Test _redact_subject returns 8-char hash"""
    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={},
    )

    capability = EmailCapability(tenant_id, employee_id, config)

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
    assert "CapabilityType.EMAIL" in repr_str
    assert str(employee_id) in repr_str
    assert "initialized=False" in repr_str
