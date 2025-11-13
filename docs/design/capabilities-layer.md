# Phase 2: Capabilities Layer Design

**Status:** Draft → In Progress
**Author:** Claude Code
**Date:** 2025-11-12
**Phase:** 2 - Basic Capabilities

---

## Table of Contents
- [Problem](#problem)
- [Solution Overview](#solution-overview)
- [Architecture](#architecture)
- [Capability Base](#capability-base)
- [Email Capability](#email-capability)
- [Calendar Capability](#calendar-capability)
- [Messaging Capability](#messaging-capability)
- [Browser Capability](#browser-capability)
- [Document Capability](#document-capability)
- [Perception Integration](#perception-integration)
- [Security & Multi-tenancy](#security--multi-tenancy)
- [Testing Strategy](#testing-strategy)
- [Performance Considerations](#performance-considerations)
- [Migration Path](#migration-path)

---

## Problem

Phase 1 delivered the autonomous core (BDI engine, proactive loop, memory systems), but employees currently lack the ability to **interact with the world**. They can think, plan, and remember - but they can't act.

**Specific gaps:**
1. **No perception sources** - Proactive loop has placeholder perception
2. **No action execution** - Intentions cannot be executed
3. **No external integrations** - Cannot access email, calendar, messaging
4. **No tool use** - Cannot perform actual work

**Goal:** Give employees their "hands" - the ability to perceive their environment and execute actions in the real world.

---

## Solution Overview

Implement the **Capabilities Layer** (Layer 2 from ARCHITECTURE.md) - a plugin-based system where each capability encapsulates:
1. **Perception** - Monitor environment for changes/events
2. **Actions** - Execute specific operations
3. **State** - Track capability-specific state
4. **Configuration** - Per-tenant, per-employee customization

**Core capabilities for Phase 2:**
- **Email**: Monitor inbox, send emails, triage, compose
- **Calendar**: Schedule meetings, find optimal times, prepare for meetings
- **Messaging**: Slack/Teams integration, monitor channels, respond
- **Browser**: Web research, data extraction, form submission
- **Document**: Generate presentations, proposals, reports

---

## Architecture

### Capability Plugin System

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from enum import Enum

class CapabilityType(str, Enum):
    """Types of capabilities"""
    EMAIL = "email"
    CALENDAR = "calendar"
    MESSAGING = "messaging"
    BROWSER = "browser"
    DOCUMENT = "document"
    CRM = "crm"
    VOICE = "voice"
    COMPUTER_USE = "computer_use"


class CapabilityConfig(BaseModel):
    """Base configuration for capabilities"""
    enabled: bool = True
    rate_limit: Optional[int] = None  # Max operations per minute
    retry_policy: Dict[str, Any] = {"max_retries": 3, "backoff": "exponential"}
    timeout_seconds: int = 30


class Observation(BaseModel):
    """Single observation from a capability"""
    source: str  # Which capability generated this
    type: str  # Type of observation (e.g., "new_email", "calendar_event")
    timestamp: datetime
    priority: int  # 1-10, higher = more important
    data: Dict[str, Any]  # Observation-specific data
    requires_action: bool = False  # Should trigger immediate action?


class Action(BaseModel):
    """Action to be executed by a capability"""
    capability: str  # Which capability should execute
    operation: str  # What operation to perform
    parameters: Dict[str, Any]  # Operation parameters
    priority: int = 5  # 1-10
    deadline: Optional[datetime] = None
    context: Dict[str, Any] = {}  # Additional context


class ActionResult(BaseModel):
    """Result of executing an action"""
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}  # Timing, cost, etc.


class BaseCapability(ABC):
    """
    Base class for all capabilities.

    A capability is a discrete unit of functionality that provides:
    1. Perception - observe environment
    2. Action - execute operations
    3. State - maintain capability-specific state

    Capabilities are:
    - Tenant-scoped (isolated per customer)
    - Employee-scoped (per-employee configuration)
    - Observable (metrics, logging)
    - Testable (mock implementations available)
    """

    def __init__(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        config: CapabilityConfig
    ):
        self.tenant_id = tenant_id
        self.employee_id = employee_id
        self.config = config
        self._initialized = False

    @property
    @abstractmethod
    def capability_type(self) -> CapabilityType:
        """Type of this capability"""
        pass

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize capability - set up connections, auth, etc.
        Called once when capability is enabled.
        """
        pass

    @abstractmethod
    async def perceive(self) -> List[Observation]:
        """
        Observe environment - check for new events, changes, triggers.
        Called periodically by proactive loop.

        Returns:
            List of observations (can be empty if nothing new)
        """
        pass

    @abstractmethod
    async def execute_action(self, action: Action) -> ActionResult:
        """
        Execute a specific action.
        Called when employee decides to act.

        Args:
            action: Action to execute with parameters

        Returns:
            Result of action execution
        """
        pass

    async def shutdown(self) -> None:
        """
        Clean shutdown - close connections, flush state.
        Called when capability is disabled or employee deactivated.
        """
        pass

    def is_healthy(self) -> bool:
        """
        Health check - is capability functioning properly?
        Used for monitoring and alerting.
        """
        return self._initialized


class CapabilityRegistry:
    """
    Central registry for all capabilities.
    Manages capability lifecycle and routing.
    """

    def __init__(self):
        self._capabilities: Dict[str, Type[BaseCapability]] = {}
        self._instances: Dict[UUID, Dict[str, BaseCapability]] = {}

    def register(
        self,
        capability_type: CapabilityType,
        capability_class: Type[BaseCapability]
    ) -> None:
        """Register a capability implementation"""
        self._capabilities[capability_type] = capability_class

    async def enable_for_employee(
        self,
        employee_id: UUID,
        tenant_id: UUID,
        capability_type: CapabilityType,
        config: CapabilityConfig
    ) -> BaseCapability:
        """Enable a capability for an employee"""

        if employee_id not in self._instances:
            self._instances[employee_id] = {}

        # Create instance
        capability_class = self._capabilities[capability_type]
        instance = capability_class(
            tenant_id=tenant_id,
            employee_id=employee_id,
            config=config
        )

        # Initialize
        await instance.initialize()

        # Store
        self._instances[employee_id][capability_type] = instance

        return instance

    async def disable_for_employee(
        self,
        employee_id: UUID,
        capability_type: CapabilityType
    ) -> None:
        """Disable a capability for an employee"""

        if employee_id in self._instances:
            if capability_type in self._instances[employee_id]:
                capability = self._instances[employee_id][capability_type]
                await capability.shutdown()
                del self._instances[employee_id][capability_type]

    def get_capability(
        self,
        employee_id: UUID,
        capability_type: CapabilityType
    ) -> Optional[BaseCapability]:
        """Get capability instance for employee"""

        if employee_id in self._instances:
            return self._instances[employee_id].get(capability_type)
        return None

    async def perceive_all(self, employee_id: UUID) -> List[Observation]:
        """
        Run perception across all enabled capabilities for employee.
        Called by proactive loop.
        """

        if employee_id not in self._instances:
            return []

        observations = []
        for capability in self._instances[employee_id].values():
            try:
                obs = await capability.perceive()
                observations.extend(obs)
            except Exception as e:
                logger.error(
                    f"Perception failed for {capability.capability_type}",
                    exc_info=True
                )

        return observations

    async def execute_action(
        self,
        employee_id: UUID,
        action: Action
    ) -> ActionResult:
        """Execute action using appropriate capability"""

        capability = self.get_capability(employee_id, action.capability)

        if not capability:
            return ActionResult(
                success=False,
                error=f"Capability {action.capability} not enabled"
            )

        try:
            return await capability.execute_action(action)
        except Exception as e:
            logger.error(
                f"Action execution failed: {action.operation}",
                exc_info=True
            )
            return ActionResult(
                success=False,
                error=str(e)
            )
```

---

## Email Capability

### Overview
Enable employees to interact via email - monitor inbox, triage messages, compose responses, send emails.

### Implementation

```python
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum

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
    thread_id: Optional[str]
    from_addr: str
    to_addrs: List[str]
    cc_addrs: List[str]
    subject: str
    body: str  # Plain text
    html_body: Optional[str]  # HTML version
    timestamp: datetime
    attachments: List[Dict[str, Any]]
    in_reply_to: Optional[str]
    labels: List[str]
    is_read: bool


class EmailConfig(CapabilityConfig):
    """Email capability configuration"""
    provider: EmailProvider
    email_address: str

    # Provider credentials (stored securely)
    credentials: Dict[str, Any]

    # Monitoring settings
    check_interval_seconds: int = 60
    monitor_folders: List[str] = ["inbox", "sent"]

    # Triage settings
    auto_triage: bool = True
    priority_keywords: Dict[EmailPriority, List[str]] = {
        EmailPriority.URGENT: ["urgent", "asap", "critical", "down"],
        EmailPriority.HIGH: ["important", "need", "question"],
    }

    # Response settings
    auto_respond: bool = False  # Require approval before sending
    signature: Optional[str] = None


class EmailCapability(BaseCapability):
    """
    Email capability implementation.

    Provides:
    - Inbox monitoring
    - Intelligent triage
    - Email composition
    - Sending with tracking
    """

    def __init__(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        config: EmailConfig
    ):
        super().__init__(tenant_id, employee_id, config)
        self.config: EmailConfig = config
        self._last_check: Optional[datetime] = None
        self._client = None  # Email provider client

    @property
    def capability_type(self) -> CapabilityType:
        return CapabilityType.EMAIL

    async def initialize(self) -> None:
        """Initialize email client"""

        if self.config.provider == EmailProvider.MICROSOFT_GRAPH:
            self._client = await self._init_microsoft_graph()
        elif self.config.provider == EmailProvider.GMAIL:
            self._client = await self._init_gmail()
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

        self._initialized = True
        logger.info(
            f"Email capability initialized",
            extra={
                "employee_id": self.employee_id,
                "email": self.config.email_address
            }
        )

    async def _init_microsoft_graph(self):
        """Initialize Microsoft Graph client"""
        # TODO: Implement Microsoft Graph authentication
        # Use OAuth2 with delegated permissions
        pass

    async def _init_gmail(self):
        """Initialize Gmail client"""
        # TODO: Implement Gmail API authentication
        pass

    async def perceive(self) -> List[Observation]:
        """
        Check inbox for new emails.
        Called periodically by proactive loop.
        """

        if not self._initialized:
            return []

        observations = []

        try:
            # Get new emails since last check
            new_emails = await self._fetch_new_emails()

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
                        "requires_response": await self._requires_response(email)
                    },
                    requires_action=(priority in [EmailPriority.URGENT, EmailPriority.HIGH])
                )

                observations.append(observation)

            self._last_check = datetime.now(timezone.utc)

        except Exception as e:
            logger.error(f"Email perception failed", exc_info=True)

        return observations

    async def _fetch_new_emails(self) -> List[Email]:
        """Fetch new emails from provider"""
        # TODO: Implement provider-specific email fetching
        # Filter by: unread, newer than last_check
        pass

    async def _triage_email(self, email: Email) -> EmailPriority:
        """
        Intelligent email triage.

        Classifies email priority based on:
        - Sender (customer, manager, lead)
        - Subject keywords
        - Content analysis
        - Thread context
        """

        # Check urgent keywords
        text = f"{email.subject} {email.body}".lower()
        for priority, keywords in self.config.priority_keywords.items():
            if any(kw in text for kw in keywords):
                return priority

        # Check sender relationship
        # TODO: Use memory system to check relationship
        # - Is this a customer?
        # - Is this my manager?
        # - Is this a hot lead?

        # Default to medium
        return EmailPriority.MEDIUM

    async def _requires_response(self, email: Email) -> bool:
        """Determine if email requires a response"""

        # Questions typically need responses
        if '?' in email.body:
            return True

        # Direct requests
        request_keywords = ["can you", "could you", "please", "need"]
        text = email.body.lower()
        if any(kw in text for kw in request_keywords):
            return True

        # FYIs typically don't
        if email.subject.lower().startswith("fyi"):
            return False

        return False

    def _priority_to_int(self, priority: EmailPriority) -> int:
        """Convert email priority to observation priority (1-10)"""
        mapping = {
            EmailPriority.URGENT: 10,
            EmailPriority.HIGH: 7,
            EmailPriority.MEDIUM: 5,
            EmailPriority.LOW: 2,
            EmailPriority.SPAM: 1
        }
        return mapping.get(priority, 5)

    async def execute_action(self, action: Action) -> ActionResult:
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

        try:
            if operation == "send_email":
                return await self._send_email(
                    to=params["to"],
                    subject=params["subject"],
                    body=params["body"],
                    cc=params.get("cc", []),
                    attachments=params.get("attachments", [])
                )

            elif operation == "reply_to_email":
                return await self._reply_to_email(
                    email_id=params["email_id"],
                    body=params["body"],
                    cc=params.get("cc", [])
                )

            elif operation == "forward_email":
                return await self._forward_email(
                    email_id=params["email_id"],
                    to=params["to"],
                    comment=params.get("comment")
                )

            elif operation == "mark_read":
                return await self._mark_read(params["email_id"])

            elif operation == "archive":
                return await self._archive(params["email_id"])

            else:
                return ActionResult(
                    success=False,
                    error=f"Unknown operation: {operation}"
                )

        except Exception as e:
            logger.error(f"Email action failed: {operation}", exc_info=True)
            return ActionResult(success=False, error=str(e))

    async def _send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        cc: List[str] = None,
        attachments: List[Dict[str, Any]] = None
    ) -> ActionResult:
        """Send new email"""

        # Add signature if configured
        if self.config.signature:
            body = f"{body}\n\n{self.config.signature}"

        # TODO: Use provider client to send
        # Record in memory system

        return ActionResult(
            success=True,
            metadata={"sent_at": datetime.now(timezone.utc)}
        )

    async def _reply_to_email(
        self,
        email_id: str,
        body: str,
        cc: List[str] = None
    ) -> ActionResult:
        """Reply to existing email"""
        # TODO: Fetch original email, create reply
        pass

    async def _forward_email(
        self,
        email_id: str,
        to: List[str],
        comment: Optional[str] = None
    ) -> ActionResult:
        """Forward email to others"""
        # TODO: Fetch original email, forward with comment
        pass

    async def _mark_read(self, email_id: str) -> ActionResult:
        """Mark email as read"""
        # TODO: Update email status via provider
        pass

    async def _archive(self, email_id: str) -> ActionResult:
        """Archive email"""
        # TODO: Move to archive folder via provider
        pass
```

---

## Calendar Capability

### Overview
Enable employees to manage calendars - schedule meetings, find optimal times, prepare for meetings.

### Implementation

```python
class CalendarProvider(str, Enum):
    """Supported calendar providers"""
    MICROSOFT_GRAPH = "microsoft_graph"
    GOOGLE_CALENDAR = "google_calendar"


@dataclass
class CalendarEvent:
    """Calendar event representation"""
    id: str
    title: str
    start_time: datetime
    end_time: datetime
    attendees: List[str]
    location: Optional[str]
    description: Optional[str]
    organizer: str
    is_online: bool
    meeting_url: Optional[str]
    status: str  # confirmed, tentative, cancelled


class CalendarConfig(CapabilityConfig):
    """Calendar capability configuration"""
    provider: CalendarProvider
    calendar_id: str
    credentials: Dict[str, Any]

    # Scheduling preferences
    working_hours_start: int = 9  # 9 AM
    working_hours_end: int = 17  # 5 PM
    timezone: str = "America/Los_Angeles"
    buffer_minutes: int = 15  # Buffer between meetings

    # Notification settings
    notify_before_minutes: int = 15


class CalendarCapability(BaseCapability):
    """
    Calendar capability implementation.

    Provides:
    - Event monitoring
    - Meeting scheduling
    - Optimal time finding
    - Meeting preparation
    """

    def __init__(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        config: CalendarConfig
    ):
        super().__init__(tenant_id, employee_id, config)
        self.config: CalendarConfig = config
        self._client = None

    @property
    def capability_type(self) -> CapabilityType:
        return CapabilityType.CALENDAR

    async def initialize(self) -> None:
        """Initialize calendar client"""
        # TODO: Initialize provider client
        self._initialized = True

    async def perceive(self) -> List[Observation]:
        """
        Monitor calendar for upcoming events.
        Called periodically by proactive loop.
        """

        observations = []

        # Get upcoming events (next 24 hours)
        upcoming = await self._get_upcoming_events(hours=24)

        for event in upcoming:
            time_until = event.start_time - datetime.now(timezone.utc)

            # Notify before meeting (e.g., 15 min)
            if time_until.total_seconds() / 60 <= self.config.notify_before_minutes:
                observations.append(Observation(
                    source="calendar",
                    type="meeting_soon",
                    timestamp=datetime.now(timezone.utc),
                    priority=8,
                    data={
                        "event_id": event.id,
                        "title": event.title,
                        "start_time": event.start_time,
                        "meeting_url": event.meeting_url
                    },
                    requires_action=True
                ))

        return observations

    async def _get_upcoming_events(self, hours: int = 24) -> List[CalendarEvent]:
        """Fetch upcoming events"""
        # TODO: Query provider for events in time window
        pass

    async def execute_action(self, action: Action) -> ActionResult:
        """
        Execute calendar actions.

        Supported operations:
        - schedule_meeting: Create new meeting
        - find_optimal_time: Find best time for meeting
        - cancel_meeting: Cancel existing meeting
        - reschedule_meeting: Move meeting to new time
        """

        operation = action.operation
        params = action.parameters

        try:
            if operation == "schedule_meeting":
                return await self._schedule_meeting(
                    title=params["title"],
                    attendees=params["attendees"],
                    start_time=params["start_time"],
                    duration_minutes=params["duration_minutes"],
                    description=params.get("description"),
                    location=params.get("location")
                )

            elif operation == "find_optimal_time":
                return await self._find_optimal_time(
                    attendees=params["attendees"],
                    duration_minutes=params["duration_minutes"],
                    preferred_times=params.get("preferred_times", [])
                )

            elif operation == "cancel_meeting":
                return await self._cancel_meeting(params["event_id"])

            elif operation == "reschedule_meeting":
                return await self._reschedule_meeting(
                    event_id=params["event_id"],
                    new_start_time=params["new_start_time"]
                )

            else:
                return ActionResult(
                    success=False,
                    error=f"Unknown operation: {operation}"
                )

        except Exception as e:
            logger.error(f"Calendar action failed: {operation}", exc_info=True)
            return ActionResult(success=False, error=str(e))

    async def _schedule_meeting(
        self,
        title: str,
        attendees: List[str],
        start_time: datetime,
        duration_minutes: int,
        description: Optional[str] = None,
        location: Optional[str] = None
    ) -> ActionResult:
        """Create new calendar event"""
        # TODO: Create event via provider
        pass

    async def _find_optimal_time(
        self,
        attendees: List[str],
        duration_minutes: int,
        preferred_times: List[datetime] = None
    ) -> ActionResult:
        """
        Find best time for meeting considering all attendees' calendars.

        Algorithm:
        1. Fetch free/busy for all attendees
        2. Find overlapping free slots
        3. Score slots based on preferences (time of day, buffer, etc.)
        4. Return top suggestions
        """
        # TODO: Implement optimal time finding
        pass
```

---

## Perception Integration

### Connecting Capabilities to Proactive Loop

Update `ProactiveExecutionLoop` to use capabilities for perception:

```python
# empla/core/loop/execution.py

class ProactiveExecutionLoop:

    def __init__(
        self,
        employee: Employee,
        capability_registry: CapabilityRegistry,
        config: LoopConfig
    ):
        self.employee = employee
        self.capability_registry = capability_registry
        self.config = config
        # ... rest of initialization

    async def perceive_environment(self) -> PerceptionResult:
        """
        Gather observations from all enabled capabilities.

        Replaces placeholder implementation from Phase 1.
        """

        # Perceive from all capabilities
        observations = await self.capability_registry.perceive_all(
            self.employee.employee_id
        )

        # Sort by priority
        observations.sort(key=lambda obs: obs.priority, reverse=True)

        return PerceptionResult(
            observations=observations,
            timestamp=datetime.now(timezone.utc),
            perception_duration_ms=...
        )

    async def execute_intentions(self) -> List[IntentionResult]:
        """
        Execute top-priority intentions using capabilities.

        Replaces placeholder implementation from Phase 1.
        """

        results = []

        # Get top N intentions
        intentions = await self.intentions.get_top_intentions(
            limit=self.config.max_concurrent_tasks
        )

        for intention in intentions:
            # Convert intention to capability action
            action = self._intention_to_action(intention)

            # Execute via capability
            result = await self.capability_registry.execute_action(
                employee_id=self.employee.employee_id,
                action=action
            )

            # Record outcome
            intention_result = IntentionResult(
                intention_id=intention.intention_id,
                success=result.success,
                output=result.output,
                error=result.error
            )
            results.append(intention_result)

            # Update intention status
            if result.success:
                await self.intentions.mark_completed(intention)
            else:
                await self.intentions.mark_failed(intention, result.error)

        return results

    def _intention_to_action(self, intention: Intention) -> Action:
        """Convert BDI intention to capability action"""

        # TODO: Sophisticated intention → action translation
        # For now, assume intention has action_spec
        return Action(
            capability=intention.action_spec["capability"],
            operation=intention.action_spec["operation"],
            parameters=intention.action_spec["parameters"],
            priority=intention.priority
        )
```

---

## Security & Multi-tenancy

### Tenant Isolation

All capabilities are tenant-scoped:
- Credentials stored per-tenant
- Data access restricted to tenant
- Rate limits per-tenant
- Audit logging includes tenant_id

### Credential Management

```python
class CredentialStore:
    """
    Secure credential storage for capabilities.

    Uses encryption at rest and in transit.
    Supports credential rotation.
    """

    async def store_credential(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        capability_type: CapabilityType,
        credentials: Dict[str, Any]
    ) -> None:
        """Store encrypted credentials"""
        # TODO: Encrypt and store in database
        pass

    async def retrieve_credential(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        capability_type: CapabilityType
    ) -> Dict[str, Any]:
        """Retrieve and decrypt credentials"""
        # TODO: Fetch from database and decrypt
        pass

    async def rotate_credential(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        capability_type: CapabilityType,
        new_credentials: Dict[str, Any]
    ) -> None:
        """Rotate credentials"""
        # TODO: Update credentials, notify capability
        pass
```

---

## Testing Strategy

### Unit Tests

Test each capability in isolation:

```python
# tests/unit/test_email_capability.py

@pytest.mark.asyncio
async def test_email_capability_perception():
    """Test email perception detects new emails"""

    # Setup
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="test@example.com",
        credentials={}
    )
    capability = EmailCapability(
        tenant_id=uuid4(),
        employee_id=uuid4(),
        config=config
    )

    # Mock email client
    capability._client = MockEmailClient(
        new_emails=[
            Email(
                id="1",
                from_addr="customer@example.com",
                subject="Urgent: System down",
                body="Our system is not working",
                timestamp=datetime.now(timezone.utc)
            )
        ]
    )

    # Execute
    observations = await capability.perceive()

    # Assert
    assert len(observations) == 1
    assert observations[0].type == "new_email"
    assert observations[0].priority == 10  # Urgent
    assert observations[0].requires_action is True


@pytest.mark.asyncio
async def test_email_capability_send():
    """Test sending email"""

    capability = EmailCapability(...)

    action = Action(
        capability="email",
        operation="send_email",
        parameters={
            "to": ["recipient@example.com"],
            "subject": "Test",
            "body": "Test body"
        }
    )

    result = await capability.execute_action(action)

    assert result.success is True
    assert "sent_at" in result.metadata
```

### Integration Tests

Test capability integration with proactive loop:

```python
# tests/integration/test_capabilities_integration.py

@pytest.mark.asyncio
async def test_proactive_loop_with_email():
    """Test proactive loop perceives emails and executes actions"""

    # Setup employee with email capability
    employee = await create_test_employee()
    registry = CapabilityRegistry()

    # Enable email capability
    await registry.enable_for_employee(
        employee_id=employee.employee_id,
        tenant_id=employee.tenant_id,
        capability_type=CapabilityType.EMAIL,
        config=EmailConfig(...)
    )

    # Create loop
    loop = ProactiveExecutionLoop(
        employee=employee,
        capability_registry=registry,
        config=LoopConfig()
    )

    # Run one cycle
    await loop.run_one_cycle()

    # Assert: Loop perceived email and created intention
    assert len(employee.intentions.pending) > 0
```

### E2E Tests

Test complete autonomous workflows:

```python
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_sales_ae_responds_to_lead_email():
    """
    E2E Test: Sales AE autonomously responds to inbound lead email

    Scenario:
    1. Lead sends email inquiry
    2. Email capability perceives email (high priority)
    3. Proactive loop creates intention to respond
    4. BDI system formulates response strategy
    5. Email capability sends response
    6. Response is tracked in memory
    """

    # Setup Sales AE employee
    sales_ae = await create_sales_ae(
        name="Jordan Chen",
        email="jordan@company.com"
    )

    # Inject test email into inbox
    await inject_test_email(
        to=sales_ae.email,
        from_addr="lead@prospect.com",
        subject="Interested in your product",
        body="Hi, I'd like to learn more about your product..."
    )

    # Run proactive loop for 5 minutes (or until action taken)
    await run_loop_until_action(sales_ae, timeout=300)

    # Assert: Response was sent
    sent_emails = await get_sent_emails(sales_ae)
    assert len(sent_emails) == 1
    assert sent_emails[0].to == "lead@prospect.com"
    assert "thank you for your interest" in sent_emails[0].body.lower()

    # Assert: Interaction was recorded in memory
    episodes = await sales_ae.memory.episodic.query(
        query="email interaction with lead@prospect.com"
    )
    assert len(episodes) > 0
```

### Test Coverage Goals

- **Unit tests**: >85% coverage for each capability
- **Integration tests**: All capability-loop interactions
- **E2E tests**: At least 3 complete autonomous workflows per employee type

---

## Performance Considerations

### Rate Limiting

Capabilities respect rate limits:
- Email: Max 100 emails/day per employee (configurable)
- Calendar: Max 50 operations/hour
- API calls: Exponential backoff on rate limit errors

### Caching

Aggressive caching for:
- Email metadata (subject, from, to) - 5 minute TTL
- Calendar free/busy - 15 minute TTL
- Credential tokens - until expiry

### Batching

Batch operations where possible:
- Fetch multiple emails in single API call
- Batch calendar queries
- Bulk event creation

### Async Execution

All capability operations are async:
- Non-blocking perception
- Parallel action execution
- Concurrent multi-capability operations

---

## Migration Path

### Phase 2.1: Capability Framework (Week 1)
- [x] Design capability abstraction
- [ ] Implement `BaseCapability` class
- [ ] Implement `CapabilityRegistry`
- [ ] Implement `CredentialStore`
- [ ] Unit tests for framework

### Phase 2.2: Email Capability (Week 2)
- [ ] Implement `EmailCapability`
- [ ] Microsoft Graph integration
- [ ] Gmail integration
- [ ] Email triage logic
- [ ] Unit tests + integration tests

### Phase 2.3: Calendar Capability (Week 2)
- [ ] Implement `CalendarCapability`
- [ ] Event monitoring
- [ ] Scheduling logic
- [ ] Optimal time finding algorithm
- [ ] Unit tests + integration tests

### Phase 2.4: Proactive Loop Integration (Week 3)
- [ ] Update `ProactiveExecutionLoop.perceive_environment()`
- [ ] Update `ProactiveExecutionLoop.execute_intentions()`
- [ ] Intention → Action translation
- [ ] Integration tests
- [ ] E2E tests

### Phase 2.5: Additional Capabilities (Week 4)
- [ ] Messaging capability (Slack/Teams)
- [ ] Browser capability (Playwright)
- [ ] Document capability (basic generation)

---

## Open Questions

1. **Agent Framework Decision**: Should we use Agno, LangGraph, or custom for tool execution?
   - **Recommendation**: Defer to Phase 2.4 - implement direct function calls first, add framework if complexity demands it

2. **Credential Storage**: Where to store encrypted credentials?
   - **Options**: PostgreSQL (simplest), HashiCorp Vault (production), AWS Secrets Manager
   - **Recommendation**: PostgreSQL for now (encrypted column), migrate to Vault in Phase 6

3. **Email Provider**: Start with Microsoft Graph, Gmail, or both?
   - **Recommendation**: Start with Microsoft Graph (more common in enterprise), add Gmail in Phase 2.5

4. **Perception Frequency**: How often should capabilities perceive?
   - **Recommendation**: Configurable per-capability (email: 60s, calendar: 300s)

5. **Action Approval**: Should actions require human approval?
   - **Recommendation**: Yes for Phase 2 (safety), make optional in Phase 3 (trust builds over time)

---

**Next Steps:**
1. Create ADR for capability framework design
2. Implement `BaseCapability` and `CapabilityRegistry`
3. Implement `EmailCapability` with Microsoft Graph
4. Write comprehensive tests
5. Integrate with proactive loop
6. E2E validation

---

**Document Status:** ✅ Complete - Ready for implementation
**Last Updated:** 2025-11-12
