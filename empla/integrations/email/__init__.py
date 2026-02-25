"""
Email integration adapters.

Provides provider-specific email adapters (Gmail, Outlook) behind
a common EmailAdapter ABC. Shared types (Email, EmailProvider, EmailPriority)
live in types.py and are importable from both layers.
"""

from empla.integrations.email.base import EmailAdapter
from empla.integrations.email.factory import create_email_adapter
from empla.integrations.email.gmail import GmailEmailAdapter
from empla.integrations.email.types import Email, EmailPriority, EmailProvider

__all__ = [
    "Email",
    "EmailAdapter",
    "EmailPriority",
    "EmailProvider",
    "GmailEmailAdapter",
    "create_email_adapter",
]
