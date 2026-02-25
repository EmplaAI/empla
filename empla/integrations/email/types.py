"""
Shared email types used by both capabilities (Layer 1) and adapters (Layer 2).

These types are intentionally in the integrations layer to avoid circular
imports. The capabilities layer re-exports them for convenience.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class EmailProvider(str, Enum):
    """Supported email providers"""

    MICROSOFT_GRAPH = "microsoft_graph"  # M365, Outlook
    GMAIL = "gmail"  # Google Workspace


class EmailPriority(str, Enum):
    """Email priority classification"""

    URGENT = "urgent"  # Customer issues, direct requests from manager
    HIGH = "high"  # Lead inquiries, important updates
    MEDIUM = "medium"  # General inquiries, internal updates
    LOW = "low"  # Newsletters, FYIs
    SPAM = "spam"  # Junk, irrelevant


@dataclass
class Email:
    """Email message representation"""

    id: str
    thread_id: str | None
    from_addr: str
    to_addrs: list[str]
    cc_addrs: list[str]
    subject: str
    body: str  # Plain text
    html_body: str | None  # HTML version
    timestamp: datetime
    attachments: list[dict[str, Any]]
    in_reply_to: str | None
    labels: list[str]
    is_read: bool
