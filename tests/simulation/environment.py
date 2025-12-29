"""
Simulated environment for E2E autonomous employee testing.

This provides a fake "world" for digital employees to interact with
without hitting real 3rd party APIs (Microsoft Graph, Gmail, etc.).

The simulated environment includes:
- Email system (inbox, sent items)
- Calendar system (events, meetings)
- CRM system (deals, contacts, pipeline metrics)
- Metrics tracking (employee performance)

Why simulate instead of mock:
- Tests ACTUAL BDI implementations (not mocks)
- Validates autonomous behavior end-to-end
- Fast, deterministic, debuggable tests
- No external dependencies or API rate limits
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4


class EmailPriority(str, Enum):
    """Email priority levels"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class DealStage(str, Enum):
    """CRM deal stages"""

    PROSPECTING = "prospecting"
    QUALIFICATION = "qualification"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class CustomerHealth(str, Enum):
    """Customer health status"""

    HEALTHY = "healthy"
    AT_RISK = "at_risk"
    CHURNED = "churned"


@dataclass
class SimulatedEmail:
    """A simulated email message"""

    id: str = field(default_factory=lambda: str(uuid4()))
    from_address: str = ""
    to_addresses: list[str] = field(default_factory=list)
    cc_addresses: list[str] = field(default_factory=list)
    subject: str = ""
    body: str = ""
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_read: bool = False
    priority: EmailPriority = EmailPriority.NORMAL
    thread_id: str | None = None
    in_reply_to: str | None = None
    attachments: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimulatedCalendarEvent:
    """A simulated calendar event"""

    id: str = field(default_factory=lambda: str(uuid4()))
    subject: str = ""
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(hours=1))
    attendees: list[str] = field(default_factory=list)
    location: str = ""
    description: str = ""
    is_organizer: bool = False
    response_status: str = "none"  # none, accepted, tentative, declined
    is_online_meeting: bool = False
    meeting_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimulatedContact:
    """A simulated CRM contact"""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    email: str = ""
    company: str = ""
    title: str = ""
    phone: str | None = None
    linkedin_url: str | None = None
    last_contact_date: datetime | None = None
    interaction_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimulatedDeal:
    """A simulated CRM deal"""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    value: float = 0.0
    stage: DealStage = DealStage.PROSPECTING
    probability: float = 0.0
    close_date: datetime | None = None
    contact_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity_date: datetime | None = None
    owner: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimulatedCustomer:
    """A simulated customer for CSM scenarios"""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    contract_value: float = 0.0
    health: CustomerHealth = CustomerHealth.HEALTHY
    last_contact_date: datetime | None = None
    onboarding_complete: bool = False
    usage_score: float = 0.0  # 0.0 to 1.0
    nps_score: int | None = None  # -100 to 100
    churn_risk_score: float = 0.0  # 0.0 to 1.0
    support_tickets_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class SimulatedEmailSystem:
    """Simulated email system with inbox and sent items"""

    def __init__(self):
        self.inbox: list[SimulatedEmail] = []
        self.sent: list[SimulatedEmail] = []
        self.drafts: list[SimulatedEmail] = []

    def receive_email(self, email: SimulatedEmail) -> None:
        """Add email to inbox"""
        self.inbox.append(email)

    def send_email(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> SimulatedEmail:
        """Send an email (adds to sent items)"""
        email = SimulatedEmail(
            from_address="employee@company.com",
            to_addresses=to,
            cc_addresses=cc or [],
            subject=subject,
            body=body,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            received_at=datetime.now(UTC),
            is_read=True,  # Sent emails are "read"
        )
        self.sent.append(email)
        return email

    def get_unread_emails(self) -> list[SimulatedEmail]:
        """Get unread emails from inbox"""
        return [email for email in self.inbox if not email.is_read]

    def mark_as_read(self, email_id: str) -> bool:
        """Mark email as read"""
        for email in self.inbox:
            if email.id == email_id:
                email.is_read = True
                return True
        return False

    def get_thread(self, thread_id: str) -> list[SimulatedEmail]:
        """Get all emails in a thread"""
        thread_emails = []
        for email in self.inbox + self.sent:
            if email.thread_id == thread_id:
                thread_emails.append(email)
        return sorted(thread_emails, key=lambda e: e.received_at)

    @property
    def sent_count(self) -> int:
        """Count of sent emails"""
        return len(self.sent)


class SimulatedCalendarSystem:
    """Simulated calendar system with events"""

    def __init__(self):
        self.events: list[SimulatedCalendarEvent] = []

    def create_event(
        self,
        subject: str,
        start_time: datetime,
        end_time: datetime,
        attendees: list[str] | None = None,
        location: str = "",
        description: str = "",
    ) -> SimulatedCalendarEvent:
        """Create a calendar event"""
        event = SimulatedCalendarEvent(
            subject=subject,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees or [],
            location=location,
            description=description,
            is_organizer=True,
        )
        self.events.append(event)
        return event

    def get_events(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[SimulatedCalendarEvent]:
        """Get events within time range"""
        events = self.events

        if start_time:
            events = [e for e in events if e.end_time >= start_time]

        if end_time:
            events = [e for e in events if e.start_time <= end_time]

        return sorted(events, key=lambda e: e.start_time)

    def get_upcoming_events(self, hours: int = 24) -> list[SimulatedCalendarEvent]:
        """Get events in the next N hours"""
        now = datetime.now(UTC)
        end_time = now + timedelta(hours=hours)
        return self.get_events(start_time=now, end_time=end_time)


class SimulatedCRMSystem:
    """Simulated CRM system with contacts, deals, and pipeline metrics"""

    def __init__(self):
        self.contacts: list[SimulatedContact] = []
        self.deals: list[SimulatedDeal] = []
        self.customers: list[SimulatedCustomer] = []
        self._pipeline_target: float = 500000.0  # Default $500K target

    def add_contact(self, contact: SimulatedContact) -> None:
        """Add a contact to CRM"""
        self.contacts.append(contact)

    def add_deal(self, deal: SimulatedDeal) -> None:
        """Add a deal to CRM"""
        self.deals.append(deal)

    def add_customer(self, customer: SimulatedCustomer) -> None:
        """Add a customer"""
        self.customers.append(customer)

    def get_pipeline_value(self) -> float:
        """Calculate total pipeline value (open deals)"""
        open_stages = [
            DealStage.PROSPECTING,
            DealStage.QUALIFICATION,
            DealStage.PROPOSAL,
            DealStage.NEGOTIATION,
        ]
        return sum(deal.value for deal in self.deals if deal.stage in open_stages)

    def get_pipeline_coverage(self) -> float:
        """
        Calculate pipeline coverage (pipeline / target).

        Returns:
            Pipeline coverage ratio, or 0.0 if target is zero/near-zero
        """
        # Guard against division-by-zero
        if self._pipeline_target == 0 or abs(self._pipeline_target) < 1e-9:
            return 0.0
        return self.get_pipeline_value() / self._pipeline_target

    def set_pipeline_target(self, target: float) -> None:
        """Set pipeline target"""
        self._pipeline_target = target

    def set_pipeline_coverage(self, coverage: float) -> None:
        """Set pipeline coverage by adjusting deals"""
        target_value = self._pipeline_target * coverage
        current_value = self.get_pipeline_value()

        if target_value > current_value:
            # Add a deal to reach target
            deal = SimulatedDeal(
                name="Placeholder Deal",
                value=target_value - current_value,
                stage=DealStage.PROSPECTING,
                probability=0.2,
            )
            self.add_deal(deal)

    def get_at_risk_customers(self) -> list[SimulatedCustomer]:
        """Get customers marked as at-risk"""
        return [c for c in self.customers if c.health == CustomerHealth.AT_RISK]

    def get_deals_by_stage(self, stage: DealStage) -> list[SimulatedDeal]:
        """Get deals at a specific stage"""
        return [d for d in self.deals if d.stage == stage]


class SimulatedMetricsSystem:
    """Track employee performance metrics"""

    def __init__(self):
        self.goals_created: int = 0
        self.goals_achieved: int = 0
        self.intentions_executed: int = 0
        self.emails_sent: int = 0
        self.meetings_scheduled: int = 0
        self.deals_created: int = 0
        self.deals_closed_won: int = 0
        self.deals_closed_lost: int = 0
        self.customer_interventions: int = 0
        self.custom_metrics: dict[str, Any] = {}

    def increment(self, metric: str, value: int = 1) -> None:
        """Increment a metric"""
        if hasattr(self, metric):
            setattr(self, metric, getattr(self, metric) + value)
        else:
            self.custom_metrics[metric] = self.custom_metrics.get(metric, 0) + value

    def get(self, metric: str) -> Any:
        """Get a metric value"""
        if hasattr(self, metric):
            return getattr(self, metric)
        return self.custom_metrics.get(metric, 0)

    def reset(self) -> None:
        """Reset all metrics"""
        self.__init__()


class SimulatedEnvironment:
    """
    Complete simulated environment for E2E testing.

    This provides a fake world for digital employees to interact with:
    - Email system (inbox, sent items)
    - Calendar system (events, meetings)
    - CRM system (deals, contacts, customers)
    - Metrics tracking

    Usage:
        env = SimulatedEnvironment()

        # Setup scenario
        env.email.receive_email(SimulatedEmail(
            from_address="prospect@company.com",
            subject="Interested in your product",
            body="Can we schedule a demo?"
        ))

        # Run employee with simulated capabilities
        employee = SalesAE(capabilities=get_simulated_capabilities(env))
        await employee.run_cycle()

        # Assert autonomous behavior
        assert env.email.sent_count > 0  # Employee replied
        assert env.metrics.get("emails_sent") > 0
    """

    def __init__(self):
        self.email = SimulatedEmailSystem()
        self.calendar = SimulatedCalendarSystem()
        self.crm = SimulatedCRMSystem()
        self.metrics = SimulatedMetricsSystem()

    def reset(self) -> None:
        """Reset all systems to clean state"""
        self.__init__()

    def get_state_summary(self) -> dict[str, Any]:
        """Get summary of current environment state"""
        return {
            "email": {
                "inbox_count": len(self.email.inbox),
                "unread_count": len(self.email.get_unread_emails()),
                "sent_count": self.email.sent_count,
            },
            "calendar": {
                "total_events": len(self.calendar.events),
                "upcoming_events": len(self.calendar.get_upcoming_events()),
            },
            "crm": {
                "contacts": len(self.crm.contacts),
                "deals": len(self.crm.deals),
                "pipeline_value": self.crm.get_pipeline_value(),
                "pipeline_coverage": self.crm.get_pipeline_coverage(),
                "customers": len(self.crm.customers),
                "at_risk_customers": len(self.crm.get_at_risk_customers()),
            },
            "metrics": {
                "goals_created": self.metrics.goals_created,
                "goals_achieved": self.metrics.goals_achieved,
                "intentions_executed": self.metrics.intentions_executed,
                "emails_sent": self.metrics.emails_sent,
            },
        }
