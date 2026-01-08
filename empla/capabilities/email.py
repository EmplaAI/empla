"""
Email Capability

Enables digital employees to interact via email - monitor inbox, triage messages,
compose responses, and send emails.

Supports two credential modes:
1. Integration Service (recommended): Credentials stored securely via IntegrationService
2. Direct Config: Credentials passed directly in config (for testing/simulation)
"""

import asyncio
import base64
import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.mime.text import MIMEText
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from empla.capabilities.base import (
    CAPABILITY_EMAIL,
    Action,
    ActionResult,
    BaseCapability,
    CapabilityConfig,
    Observation,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from empla.services.integrations import IntegrationService

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

    # Credential source: use integration service (recommended) or direct config
    use_integration_service: bool = True

    # Provider credentials (only used if use_integration_service=False)
    # When using integration service, credentials are fetched automatically
    credentials: dict[str, Any] | None = None

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

    Credential Modes:
    1. Integration Service (default): Credentials fetched from IntegrationService
       - Requires integration_service and session to be set
       - Supports automatic token refresh
    2. Direct Config: Credentials in config.credentials
       - For testing/simulation
       - Set use_integration_service=False
    """

    def __init__(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        config: EmailConfig,
        integration_service: "IntegrationService | None" = None,
        session: "AsyncSession | None" = None,
    ) -> None:
        """
        Initialize EmailCapability.

        Parameters:
            tenant_id (UUID): Tenant identifier
            employee_id (UUID): Employee identifier
            config (EmailConfig): Email configuration
            integration_service (IntegrationService, optional): Service for credential management
            session (AsyncSession, optional): Database session for integration service
        """
        super().__init__(tenant_id, employee_id, config)
        self.config: EmailConfig = config
        self._last_check: datetime | None = None
        self._client = None  # Email provider client
        self._integration_service = integration_service
        self._session = session
        self._cached_credentials: dict[str, Any] | None = None
        self._credential_expires_at: datetime | None = None

    @property
    def capability_type(self) -> str:
        """
        Return the capability type for this capability.

        Returns:
            CAPABILITY_EMAIL
        """
        return CAPABILITY_EMAIL

    async def initialize(self) -> None:
        """
        Initialize email client based on configured provider.

        Gets credentials from integration service if enabled, then initializes
        the provider-specific client.

        Raises:
            ValueError: If provider is not supported
            RuntimeError: If credentials cannot be obtained
        """
        # Get credentials (from integration service or config)
        credentials = await self._get_credentials()

        if credentials is None:
            raise RuntimeError(
                "No credentials available. Either configure integration service "
                "or provide credentials in config."
            )

        if self.config.provider == EmailProvider.MICROSOFT_GRAPH:
            self._client = await self._init_microsoft_graph(credentials)
        elif self.config.provider == EmailProvider.GMAIL:
            self._client = await self._init_gmail(credentials)
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

        self._initialized = True

        # Get logging settings safely (may not be EmailConfig)
        log_pii = getattr(self.config, "log_pii", False)
        email_address = getattr(self.config, "email_address", "unknown")
        use_integration = getattr(self.config, "use_integration_service", False)

        logger.info(
            "Email capability initialized",
            extra={
                "employee_id": str(self.employee_id),
                "email": (email_address if log_pii else self._redact_email_address(email_address)),
                "provider": getattr(self.config, "provider", "unknown"),
                "credential_source": ("integration_service" if use_integration else "config"),
            },
        )

    async def _get_credentials(self) -> dict[str, Any] | None:
        """
        Get credentials for email provider.

        If use_integration_service is True, fetches from IntegrationService
        with automatic token refresh. Otherwise uses config.credentials.

        Credentials are cached for the session to reduce DB calls.

        Returns:
            dict: Credential data with access_token, refresh_token, etc.
            None: If no credentials available
        """
        # Use cached credentials if still valid
        if self._cached_credentials and self._credential_expires_at:
            # Check if credentials expire in the next 5 minutes
            buffer = datetime.now(UTC) + timedelta(minutes=5)
            if self._credential_expires_at > buffer:
                return self._cached_credentials

        # Check if config is an EmailConfig (has the integration service flag)
        use_integration = getattr(self.config, "use_integration_service", False)
        config_credentials = getattr(self.config, "credentials", None)

        # Direct config mode
        if not use_integration:
            return config_credentials

        # Integration service mode
        if not self._integration_service:
            logger.warning(
                "Integration service not configured but use_integration_service=True",
                extra={"employee_id": str(self.employee_id)},
            )
            # Fall back to config credentials if available
            return config_credentials

        # Map email provider to integration provider
        from empla.models.integration import IntegrationProvider

        provider_map = {
            EmailProvider.GMAIL: IntegrationProvider.GOOGLE_WORKSPACE,
            EmailProvider.MICROSOFT_GRAPH: IntegrationProvider.MICROSOFT_GRAPH,
        }
        integration_provider = provider_map.get(self.config.provider)

        if not integration_provider:
            logger.error(
                f"No integration provider for email provider {self.config.provider}",
                extra={"employee_id": str(self.employee_id)},
            )
            return None

        # Fetch from integration service
        result = await self._integration_service.get_credential_for_employee(
            tenant_id=self.tenant_id,
            employee_id=self.employee_id,
            provider=integration_provider,
            auto_refresh=True,  # Auto-refresh expiring tokens
        )

        if not result:
            logger.warning(
                f"No credential found for employee {self.employee_id} with {integration_provider}",
                extra={
                    "employee_id": str(self.employee_id),
                    "provider": integration_provider.value,
                },
            )
            return None

        _, credential, data = result

        # Cache credentials
        self._cached_credentials = data
        self._credential_expires_at = credential.expires_at

        logger.debug(
            "Retrieved credentials from integration service",
            extra={
                "employee_id": str(self.employee_id),
                "credential_id": str(credential.id),
                "expires_at": credential.expires_at.isoformat() if credential.expires_at else None,
            },
        )

        return data

    async def _init_microsoft_graph(self, credentials: dict[str, Any]) -> Any:
        """
        Initialize Microsoft Graph client.

        TODO: Implement Microsoft Graph authentication
        Use OAuth2 with delegated permissions

        Parameters:
            credentials: OAuth credentials with access_token

        Returns:
            Microsoft Graph client instance (None until implemented)
        """
        # TODO: Implement Microsoft Graph authentication
        # from msgraph.core import GraphClient
        # access_token = credentials.get("access_token")
        # return GraphClient(credential=access_token)
        logger.info(
            "Microsoft Graph client initialization - placeholder",
            extra={
                "has_access_token": "access_token" in credentials,
                "has_refresh_token": "refresh_token" in credentials,
            },
        )
        return None

    async def _init_gmail(self, credentials: dict[str, Any]) -> Any:
        """
        Initialize Gmail client using OAuth credentials.

        Parameters:
            credentials: OAuth credentials with access_token, refresh_token

        Returns:
            Gmail API service instance

        Raises:
            RuntimeError: If Gmail client cannot be initialized
        """
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            # Create credentials from OAuth tokens
            creds = Credentials(
                token=credentials.get("access_token"),
                refresh_token=credentials.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                # client_id and client_secret not needed for API calls
                # (they're only needed for token refresh, which IntegrationService handles)
            )

            # Build Gmail API service (synchronous, wrap in thread)
            def _build_service() -> Any:
                return build("gmail", "v1", credentials=creds, cache_discovery=False)

            service = await asyncio.to_thread(_build_service)

            logger.info(
                "Gmail client initialized successfully",
                extra={
                    "employee_id": str(self.employee_id),
                    "has_access_token": "access_token" in credentials,
                    "has_refresh_token": "refresh_token" in credentials,
                },
            )

            return service

        except ImportError as e:
            logger.error(
                "Gmail dependencies not installed. Run: pip install google-api-python-client google-auth",
                extra={"error": str(e)},
            )
            raise RuntimeError("Gmail dependencies not installed") from e
        except Exception as e:
            logger.error(
                "Failed to initialize Gmail client",
                exc_info=True,
                extra={"employee_id": str(self.employee_id), "error": str(e)},
            )
            raise RuntimeError(f"Gmail initialization failed: {e}") from e

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
                    employee_id=self.employee_id,
                    tenant_id=self.tenant_id,
                    observation_type="new_email",
                    source="email",
                    content={
                        "email_id": email.id,
                        "from": email.from_addr,
                        "subject": email.subject,
                        "priority": priority,
                        "requires_response": await self._requires_response(email),
                    },
                    timestamp=email.timestamp,
                    priority=self._priority_to_int(priority),
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
        Fetch new unread emails from provider.

        Returns:
            List[Email]: New unread emails
        """
        if self.config.provider == EmailProvider.GMAIL:
            return await self._fetch_gmail_emails()
        if self.config.provider == EmailProvider.MICROSOFT_GRAPH:
            # TODO: Implement Microsoft Graph email fetching
            logger.debug(
                "Microsoft Graph email fetching not yet implemented",
                extra={"employee_id": str(self.employee_id)},
            )
            return []
        logger.warning(
            f"Unknown email provider: {self.config.provider}",
            extra={"employee_id": str(self.employee_id)},
        )
        return []

    async def _fetch_gmail_emails(self) -> list[Email]:
        """
        Fetch unread emails from Gmail.

        Returns:
            List[Email]: Unread emails from Gmail
        """
        if not self._client:
            logger.warning(
                "Gmail client not initialized",
                extra={"employee_id": str(self.employee_id)},
            )
            return []

        try:
            # Build query for unread emails in monitored folders
            query_parts = ["is:unread"]
            if self._last_check:
                # Gmail uses epoch seconds for after: query
                epoch = int(self._last_check.timestamp())
                query_parts.append(f"after:{epoch}")

            query = " ".join(query_parts)

            # List messages (synchronous API, wrap in thread)
            def _list_messages() -> dict[str, Any]:
                return (
                    self._client.users()
                    .messages()
                    .list(userId="me", q=query, maxResults=50)
                    .execute()
                )

            result = await asyncio.to_thread(_list_messages)
            messages = result.get("messages", [])

            if not messages:
                logger.debug(
                    "No new unread emails",
                    extra={"employee_id": str(self.employee_id)},
                )
                return []

            # Fetch full message details
            emails = []
            for msg_info in messages:
                try:
                    email = await self._fetch_gmail_message(msg_info["id"])
                    if email:
                        emails.append(email)
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch message {msg_info['id']}: {e}",
                        extra={"employee_id": str(self.employee_id)},
                    )

            logger.info(
                f"Fetched {len(emails)} new emails from Gmail",
                extra={
                    "employee_id": str(self.employee_id),
                    "email_count": len(emails),
                },
            )

            return emails

        except Exception as e:
            logger.error(
                "Failed to fetch Gmail emails",
                exc_info=True,
                extra={"employee_id": str(self.employee_id), "error": str(e)},
            )
            return []

    async def _fetch_gmail_message(self, message_id: str) -> Email | None:
        """
        Fetch a single Gmail message by ID.

        Parameters:
            message_id: Gmail message ID

        Returns:
            Email object or None if fetch fails
        """

        def _get_message() -> dict[str, Any]:
            return (
                self._client.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

        msg = await asyncio.to_thread(_get_message)

        # Parse headers
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}

        # Parse body
        body = ""
        html_body = None
        payload = msg.get("payload", {})

        if "parts" in payload:
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")
                data = part.get("body", {}).get("data", "")
                if data:
                    decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    if mime_type == "text/plain":
                        body = decoded
                    elif mime_type == "text/html":
                        html_body = decoded
        elif "body" in payload and payload["body"].get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode(
                "utf-8", errors="replace"
            )

        # Parse timestamp
        internal_date = msg.get("internalDate")
        timestamp = (
            datetime.fromtimestamp(int(internal_date) / 1000, tz=UTC)
            if internal_date
            else datetime.now(UTC)
        )

        # Parse addresses
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
            attachments=[],  # TODO: Parse attachments
            in_reply_to=headers.get("in-reply-to"),
            labels=msg.get("labelIds", []),
            is_read="UNREAD" not in msg.get("labelIds", []),
        )

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
        Send new email via Gmail or Microsoft Graph.

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

        if self.config.provider == EmailProvider.GMAIL:
            return await self._send_gmail(to, subject, body, cc)
        if self.config.provider == EmailProvider.MICROSOFT_GRAPH:
            # TODO: Implement Microsoft Graph send
            logger.warning("Microsoft Graph send not yet implemented")
            return ActionResult(success=False, error="Microsoft Graph not implemented")
        return ActionResult(success=False, error=f"Unknown provider: {self.config.provider}")

    async def _send_gmail(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
    ) -> ActionResult:
        """
        Send email via Gmail API.

        Parameters:
            to: Recipient email addresses
            subject: Email subject
            body: Email body (plain text)
            cc: CC recipients

        Returns:
            ActionResult with message_id on success
        """
        if not self._client:
            return ActionResult(success=False, error="Gmail client not initialized")

        try:
            # Create MIME message
            message = MIMEText(body)
            message["to"] = ", ".join(to)
            message["from"] = self.config.email_address
            message["subject"] = subject
            if cc:
                message["cc"] = ", ".join(cc)

            # Encode for Gmail API
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

            def _send() -> dict[str, Any]:
                return (
                    self._client.users().messages().send(userId="me", body={"raw": raw}).execute()
                )

            result = await asyncio.to_thread(_send)
            message_id = result.get("id", "")

            logger.info(
                "Email sent via Gmail",
                extra={
                    "employee_id": str(self.employee_id),
                    "message_id": message_id,
                    "recipient_count": len(to),
                    "recipient_domains": (to if self.config.log_pii else self._extract_domains(to)),
                    "subject_hash": (
                        subject if self.config.log_pii else self._redact_subject(subject)
                    ),
                    "cc_count": len(cc) if cc else 0,
                },
            )

            return ActionResult(
                success=True,
                metadata={
                    "message_id": message_id,
                    "sent_at": datetime.now(UTC).isoformat(),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to send email via Gmail",
                exc_info=True,
                extra={"employee_id": str(self.employee_id), "error": str(e)},
            )
            return ActionResult(success=False, error=f"Gmail send failed: {e}")

    async def _reply_to_email(
        self, email_id: str, body: str, cc: list[str] | None = None
    ) -> ActionResult:
        """
        Reply to existing email.

        Parameters:
            email_id (str): ID of email to reply to
            body (str): Reply body
            cc (List[str], optional): Additional CC recipients

        Returns:
            ActionResult: Success with metadata or error
        """
        if self.config.provider == EmailProvider.GMAIL:
            return await self._reply_gmail(email_id, body, cc)
        if self.config.provider == EmailProvider.MICROSOFT_GRAPH:
            logger.warning("Microsoft Graph reply not yet implemented")
            return ActionResult(success=False, error="Microsoft Graph not implemented")
        return ActionResult(success=False, error=f"Unknown provider: {self.config.provider}")

    async def _reply_gmail(
        self, email_id: str, body: str, cc: list[str] | None = None
    ) -> ActionResult:
        """
        Reply to email via Gmail API.

        Parameters:
            email_id: ID of email to reply to
            body: Reply body
            cc: Additional CC recipients

        Returns:
            ActionResult with message_id on success
        """
        if not self._client:
            return ActionResult(success=False, error="Gmail client not initialized")

        try:
            # Fetch original message to get thread ID and headers
            original = await self._fetch_gmail_message(email_id)
            if not original:
                return ActionResult(success=False, error="Original email not found")

            # Add signature if configured
            if self.config.signature:
                body = f"{body}\n\n{self.config.signature}"

            # Create reply message
            message = MIMEText(body)
            message["to"] = original.from_addr
            message["from"] = self.config.email_address
            message["subject"] = (
                f"Re: {original.subject}"
                if not original.subject.startswith("Re:")
                else original.subject
            )
            message["In-Reply-To"] = email_id
            message["References"] = email_id
            if cc:
                message["cc"] = ", ".join(cc)

            # Encode for Gmail API
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

            def _send() -> dict[str, Any]:
                return (
                    self._client.users()
                    .messages()
                    .send(userId="me", body={"raw": raw, "threadId": original.thread_id})
                    .execute()
                )

            result = await asyncio.to_thread(_send)
            message_id = result.get("id", "")

            logger.info(
                "Email reply sent via Gmail",
                extra={
                    "employee_id": str(self.employee_id),
                    "message_id": message_id,
                    "original_id": email_id
                    if self.config.log_pii
                    else self._redact_email_id(email_id),
                    "cc_count": len(cc) if cc else 0,
                },
            )

            return ActionResult(
                success=True,
                metadata={
                    "message_id": message_id,
                    "replied_at": datetime.now(UTC).isoformat(),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to reply to email via Gmail",
                exc_info=True,
                extra={"employee_id": str(self.employee_id), "error": str(e)},
            )
            return ActionResult(success=False, error=f"Gmail reply failed: {e}")

    async def _forward_email(
        self,
        email_id: str,
        to: list[str],
        comment: str | None = None,
    ) -> ActionResult:
        """
        Forward email to others.

        Parameters:
            email_id (str): ID of email to forward
            to (List[str]): Recipient email addresses
            comment (str, optional): Comment to add when forwarding

        Returns:
            ActionResult: Success with metadata or error
        """
        if self.config.provider == EmailProvider.GMAIL:
            return await self._forward_gmail(email_id, to, comment)
        if self.config.provider == EmailProvider.MICROSOFT_GRAPH:
            logger.warning("Microsoft Graph forward not yet implemented")
            return ActionResult(success=False, error="Microsoft Graph not implemented")
        return ActionResult(success=False, error=f"Unknown provider: {self.config.provider}")

    async def _forward_gmail(
        self,
        email_id: str,
        to: list[str],
        comment: str | None = None,
    ) -> ActionResult:
        """
        Forward email via Gmail API.

        Parameters:
            email_id: ID of email to forward
            to: Recipient email addresses
            comment: Comment to add when forwarding

        Returns:
            ActionResult with message_id on success
        """
        if not self._client:
            return ActionResult(success=False, error="Gmail client not initialized")

        try:
            # Fetch original message
            original = await self._fetch_gmail_message(email_id)
            if not original:
                return ActionResult(success=False, error="Original email not found")

            # Build forward body
            forward_header = (
                f"\n\n---------- Forwarded message ----------\n"
                f"From: {original.from_addr}\n"
                f"Date: {original.timestamp.isoformat() if original.timestamp else 'Unknown'}\n"
                f"Subject: {original.subject}\n"
                f"To: {', '.join(original.to_addrs)}\n\n"
            )
            body = (comment or "") + forward_header + (original.body or "")

            # Add signature if configured
            if self.config.signature:
                body = f"{body}\n\n{self.config.signature}"

            # Create forward message
            message = MIMEText(body)
            message["to"] = ", ".join(to)
            message["from"] = self.config.email_address
            message["subject"] = (
                f"Fwd: {original.subject}"
                if not original.subject.startswith("Fwd:")
                else original.subject
            )

            # Encode for Gmail API
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

            def _send() -> dict[str, Any]:
                return (
                    self._client.users().messages().send(userId="me", body={"raw": raw}).execute()
                )

            result = await asyncio.to_thread(_send)
            message_id = result.get("id", "")

            logger.info(
                "Email forwarded via Gmail",
                extra={
                    "employee_id": str(self.employee_id),
                    "message_id": message_id,
                    "original_id": (
                        email_id if self.config.log_pii else self._redact_email_id(email_id)
                    ),
                    "recipient_count": len(to),
                    "recipient_domains": (to if self.config.log_pii else self._extract_domains(to)),
                },
            )

            return ActionResult(
                success=True,
                metadata={
                    "message_id": message_id,
                    "forwarded_at": datetime.now(UTC).isoformat(),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to forward email via Gmail",
                exc_info=True,
                extra={"employee_id": str(self.employee_id), "error": str(e)},
            )
            return ActionResult(success=False, error=f"Gmail forward failed: {e}")

    async def _mark_read(self, email_id: str) -> ActionResult:
        """
        Mark email as read.

        Parameters:
            email_id (str): ID of email to mark as read

        Returns:
            ActionResult: Success or error
        """
        if self.config.provider == EmailProvider.GMAIL:
            return await self._mark_read_gmail(email_id)
        if self.config.provider == EmailProvider.MICROSOFT_GRAPH:
            logger.warning("Microsoft Graph mark_read not yet implemented")
            return ActionResult(success=False, error="Microsoft Graph not implemented")
        return ActionResult(success=False, error=f"Unknown provider: {self.config.provider}")

    async def _mark_read_gmail(self, email_id: str) -> ActionResult:
        """
        Mark email as read via Gmail API.

        Removes the UNREAD label from the message.

        Parameters:
            email_id: ID of email to mark as read

        Returns:
            ActionResult with success status
        """
        if not self._client:
            return ActionResult(success=False, error="Gmail client not initialized")

        try:

            def _modify() -> dict[str, Any]:
                return (
                    self._client.users()
                    .messages()
                    .modify(
                        userId="me",
                        id=email_id,
                        body={"removeLabelIds": ["UNREAD"]},
                    )
                    .execute()
                )

            await asyncio.to_thread(_modify)

            logger.debug(
                "Email marked as read via Gmail",
                extra={
                    "employee_id": str(self.employee_id),
                    "email_id": (
                        email_id if self.config.log_pii else self._redact_email_id(email_id)
                    ),
                },
            )

            return ActionResult(success=True)

        except Exception as e:
            logger.error(
                "Failed to mark email as read via Gmail",
                exc_info=True,
                extra={"employee_id": str(self.employee_id), "error": str(e)},
            )
            return ActionResult(success=False, error=f"Gmail mark_read failed: {e}")

    async def _archive(self, email_id: str) -> ActionResult:
        """
        Archive email.

        Parameters:
            email_id (str): ID of email to archive

        Returns:
            ActionResult: Success or error
        """
        if self.config.provider == EmailProvider.GMAIL:
            return await self._archive_gmail(email_id)
        if self.config.provider == EmailProvider.MICROSOFT_GRAPH:
            logger.warning("Microsoft Graph archive not yet implemented")
            return ActionResult(success=False, error="Microsoft Graph not implemented")
        return ActionResult(success=False, error=f"Unknown provider: {self.config.provider}")

    async def _archive_gmail(self, email_id: str) -> ActionResult:
        """
        Archive email via Gmail API.

        In Gmail, archiving means removing the INBOX label.
        The message remains accessible via "All Mail".

        Parameters:
            email_id: ID of email to archive

        Returns:
            ActionResult with success status
        """
        if not self._client:
            return ActionResult(success=False, error="Gmail client not initialized")

        try:

            def _modify() -> dict[str, Any]:
                return (
                    self._client.users()
                    .messages()
                    .modify(
                        userId="me",
                        id=email_id,
                        body={"removeLabelIds": ["INBOX"]},
                    )
                    .execute()
                )

            await asyncio.to_thread(_modify)

            logger.debug(
                "Email archived via Gmail",
                extra={
                    "employee_id": str(self.employee_id),
                    "email_id": (
                        email_id if self.config.log_pii else self._redact_email_id(email_id)
                    ),
                },
            )

            return ActionResult(success=True)

        except Exception as e:
            logger.error(
                "Failed to archive email via Gmail",
                exc_info=True,
                extra={"employee_id": str(self.employee_id), "error": str(e)},
            )
            return ActionResult(success=False, error=f"Gmail archive failed: {e}")
