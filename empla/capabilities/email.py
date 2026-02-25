"""
Email Capability

Enables digital employees to interact via email - monitor inbox, triage messages,
compose responses, and send emails.

Supports two credential modes:
1. Integration Service (recommended): Credentials stored securely via IntegrationService
2. Direct Config: Credentials passed directly in config (for testing/simulation)

Provider-specific API logic lives in empla.integrations.email adapters (Layer 2).
This module handles capability logic: triage, dispatch, PII logging, signatures.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
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
from empla.integrations.email.types import Email, EmailPriority, EmailProvider

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from empla.integrations.email.base import EmailAdapter
    from empla.services.integrations import IntegrationService

logger = logging.getLogger(__name__)


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

    Provider-specific API calls are delegated to EmailAdapter instances
    (Layer 2) via the integration adapter layer.

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
        integration_service: IntegrationService | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        super().__init__(tenant_id, employee_id, config)
        self.config: EmailConfig = config
        self._last_check: datetime | None = None
        self._adapter: EmailAdapter | None = None
        self._integration_service = integration_service
        self._session = session
        self._cached_credentials: dict[str, Any] | None = None
        self._credential_expires_at: datetime | None = None

    @property
    def capability_type(self) -> str:
        return CAPABILITY_EMAIL

    async def initialize(self) -> None:
        """Initialize email adapter for the configured provider."""
        from empla.integrations.email.factory import create_email_adapter

        credentials = await self._get_credentials()

        if credentials is None:
            raise RuntimeError(
                "No credentials available. Either configure integration service "
                "or provide credentials in config."
            )

        email_address = getattr(self.config, "email_address", "unknown")
        provider_value = (
            self.config.provider.value
            if isinstance(self.config.provider, EmailProvider)
            else str(self.config.provider)
        )

        self._adapter = create_email_adapter(provider_value, email_address)
        await self._adapter.initialize(credentials)
        self._initialized = True

        log_pii = getattr(self.config, "log_pii", False)
        use_integration = getattr(self.config, "use_integration_service", False)

        logger.info(
            "Email capability initialized",
            extra={
                "employee_id": str(self.employee_id),
                "email": (email_address if log_pii else self._redact_email_address(email_address)),
                "provider": provider_value,
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
        """Fetch new unread emails via the adapter."""
        if not self._adapter:
            return []

        return await self._adapter.fetch_emails(
            unread_only=True,
            since=self._last_check,
            max_results=50,
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
        """Convert email priority to observation priority (1-10)."""
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
        """Compute stable SHA256 hash (first 8 chars) for PII-safe logging."""
        return hashlib.sha256(value.encode()).hexdigest()[:8]

    def _extract_domains(self, addresses: list[str]) -> list[str]:
        """Extract unique domains from email addresses."""
        domains = set()
        for addr in addresses:
            if "@" in addr:
                domains.add(addr.split("@")[1])
        return sorted(domains)

    def _redact_email_id(self, email_id: str) -> str:
        """Redact email ID for PII-safe logging."""
        return self._hash_value(email_id)

    def _redact_subject(self, subject: str) -> str:
        """Redact email subject for PII-safe logging."""
        return self._hash_value(subject)

    def _redact_email_address(self, email: str) -> str:
        """Redact email address for PII-safe logging (domain only)."""
        if "@" in email:
            return email.split("@")[1]
        return "[redacted]"

    async def shutdown(self) -> None:
        """Shut down the email adapter and release resources."""
        if self._adapter:
            await self._adapter.shutdown()
            self._adapter = None
        self._initialized = False

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        """
        Execute email actions.

        Supported operations:
        - send_email: Send new email
        - reply_to_email: Reply to existing email
        - forward_email: Forward email
        - mark_read: Mark email as read
        - archive: Archive email
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
        """Send new email via adapter."""
        if not self._adapter:
            return ActionResult(success=False, error="Email adapter not initialized")

        # Add signature if configured
        if self.config.signature:
            body = f"{body}\n\n{self.config.signature}"

        result = await self._adapter.send(to, subject, body, cc)

        if result.success:
            message_id = result.data.get("message_id", "")
            logger.info(
                "Email sent",
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

        return ActionResult(success=False, error=result.error)

    async def _reply_to_email(
        self, email_id: str, body: str, cc: list[str] | None = None
    ) -> ActionResult:
        """Reply to existing email via adapter."""
        if not self._adapter:
            return ActionResult(success=False, error="Email adapter not initialized")

        # Add signature if configured
        if self.config.signature:
            body = f"{body}\n\n{self.config.signature}"

        result = await self._adapter.reply(email_id, body, cc)

        if result.success:
            message_id = result.data.get("message_id", "")
            logger.info(
                "Email reply sent",
                extra={
                    "employee_id": str(self.employee_id),
                    "message_id": message_id,
                    "original_id": (
                        email_id if self.config.log_pii else self._redact_email_id(email_id)
                    ),
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

        return ActionResult(success=False, error=result.error)

    async def _forward_email(
        self,
        email_id: str,
        to: list[str],
        comment: str | None = None,
    ) -> ActionResult:
        """Forward email via adapter."""
        if not self._adapter:
            return ActionResult(success=False, error="Email adapter not initialized")

        # Append signature if configured, same as send/reply
        if self.config.signature:
            body = f"{comment}\n\n{self.config.signature}" if comment else self.config.signature
        else:
            body = comment

        result = await self._adapter.forward(email_id, to, body)

        if result.success:
            message_id = result.data.get("message_id", "")
            logger.info(
                "Email forwarded",
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

        return ActionResult(success=False, error=result.error)

    async def _mark_read(self, email_id: str) -> ActionResult:
        """Mark email as read via adapter."""
        if not self._adapter:
            return ActionResult(success=False, error="Email adapter not initialized")

        result = await self._adapter.mark_read(email_id)

        if result.success:
            logger.debug(
                "Email marked as read",
                extra={
                    "employee_id": str(self.employee_id),
                    "email_id": (
                        email_id if self.config.log_pii else self._redact_email_id(email_id)
                    ),
                },
            )
            return ActionResult(success=True)

        return ActionResult(success=False, error=result.error)

    async def _archive(self, email_id: str) -> ActionResult:
        """Archive email via adapter."""
        if not self._adapter:
            return ActionResult(success=False, error="Email adapter not initialized")

        result = await self._adapter.archive(email_id)

        if result.success:
            logger.debug(
                "Email archived",
                extra={
                    "employee_id": str(self.employee_id),
                    "email_id": (
                        email_id if self.config.log_pii else self._redact_email_id(email_id)
                    ),
                },
            )
            return ActionResult(success=True)

        return ActionResult(success=False, error=result.error)
