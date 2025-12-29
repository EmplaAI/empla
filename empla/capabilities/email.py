"""
Email Capability

Enables digital employees to interact via email - monitor inbox, triage messages,
compose responses, and send emails.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from empla.capabilities.base import (
    Action,
    ActionResult,
    BaseCapability,
    CapabilityConfig,
    CapabilityType,
    Observation,
)

logger = logging.getLogger(__name__)


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


class EmailConfig(CapabilityConfig):
    """Email capability configuration"""

    provider: EmailProvider
    email_address: str

    # Provider credentials (stored securely)
    credentials: dict[str, Any]

    # Monitoring settings
    check_interval_seconds: int = 60
    monitor_folders: list[str] | None = None

    # Triage settings
    auto_triage: bool = True
    priority_keywords: dict[str, list[str]] | None = None

    # Response settings
    auto_respond: bool = False  # Require approval before sending
    signature: str | None = None

    # Privacy settings
    log_pii: bool = False  # If True, log full PII (email addresses, subjects, etc.)

    def __init__(self, **data: Any) -> None:
        """Initialize with sensible defaults"""
        if "monitor_folders" not in data or data["monitor_folders"] is None:
            data["monitor_folders"] = ["inbox", "sent"]

        if "priority_keywords" not in data or data["priority_keywords"] is None:
            data["priority_keywords"] = {
                EmailPriority.URGENT: ["urgent", "asap", "critical", "down"],
                EmailPriority.HIGH: ["important", "need", "question"],
            }

        super().__init__(**data)


class EmailCapability(BaseCapability):
    """
    Email capability implementation.

    Provides:
    - Inbox monitoring
    - Intelligent triage
    - Email composition
    - Sending with tracking
    """

    def __init__(self, tenant_id: UUID, employee_id: UUID, config: EmailConfig) -> None:
        """
        Initialize EmailCapability.

        Parameters:
            tenant_id (UUID): Tenant identifier
            employee_id (UUID): Employee identifier
            config (EmailConfig): Email configuration including provider and credentials
        """
        super().__init__(tenant_id, employee_id, config)
        self.config: EmailConfig = config
        self._last_check: datetime | None = None
        self._client = None  # Email provider client

    @property
    def capability_type(self) -> CapabilityType:
        """
        Return the capability type for this capability.

        Returns:
            CapabilityType.EMAIL
        """
        return CapabilityType.EMAIL

    async def initialize(self) -> None:
        """
        Initialize email client based on configured provider.

        Raises:
            ValueError: If provider is not supported
        """
        if self.config.provider == EmailProvider.MICROSOFT_GRAPH:
            self._client = await self._init_microsoft_graph()
        elif self.config.provider == EmailProvider.GMAIL:
            self._client = await self._init_gmail()
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

        self._initialized = True
        logger.info(
            "Email capability initialized",
            extra={
                "employee_id": str(self.employee_id),
                "email": (
                    self.config.email_address
                    if self.config.log_pii
                    else self._redact_email_address(self.config.email_address)
                ),
                "provider": self.config.provider,
            },
        )

    async def _init_microsoft_graph(self) -> None:
        """
        Initialize Microsoft Graph client.

        TODO: Implement Microsoft Graph authentication
        Use OAuth2 with delegated permissions

        Returns:
            Microsoft Graph client instance
        """
        # TODO: Implement Microsoft Graph authentication
        # from msgraph.core import GraphClient
        # return GraphClient(credentials=self.config.credentials)
        logger.info("Microsoft Graph client initialization - placeholder")

    async def _init_gmail(self) -> None:
        """
        Initialize Gmail client.

        TODO: Implement Gmail API authentication

        Returns:
            Gmail client instance
        """
        # TODO: Implement Gmail API authentication
        # from googleapiclient.discovery import build
        # return build('gmail', 'v1', credentials=self.config.credentials)
        logger.info("Gmail client initialization - placeholder")

    async def perceive(self) -> list[Observation]:
        """
        Check inbox for new emails and create observations.

        Called periodically by proactive loop to monitor email environment.

        Returns:
            List[Observation]: Observations for each new email detected
        """
        if not self._initialized:
            logger.warning(
                "Email perception called before initialization",
                extra={"employee_id": str(self.employee_id)},
            )
            return []

        observations = []

        try:
            # Get new emails since last check
            new_emails = await self._fetch_new_emails()

            logger.debug(
                f"Fetched {len(new_emails)} new emails",
                extra={
                    "employee_id": str(self.employee_id),
                    "email_count": len(new_emails),
                },
            )

            # Triage each email
            for email in new_emails:
                priority = await self._triage_email(email)

                observation = Observation(
                    source="email",
                    type="new_email",
                    timestamp=email.timestamp,
                    priority=self._priority_to_int(priority),
                    data={
                        "email_id": email.id,
                        "from": email.from_addr,
                        "subject": email.subject,
                        "priority": priority,
                        "requires_response": await self._requires_response(email),
                    },
                    requires_action=(priority in [EmailPriority.URGENT, EmailPriority.HIGH]),
                )

                observations.append(observation)

            self._last_check = datetime.now(UTC)

        except Exception as e:
            logger.error(
                "Email perception failed",
                exc_info=True,
                extra={
                    "employee_id": str(self.employee_id),
                    "error": str(e),
                },
            )

        return observations

    async def _fetch_new_emails(self) -> list[Email]:
        """
        Fetch new emails from provider.

        TODO: Implement provider-specific email fetching
        Filter by: unread, newer than last_check

        Returns:
            List[Email]: New emails since last check
        """
        # TODO: Implement provider-specific email fetching
        # For now, return empty list (placeholder)
        logger.debug(
            "Fetching new emails - placeholder implementation",
            extra={"employee_id": str(self.employee_id)},
        )
        return []

    async def _triage_email(self, email: Email) -> EmailPriority:
        """
        Intelligently classify email priority.

        Classifies email priority based on:
        - Sender (customer, manager, lead)
        - Subject keywords
        - Content analysis
        - Thread context

        Parameters:
            email (Email): Email to triage

        Returns:
            EmailPriority: Classified priority level
        """
        # Check urgent keywords
        text = f"{email.subject} {email.body}".lower()

        # Check configured priority keywords (use empty dict if None for safety)
        for priority_str, keywords in (self.config.priority_keywords or {}).items():
            # Convert string to EmailPriority enum
            priority = EmailPriority(priority_str)
            if any(kw in text for kw in keywords):
                logger.debug(
                    f"Email triaged as {priority} based on keywords",
                    extra={
                        "employee_id": str(self.employee_id),
                        "email_id_hash": (
                            email.id if self.config.log_pii else self._redact_email_id(email.id)
                        ),
                        "priority": priority,
                    },
                )
                return priority

        # TODO: Check sender relationship
        # - Use memory system to check relationship
        # - Is this a customer?
        # - Is this my manager?
        # - Is this a hot lead?

        # Default to medium
        logger.debug(
            "Email triaged as MEDIUM (default)",
            extra={
                "employee_id": str(self.employee_id),
                "email_id_hash": (
                    email.id if self.config.log_pii else self._redact_email_id(email.id)
                ),
            },
        )
        return EmailPriority.MEDIUM

    async def _requires_response(self, email: Email) -> bool:
        """
        Determine if email requires a response.

        Heuristics:
        - Questions typically need responses
        - Direct requests need responses
        - FYIs typically don't need responses

        Parameters:
            email (Email): Email to analyze

        Returns:
            bool: True if email likely requires response
        """
        # Questions typically need responses
        if "?" in email.body:
            return True

        # Direct requests
        request_keywords = ["can you", "could you", "please", "need"]
        text = email.body.lower()
        if any(kw in text for kw in request_keywords):
            return True

        # FYIs typically don't need responses
        if email.subject.lower().startswith("fyi"):
            return False

        return False

    def _priority_to_int(self, priority: EmailPriority) -> int:
        """
        Convert email priority to observation priority (1-10).

        Parameters:
            priority (EmailPriority): Email priority enum

        Returns:
            int: Observation priority score (1-10)
        """
        mapping = {
            EmailPriority.URGENT: 10,
            EmailPriority.HIGH: 7,
            EmailPriority.MEDIUM: 5,
            EmailPriority.LOW: 2,
            EmailPriority.SPAM: 1,
        }
        return mapping.get(priority, 5)

    # PII Redaction Helpers

    def _hash_value(self, value: str) -> str:
        """
        Compute stable SHA256 hash of a value for PII-safe logging.

        Parameters:
            value (str): Value to hash

        Returns:
            str: First 8 characters of SHA256 hex digest
        """
        return hashlib.sha256(value.encode()).hexdigest()[:8]

    def _extract_domains(self, addresses: list[str]) -> list[str]:
        """
        Extract unique domains from email addresses.

        Parameters:
            addresses (List[str]): Email addresses

        Returns:
            List[str]: Unique domain names
        """
        domains = set()
        for addr in addresses:
            if "@" in addr:
                domains.add(addr.split("@")[1])
        return sorted(domains)

    def _redact_email_id(self, email_id: str) -> str:
        """
        Redact email ID for PII-safe logging.

        Parameters:
            email_id (str): Email ID

        Returns:
            str: Hashed email ID (first 8 chars of SHA256)
        """
        return self._hash_value(email_id)

    def _redact_subject(self, subject: str) -> str:
        """
        Redact email subject for PII-safe logging.

        Parameters:
            subject (str): Email subject

        Returns:
            str: Hashed subject (first 8 chars of SHA256)
        """
        return self._hash_value(subject)

    def _redact_email_address(self, email: str) -> str:
        """
        Redact email address for PII-safe logging.

        Parameters:
            email (str): Email address

        Returns:
            str: Domain only (e.g., "user@example.com" -> "example.com")
        """
        if "@" in email:
            return email.split("@")[1]
        return "[redacted]"

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        """
        Execute email actions.

        Supported operations:
        - send_email: Send new email
        - reply_to_email: Reply to existing email
        - forward_email: Forward email
        - mark_read: Mark email as read
        - archive: Archive email

        Parameters:
            action (Action): Action to execute with parameters

        Returns:
            ActionResult: Result of action execution
        """
        operation = action.operation
        params = action.parameters

        if operation == "send_email":
            return await self._send_email(
                to=params["to"],
                subject=params["subject"],
                body=params["body"],
                cc=params.get("cc", []),
                attachments=params.get("attachments", []),
            )

        if operation == "reply_to_email":
            return await self._reply_to_email(
                email_id=params["email_id"],
                body=params["body"],
                cc=params.get("cc", []),
            )

        if operation == "forward_email":
            return await self._forward_email(
                email_id=params["email_id"],
                to=params["to"],
                comment=params.get("comment"),
            )

        if operation == "mark_read":
            return await self._mark_read(params["email_id"])

        if operation == "archive":
            return await self._archive(params["email_id"])

        return ActionResult(success=False, error=f"Unknown operation: {operation}")

    async def _send_email(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> ActionResult:
        """
        Send new email.

        TODO: Implement actual email sending via provider

        Parameters:
            to (List[str]): Recipient email addresses
            subject (str): Email subject
            body (str): Email body (plain text)
            cc (List[str], optional): CC recipients
            attachments (List[Dict], optional): Email attachments

        Returns:
            ActionResult: Success with metadata or error
        """
        # Add signature if configured
        if self.config.signature:
            body = f"{body}\n\n{self.config.signature}"

        # TODO: Use provider client to send
        # Record in memory system

        logger.info(
            "Email sent (placeholder)",
            extra={
                "employee_id": str(self.employee_id),
                "recipient_count": len(to),
                "recipient_domains": (to if self.config.log_pii else self._extract_domains(to)),
                "subject_hash": (subject if self.config.log_pii else self._redact_subject(subject)),
                "cc_count": len(cc) if cc else 0,
                "has_attachments": bool(attachments),
            },
        )

        return ActionResult(
            success=True,
            metadata={"sent_at": datetime.now(UTC).isoformat()},
        )

    async def _reply_to_email(
        self, email_id: str, body: str, cc: list[str] | None = None
    ) -> ActionResult:
        """
        Reply to existing email.

        TODO: Implement email reply via provider

        Parameters:
            email_id (str): ID of email to reply to
            body (str): Reply body
            cc (List[str], optional): Additional CC recipients

        Returns:
            ActionResult: Success with metadata or error
        """
        # TODO: Fetch original email, create reply
        logger.info(
            "Email reply (placeholder)",
            extra={
                "employee_id": str(self.employee_id),
                "email_id_hash": (
                    email_id if self.config.log_pii else self._redact_email_id(email_id)
                ),
                "cc_count": len(cc) if cc else 0,
            },
        )

        return ActionResult(
            success=True,
            metadata={"replied_at": datetime.now(UTC).isoformat()},
        )

    async def _forward_email(
        self,
        email_id: str,
        to: list[str],
        comment: str | None = None,
    ) -> ActionResult:
        """
        Forward email to others.

        TODO: Implement email forwarding via provider

        Parameters:
            email_id (str): ID of email to forward
            to (List[str]): Recipient email addresses
            comment (str, optional): Comment to add when forwarding

        Returns:
            ActionResult: Success with metadata or error
        """
        # TODO: Fetch original email, forward with comment
        logger.info(
            "Email forward (placeholder)",
            extra={
                "employee_id": str(self.employee_id),
                "email_id_hash": (
                    email_id if self.config.log_pii else self._redact_email_id(email_id)
                ),
                "recipient_count": len(to),
                "recipient_domains": (to if self.config.log_pii else self._extract_domains(to)),
                "has_comment": comment is not None,
            },
        )

        return ActionResult(
            success=True,
            metadata={"forwarded_at": datetime.now(UTC).isoformat()},
        )

    async def _mark_read(self, email_id: str) -> ActionResult:
        """
        Mark email as read.

        TODO: Implement via provider

        Parameters:
            email_id (str): ID of email to mark as read

        Returns:
            ActionResult: Success or error
        """
        # TODO: Update email status via provider
        logger.debug(
            "Email marked as read (placeholder)",
            extra={
                "employee_id": str(self.employee_id),
                "email_id_hash": (
                    email_id if self.config.log_pii else self._redact_email_id(email_id)
                ),
            },
        )

        return ActionResult(success=True)

    async def _archive(self, email_id: str) -> ActionResult:
        """
        Archive email.

        TODO: Implement via provider

        Parameters:
            email_id (str): ID of email to archive

        Returns:
            ActionResult: Success or error
        """
        # TODO: Move to archive folder via provider
        logger.debug(
            "Email archived (placeholder)",
            extra={
                "employee_id": str(self.employee_id),
                "email_id_hash": (
                    email_id if self.config.log_pii else self._redact_email_id(email_id)
                ),
            },
        )

        return ActionResult(success=True)
