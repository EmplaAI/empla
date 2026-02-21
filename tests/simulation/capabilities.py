"""
Simulated capabilities for E2E autonomous employee testing.

These capabilities implement the same interfaces as real capabilities
but interact with SimulatedEnvironment instead of real APIs.

This allows testing autonomous employee behavior end-to-end without:
- External API dependencies
- Rate limits
- Network latency
- Authentication complexity
- Cost per API call

The simulated capabilities interact with the same BDI engine, memory systems,
and proactive loop as production - only the "outside world" is simulated.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from empla.capabilities import CapabilityRegistry

from empla.capabilities.base import (
    CAPABILITY_CALENDAR,
    CAPABILITY_CRM,
    CAPABILITY_EMAIL,
    CAPABILITY_WORKSPACE,
    Action,
    ActionResult,
    BaseCapability,
    CapabilityConfig,
    Observation,
)
from tests.simulation.environment import (
    DealStage,
    SimulatedContact,
    SimulatedDeal,
    SimulatedEmail,
    SimulatedEnvironment,
)
from tests.simulation.environment import (
    EmailPriority as SimEmailPriority,
)

logger = logging.getLogger(__name__)


class SimulatedEmailCapability(BaseCapability):
    """
    Simulated email capability that interacts with SimulatedEnvironment.

    Implements the same EmailCapability interface but reads/writes to
    SimulatedEmailSystem instead of Microsoft Graph or Gmail API.
    """

    def __init__(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        config: CapabilityConfig,
        environment: SimulatedEnvironment,
    ):
        """
        Initialize simulated email capability.

        Parameters:
            tenant_id: Tenant identifier
            employee_id: Employee identifier
            config: Capability configuration
            environment: Simulated environment to interact with
        """
        super().__init__(tenant_id, employee_id, config)
        self.environment = environment
        self._last_check: datetime | None = None

    @property
    def capability_type(self) -> str:
        """Return EMAIL capability type"""
        return CAPABILITY_EMAIL

    async def initialize(self) -> None:
        """Initialize capability (simulated - always succeeds)"""
        self._initialized = True
        logger.info(f"Simulated email capability initialized for employee {self.employee_id}")

    async def perceive(self) -> list[Observation]:
        """
        Check simulated inbox for new emails and create observations.

        This simulates the email monitoring that EmailCapability.perceive() does,
        but reads from SimulatedEmailSystem instead of real API.

        Returns:
            List[Observation]: Observations for each unread email
        """
        if not self._initialized:
            return []

        observations = []

        # Get unread emails from simulated inbox
        unread_emails = self.environment.email.get_unread_emails()

        for email in unread_emails:
            # Triage email (simple keyword-based)
            priority = self._triage_email(email)

            # Create observation using unified Observation model
            observation = Observation(
                employee_id=self.employee_id,
                tenant_id=self.tenant_id,
                observation_type="new_email",
                source="email",
                content={
                    "email_id": email.id,
                    "from": email.from_address,
                    "to": email.to_addresses,
                    "subject": email.subject,
                    "body": email.body,
                    "priority": priority.value,
                    "thread_id": email.thread_id,
                    "requires_response": self._requires_response(email),
                },
                timestamp=email.received_at,
                priority=self._priority_to_int(priority),
                requires_action=(priority in [SimEmailPriority.URGENT, SimEmailPriority.HIGH]),
            )

            observations.append(observation)

        self._last_check = datetime.now(UTC)

        logger.debug(
            f"Simulated email perception: {len(observations)} new emails",
            extra={
                "employee_id": str(self.employee_id),
                "email_count": len(observations),
            },
        )

        return observations

    def _triage_email(self, email: SimulatedEmail) -> SimEmailPriority:
        """
        Classify email priority based on keywords.

        Parameters:
            email: Email to triage

        Returns:
            Priority level
        """
        text = f"{email.subject} {email.body}".lower()

        # Check for urgent keywords
        if any(kw in text for kw in ["urgent", "asap", "critical", "down", "outage"]):
            return SimEmailPriority.URGENT

        # Check for high priority keywords
        if any(kw in text for kw in ["important", "need", "question", "demo", "meeting"]):
            return SimEmailPriority.HIGH

        # Check if from email priority is already set
        if email.priority != SimEmailPriority.NORMAL:
            return email.priority

        return SimEmailPriority.NORMAL

    def _requires_response(self, email: SimulatedEmail) -> bool:
        """
        Determine if email requires a response.

        Parameters:
            email: Email to analyze

        Returns:
            True if response needed
        """
        # Questions need responses
        if "?" in email.body:
            return True

        # Direct requests
        text = email.body.lower()
        if any(kw in text for kw in ["can you", "could you", "please", "need"]):
            return True

        # FYIs don't need responses
        if email.subject.lower().startswith("fyi"):
            return False

        return False

    def _priority_to_int(self, priority: SimEmailPriority) -> int:
        """
        Convert email priority to observation priority (1-10).

        Parameters:
            priority: Email priority

        Returns:
            Observation priority (1-10)
        """
        mapping = {
            SimEmailPriority.URGENT: 10,
            SimEmailPriority.HIGH: 7,
            SimEmailPriority.NORMAL: 5,
            SimEmailPriority.LOW: 2,
        }
        return mapping.get(priority, 5)

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        """
        Execute email actions on simulated environment.

        Supported operations:
        - send_email: Send new email (adds to sent items)
        - reply_to_email: Reply to existing email
        - mark_read: Mark email as read

        Parameters:
            action: Action to execute

        Returns:
            Action result
        """
        operation = action.operation
        params = action.parameters

        if operation == "send_email":
            return await self._send_email(
                to=params["to"],
                subject=params["subject"],
                body=params["body"],
                cc=params.get("cc", []),
                thread_id=params.get("thread_id"),
                in_reply_to=params.get("in_reply_to"),
            )

        if operation == "reply_to_email":
            return await self._reply_to_email(
                email_id=params["email_id"],
                body=params["body"],
            )

        if operation == "mark_read":
            return await self._mark_read(params["email_id"])

        return ActionResult(success=False, error=f"Unknown operation: {operation}")

    async def _send_email(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> ActionResult:
        """
        Send email via simulated email system.

        Parameters:
            to: Recipient addresses
            subject: Email subject
            body: Email body
            cc: CC recipients
            thread_id: Thread ID (for threading)
            in_reply_to: Email ID being replied to

        Returns:
            Success result with metadata
        """
        email = self.environment.email.send_email(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
        )

        # Update metrics
        self.environment.metrics.increment("emails_sent")

        logger.info(
            f"Simulated email sent: {email.id}",
            extra={
                "employee_id": str(self.employee_id),
                "to": to,
                "subject": subject,
            },
        )

        return ActionResult(
            success=True,
            output={"email_id": email.id},
            metadata={
                "sent_at": email.received_at.isoformat(),
                "to": to,
                "subject": subject,
            },
        )

    async def _reply_to_email(self, email_id: str, body: str) -> ActionResult:
        """
        Reply to email in simulated environment.

        Parameters:
            email_id: ID of email to reply to
            body: Reply body

        Returns:
            Success result
        """
        # Find original email
        original = None
        for email in self.environment.email.inbox:
            if email.id == email_id:
                original = email
                break

        if not original:
            return ActionResult(success=False, error=f"Email {email_id} not found")

        # Send reply
        return await self._send_email(
            to=[original.from_address],
            subject=f"Re: {original.subject}",
            body=body,
            thread_id=original.thread_id or original.id,
            in_reply_to=email_id,
        )

    async def _mark_read(self, email_id: str) -> ActionResult:
        """
        Mark email as read in simulated environment.

        Parameters:
            email_id: ID of email to mark as read

        Returns:
            Success result
        """
        success = self.environment.email.mark_as_read(email_id)

        if success:
            return ActionResult(success=True)
        return ActionResult(success=False, error=f"Email {email_id} not found")


class SimulatedCalendarCapability(BaseCapability):
    """
    Simulated calendar capability that interacts with SimulatedEnvironment.

    Provides calendar monitoring and meeting scheduling without real API calls.
    """

    def __init__(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        config: CapabilityConfig,
        environment: SimulatedEnvironment,
    ):
        """
        Initialize simulated calendar capability.

        Parameters:
            tenant_id: Tenant identifier
            employee_id: Employee identifier
            config: Capability configuration
            environment: Simulated environment
        """
        super().__init__(tenant_id, employee_id, config)
        self.environment = environment

    @property
    def capability_type(self) -> str:
        """Return CALENDAR capability type"""
        return CAPABILITY_CALENDAR

    async def initialize(self) -> None:
        """Initialize capability (simulated)"""
        self._initialized = True
        logger.info(f"Simulated calendar capability initialized for employee {self.employee_id}")

    async def perceive(self) -> list[Observation]:
        """
        Check simulated calendar for upcoming events.

        Returns:
            List[Observation]: Observations for upcoming meetings
        """
        if not self._initialized:
            return []

        observations = []

        # Get events in next 24 hours
        upcoming = self.environment.calendar.get_upcoming_events(hours=24)

        for event in upcoming:
            # How soon is the event?
            time_until = event.start_time - datetime.now(UTC)
            hours_until = time_until.total_seconds() / 3600

            # Determine priority based on how soon
            if hours_until < 1:
                priority = 9  # Very soon
            elif hours_until < 4:
                priority = 7  # Soon
            else:
                priority = 5  # Normal

            observation = Observation(
                employee_id=self.employee_id,
                tenant_id=self.tenant_id,
                observation_type="upcoming_meeting",
                source="calendar",
                content={
                    "event_id": event.id,
                    "subject": event.subject,
                    "start_time": event.start_time.isoformat(),
                    "end_time": event.end_time.isoformat(),
                    "attendees": event.attendees,
                    "location": event.location,
                    "hours_until": hours_until,
                },
                timestamp=datetime.now(UTC),
                priority=priority,
                requires_action=(hours_until < 1),  # Urgent if <1 hour
            )

            observations.append(observation)

        return observations

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        """
        Execute calendar actions on simulated environment.

        Supported operations:
        - create_event: Create calendar event
        - update_event: Update existing event
        - cancel_event: Cancel event

        Parameters:
            action: Action to execute

        Returns:
            Action result
        """
        operation = action.operation
        params = action.parameters

        if operation == "create_event":
            return await self._create_event(
                subject=params["subject"],
                start_time=params["start_time"],
                end_time=params["end_time"],
                attendees=params.get("attendees", []),
                location=params.get("location", ""),
                description=params.get("description", ""),
            )

        return ActionResult(success=False, error=f"Unknown operation: {operation}")

    async def _create_event(
        self,
        subject: str,
        start_time: datetime,
        end_time: datetime,
        attendees: list[str],
        location: str,
        description: str,
    ) -> ActionResult:
        """
        Create calendar event in simulated environment.

        Parameters:
            subject: Event subject
            start_time: Event start time
            end_time: Event end time
            attendees: Attendee email addresses
            location: Event location
            description: Event description

        Returns:
            Success result with event ID
        """
        event = self.environment.calendar.create_event(
            subject=subject,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees,
            location=location,
            description=description,
        )

        # Update metrics
        self.environment.metrics.increment("meetings_scheduled")

        logger.info(
            f"Simulated calendar event created: {event.id}",
            extra={
                "employee_id": str(self.employee_id),
                "subject": subject,
                "attendees": attendees,
            },
        )

        return ActionResult(
            success=True,
            output={"event_id": event.id},
            metadata={
                "subject": subject,
                "start_time": start_time.isoformat(),
                "attendees": attendees,
            },
        )


class SimulatedCRMCapability(BaseCapability):
    """
    Simulated CRM capability for sales/CSM scenarios.

    Provides access to simulated deals, contacts, and customer data.
    """

    def __init__(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        config: CapabilityConfig,
        environment: SimulatedEnvironment,
    ):
        """
        Initialize simulated CRM capability.

        Parameters:
            tenant_id: Tenant identifier
            employee_id: Employee identifier
            config: Capability configuration
            environment: Simulated environment
        """
        super().__init__(tenant_id, employee_id, config)
        self.environment = environment

    @property
    def capability_type(self) -> str:
        """Return CRM capability type"""
        return CAPABILITY_CRM

    async def initialize(self) -> None:
        """Initialize capability (simulated)"""
        self._initialized = True
        logger.info(f"Simulated CRM capability initialized for employee {self.employee_id}")

    async def perceive(self) -> list[Observation]:
        """
        Monitor CRM for important changes.

        Returns:
            List[Observation]: Observations for CRM events (low pipeline, at-risk customers, etc.)
        """
        if not self._initialized:
            return []

        observations = []

        # Check pipeline coverage (for sales scenarios)
        pipeline_coverage = self.environment.crm.get_pipeline_coverage()
        if pipeline_coverage < 3.0:  # Below 3x target
            observations.append(
                Observation(
                    employee_id=self.employee_id,
                    tenant_id=self.tenant_id,
                    observation_type="low_pipeline_coverage",
                    source="crm",
                    content={
                        "pipeline_coverage": pipeline_coverage,
                        "pipeline_value": self.environment.crm.get_pipeline_value(),
                        "target": self.environment.crm._pipeline_target,
                    },
                    timestamp=datetime.now(UTC),
                    priority=8,  # High priority
                    requires_action=True,
                )
            )

        # Check for at-risk customers (for CSM scenarios)
        at_risk = self.environment.crm.get_at_risk_customers()
        for customer in at_risk:
            observations.append(
                Observation(
                    employee_id=self.employee_id,
                    tenant_id=self.tenant_id,
                    observation_type="customer_at_risk",
                    source="crm",
                    content={
                        "customer_id": customer.id,
                        "customer_name": customer.name,
                        "health": customer.health.value,
                        "churn_risk_score": customer.churn_risk_score,
                        "contract_value": customer.contract_value,
                        "last_contact_date": (
                            customer.last_contact_date.isoformat()
                            if customer.last_contact_date
                            else None
                        ),
                    },
                    timestamp=datetime.now(UTC),
                    priority=9,  # Very high priority
                    requires_action=True,
                )
            )

        return observations

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        """
        Execute CRM actions on simulated environment.

        Supported operations:
        - create_deal: Create new deal
        - update_deal: Update deal stage/value
        - add_contact: Add contact
        - update_customer_health: Update customer health score

        Parameters:
            action: Action to execute

        Returns:
            Action result
        """
        operation = action.operation
        params = action.parameters

        if operation == "create_deal":
            return await self._create_deal(
                name=params["name"],
                value=params["value"],
                stage=params.get("stage", DealStage.PROSPECTING),
                contact_id=params.get("contact_id"),
            )

        if operation == "update_deal":
            return await self._update_deal(
                deal_id=params["deal_id"],
                stage=params.get("stage"),
                value=params.get("value"),
            )

        if operation == "add_contact":
            return await self._add_contact(
                name=params["name"],
                email=params["email"],
                company=params.get("company", ""),
                title=params.get("title", ""),
            )

        return ActionResult(success=False, error=f"Unknown operation: {operation}")

    async def _create_deal(
        self,
        name: str,
        value: float,
        stage: DealStage,
        contact_id: str | None,
    ) -> ActionResult:
        """
        Create deal in simulated CRM.

        Parameters:
            name: Deal name
            value: Deal value
            stage: Deal stage
            contact_id: Associated contact ID

        Returns:
            Success result with deal ID
        """
        deal = SimulatedDeal(
            name=name,
            value=value,
            stage=stage,
            contact_id=contact_id,
            owner=str(self.employee_id),
        )

        self.environment.crm.add_deal(deal)
        self.environment.metrics.increment("deals_created")

        logger.info(
            f"Simulated deal created: {deal.id}",
            extra={
                "employee_id": str(self.employee_id),
                "deal_name": name,
                "value": value,
            },
        )

        return ActionResult(
            success=True,
            output={"deal_id": deal.id},
            metadata={"name": name, "value": value, "stage": stage.value},
        )

    async def _update_deal(
        self,
        deal_id: str,
        stage: DealStage | None = None,
        value: float | None = None,
    ) -> ActionResult:
        """
        Update deal in simulated CRM.

        Parameters:
            deal_id: Deal ID to update
            stage: New stage (optional)
            value: New value (optional)

        Returns:
            Success result
        """
        # Find deal
        deal = None
        for d in self.environment.crm.deals:
            if d.id == deal_id:
                deal = d
                break

        if not deal:
            return ActionResult(success=False, error=f"Deal {deal_id} not found")

        # Update fields
        if stage:
            deal.stage = stage
            if stage == DealStage.CLOSED_WON:
                self.environment.metrics.increment("deals_closed_won")
            elif stage == DealStage.CLOSED_LOST:
                self.environment.metrics.increment("deals_closed_lost")

        if value:
            deal.value = value

        deal.last_activity_date = datetime.now(UTC)

        logger.info(
            f"Simulated deal updated: {deal_id}",
            extra={
                "employee_id": str(self.employee_id),
                "deal_id": deal_id,
                "stage": stage.value if stage else None,
                "value": value,
            },
        )

        return ActionResult(success=True, output={"deal_id": deal_id})

    async def _add_contact(self, name: str, email: str, company: str, title: str) -> ActionResult:
        """
        Add contact to simulated CRM.

        Parameters:
            name: Contact name
            email: Email address
            company: Company name
            title: Job title

        Returns:
            Success result with contact ID
        """
        contact = SimulatedContact(name=name, email=email, company=company, title=title)

        self.environment.crm.add_contact(contact)

        logger.info(
            f"Simulated contact created: {contact.id}",
            extra={
                "employee_id": str(self.employee_id),
                "contact_name": name,
                "company": company,
            },
        )

        return ActionResult(
            success=True,
            output={"contact_id": contact.id},
            metadata={"name": name, "email": email, "company": company},
        )


class SimulatedWorkspaceCapability(BaseCapability):
    """
    Simulated workspace capability that uses in-memory storage.

    Delegates file operations to SimulatedWorkspaceSystem instead of real filesystem.
    Note: perceive() is a no-op stub that always returns an empty list. Stale draft
    detection, new file detection, and capacity monitoring are not simulated.
    """

    def __init__(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        config: CapabilityConfig,
        environment: SimulatedEnvironment,
    ):
        super().__init__(tenant_id, employee_id, config)
        self.environment = environment

    @property
    def capability_type(self) -> str:
        return CAPABILITY_WORKSPACE

    async def initialize(self) -> None:
        self._initialized = True
        logger.info(f"Simulated workspace capability initialized for employee {self.employee_id}")

    async def perceive(self) -> list[Observation]:
        if not self._initialized:
            return []
        return []

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        operation = action.operation
        params = action.parameters
        ws = self.environment.workspace

        if operation == "write_file":
            size = ws.write_file(params["path"], params["content"])
            return ActionResult(
                success=True,
                output={"path": params["path"], "size_bytes": size},
            )

        if operation == "read_file":
            content = ws.read_file(params["path"])
            if content is None:
                return ActionResult(success=False, error=f"File not found: {params['path']}")
            return ActionResult(
                success=True,
                output={
                    "content": content,
                    "size_bytes": len(content.encode("utf-8")),
                    "modified_at": datetime.now(UTC).isoformat(),
                },
            )

        if operation == "delete_file":
            deleted = ws.delete_file(params["path"])
            if not deleted:
                return ActionResult(success=False, error=f"File not found: {params['path']}")
            return ActionResult(success=True, output={"deleted": True})

        if operation == "move_file":
            if params["from"] == params["to"]:
                return ActionResult(success=False, error="Source and destination are the same")
            content = ws.read_file(params["from"])
            if content is None:
                return ActionResult(success=False, error=f"Source not found: {params['from']}")
            if ws.read_file(params["to"]) is not None:
                return ActionResult(
                    success=False, error=f"Destination already exists: {params['to']}"
                )
            ws.write_file(params["to"], content)
            if not ws.delete_file(params["from"]):
                return ActionResult(
                    success=False, error=f"Failed to remove source: {params['from']}"
                )
            return ActionResult(success=True, output={"new_path": params["to"]})

        if operation == "list_directory":
            files = ws.list_directory(params.get("path", ""))
            return ActionResult(
                success=True,
                output={
                    "files": [
                        {
                            "name": Path(f).name,
                            "size_bytes": len(ws.files[f].encode("utf-8")) if f in ws.files else 0,
                            "modified_at": datetime.now(UTC).isoformat(),
                            "is_dir": False,
                        }
                        for f in files
                    ]
                },
            )

        if operation == "search_files":
            matches = ws.search(params["query"])
            return ActionResult(
                success=True,
                output={"matches": matches, "total": len(matches)},
            )

        if operation == "get_workspace_status":
            return ActionResult(
                success=True,
                output={
                    "total_files": ws.total_files,
                    "total_size_mb": round(ws.total_size_bytes / (1024 * 1024), 2),
                    "max_size_mb": 500,
                    "recent_changes": [],
                },
            )

        return ActionResult(success=False, error=f"Unknown operation: {operation}")


def get_simulated_capabilities(
    tenant_id: UUID,
    employee_id: UUID,
    environment: SimulatedEnvironment,
    enabled_capabilities: list[str] | None = None,
) -> dict[str, BaseCapability]:
    """
    Create simulated capabilities for an employee.

    Parameters:
        tenant_id: Tenant ID
        employee_id: Employee ID
        environment: Simulated environment
        enabled_capabilities: List of capability types to enable (default: all)

    Returns:
        Dict mapping capability types to capability instances
    """
    if enabled_capabilities is None:
        enabled_capabilities = [
            CAPABILITY_EMAIL,
            CAPABILITY_CALENDAR,
            CAPABILITY_CRM,
            CAPABILITY_WORKSPACE,
        ]

    capabilities = {}

    if CAPABILITY_EMAIL in enabled_capabilities:
        capabilities[CAPABILITY_EMAIL] = SimulatedEmailCapability(
            tenant_id=tenant_id,
            employee_id=employee_id,
            config=CapabilityConfig(),
            environment=environment,
        )

    if CAPABILITY_CALENDAR in enabled_capabilities:
        capabilities[CAPABILITY_CALENDAR] = SimulatedCalendarCapability(
            tenant_id=tenant_id,
            employee_id=employee_id,
            config=CapabilityConfig(),
            environment=environment,
        )

    if CAPABILITY_CRM in enabled_capabilities:
        capabilities[CAPABILITY_CRM] = SimulatedCRMCapability(
            tenant_id=tenant_id,
            employee_id=employee_id,
            config=CapabilityConfig(),
            environment=environment,
        )

    if CAPABILITY_WORKSPACE in enabled_capabilities:
        capabilities[CAPABILITY_WORKSPACE] = SimulatedWorkspaceCapability(
            tenant_id=tenant_id,
            employee_id=employee_id,
            config=CapabilityConfig(),
            environment=environment,
        )

    return capabilities


def get_simulated_registry(
    tenant_id: UUID,
    employee_id: UUID,
    environment: SimulatedEnvironment,
    enabled_capabilities: list[str] | None = None,
) -> "CapabilityRegistry":
    """
    Create a pre-populated CapabilityRegistry with simulated capabilities.

    This is designed for use with DigitalEmployee's capability_registry injection:

        registry = get_simulated_registry(tenant_id, employee_id, env)
        employee = SalesAE(config, capability_registry=registry)

    Parameters:
        tenant_id: Tenant ID
        employee_id: Employee ID
        environment: Simulated environment to interact with
        enabled_capabilities: List of capability types to enable (default: all)

    Returns:
        CapabilityRegistry with simulated capabilities pre-initialized
    """
    from empla.capabilities import CapabilityRegistry

    # Create capabilities
    capabilities = get_simulated_capabilities(
        tenant_id=tenant_id,
        employee_id=employee_id,
        environment=environment,
        enabled_capabilities=enabled_capabilities,
    )

    # Create registry, register capability classes, and inject instances
    registry = CapabilityRegistry()

    # Register the capability classes so execute_action validation works
    for cap_type, instance in capabilities.items():
        registry.register(cap_type, type(instance))

    registry._instances[employee_id] = capabilities

    return registry


async def initialize_simulated_capabilities(
    registry: "CapabilityRegistry",
    employee_id: UUID,
) -> None:
    """
    Initialize all simulated capabilities in a registry.

    Call this after injecting the registry into a DigitalEmployee
    to ensure all capabilities are marked as initialized.

    Parameters:
        registry: Registry with simulated capabilities
        employee_id: Employee ID whose capabilities to initialize
    """
    if employee_id not in registry._instances:
        return

    for capability in registry._instances[employee_id].values():
        await capability.initialize()
