"""
Email adapter abstract base class.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from empla.integrations.base import AdapterResult
from empla.integrations.email.types import Email


class EmailAdapter(ABC):
    """Abstract base class for email provider adapters.

    Each provider (Gmail, Outlook, etc.) implements this interface.
    Adapters receive pre-authenticated credentials from Layer 1,
    which gets them from Layer 3.
    """

    @abstractmethod
    async def initialize(self, credentials: dict[str, Any]) -> None:
        """Initialize the provider client with credentials.

        Args:
            credentials: OAuth credentials with access_token, refresh_token, etc.

        Raises:
            RuntimeError: If the client cannot be initialized.
        """

    @abstractmethod
    async def fetch_emails(
        self,
        *,
        unread_only: bool = True,
        since: datetime | None = None,
        max_results: int = 50,
    ) -> list[Email]:
        """Fetch emails matching the given criteria.

        Each adapter translates these structured parameters into its
        provider-specific query format (Gmail search operators, MS Graph
        OData filters, etc.).

        Args:
            unread_only: Only return unread emails.
            since: Only return emails received after this timestamp.
            max_results: Maximum number of emails to return.

        Returns:
            List of Email objects.
        """

    @abstractmethod
    async def fetch_message(self, message_id: str) -> Email | None:
        """Fetch a single email by ID.

        Args:
            message_id: Provider-specific message ID.

        Returns:
            Email object or None if not found.
        """

    @abstractmethod
    async def send(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
    ) -> AdapterResult:
        """Send a new email.

        Args:
            to: Recipient email addresses.
            subject: Email subject.
            body: Email body (plain text).
            cc: CC recipients.

        Returns:
            AdapterResult with message_id in data on success.
        """

    @abstractmethod
    async def reply(
        self,
        message_id: str,
        body: str,
        cc: list[str] | None = None,
    ) -> AdapterResult:
        """Reply to an existing email.

        Args:
            message_id: ID of the email to reply to.
            body: Reply body.
            cc: Additional CC recipients.

        Returns:
            AdapterResult with message_id in data on success.
        """

    @abstractmethod
    async def forward(
        self,
        message_id: str,
        to: list[str],
        body: str | None = None,
    ) -> AdapterResult:
        """Forward an email.

        Args:
            message_id: ID of the email to forward.
            to: Recipient email addresses.
            body: Optional comment to add when forwarding.

        Returns:
            AdapterResult with message_id in data on success.
        """

    @abstractmethod
    async def mark_read(self, message_id: str) -> AdapterResult:
        """Mark an email as read.

        Args:
            message_id: ID of the email to mark as read.

        Returns:
            AdapterResult with success status.
        """

    @abstractmethod
    async def archive(self, message_id: str) -> AdapterResult:
        """Archive an email.

        Args:
            message_id: ID of the email to archive.

        Returns:
            AdapterResult with success status.
        """

    async def shutdown(self) -> None:
        """Clean up adapter resources. Default is no-op."""
