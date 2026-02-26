"""
Shared email types used by both capabilities (Layer 1) and adapters (Layer 2).

These types are intentionally in the integrations layer to avoid circular
imports. The capabilities layer imports them directly.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class EmailProvider(StrEnum):
    """Supported email providers"""

    MICROSOFT_GRAPH = "microsoft_graph"  # M365, Outlook
    GMAIL = "gmail"  # Google Workspace


class EmailPriority(StrEnum):
    """Email priority classification"""

    URGENT = "urgent"  # Customer issues, direct requests from manager
    HIGH = "high"  # Lead inquiries, important updates
    MEDIUM = "medium"  # General inquiries, internal updates
    LOW = "low"  # Newsletters, FYIs
    SPAM = "spam"  # Junk, irrelevant


class Attachment(BaseModel):
    """Email attachment metadata."""

    filename: str
    mime_type: str
    size: int = 0
    attachment_id: str | None = None


class Email(BaseModel):
    """Email message representation."""

    id: str
    thread_id: str | None
    from_addr: str
    to_addrs: list[str]
    cc_addrs: list[str]
    subject: str
    body: str  # Plain text
    html_body: str | None  # HTML version
    timestamp: datetime
    attachments: list[Attachment] = []
    in_reply_to: str | None = None
    labels: list[str] = []
    is_read: bool = False
