---
name: empla-capability
description: How to implement capabilities in empla. Use when creating new capabilities like email, calendar, CRM, or other integrations. Covers the BaseCapability interface, registration, and capability patterns.
---

# empla Capability Development

Capabilities are how employees interact with the outside world (email, calendar, CRM, etc.).

## Capability Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CapabilityRegistry                       │
│  - Manages capability instances per employee                │
│  - Handles enable/disable                                   │
│  - Routes perceive/execute calls                            │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ EmailCapability│   │CalendarCapability│ │ CRMCapability │
│               │   │               │   │               │
│ - perceive()  │   │ - perceive()  │   │ - perceive()  │
│ - execute()   │   │ - execute()   │   │ - execute()   │
└───────────────┘   └───────────────┘   └───────────────┘
```

## BaseCapability Interface

All capabilities extend `BaseCapability`:

```python
from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from empla.capabilities.base import BaseCapability, CapabilityType

class MyCapability(BaseCapability):
    """Custom capability implementation."""

    def __init__(self):
        super().__init__(CapabilityType.MY_TYPE)

    @abstractmethod
    async def initialize(self, employee_id: UUID, config: dict[str, Any]) -> None:
        """Initialize capability for an employee."""
        # Set up API clients, load credentials, etc.
        pass

    @abstractmethod
    async def perceive(self, employee_id: UUID) -> list[dict[str, Any]]:
        """
        Gather observations from this capability.

        Called by the proactive loop to get new information.
        Returns observations that will be processed into beliefs.
        """
        pass

    @abstractmethod
    async def execute_action(
        self,
        employee_id: UUID,
        action: str,
        parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Execute an action through this capability.

        Called when an intention needs to interact with this capability.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if capability is operational."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up resources."""
        pass
```

## Example: Email Capability

```python
from empla.capabilities.base import BaseCapability, CapabilityType

class EmailCapability(BaseCapability):
    """Email integration capability."""

    def __init__(self, provider: str = "microsoft"):
        super().__init__(CapabilityType.EMAIL)
        self.provider = provider
        self._clients: dict[UUID, EmailClient] = {}

    async def initialize(self, employee_id: UUID, config: dict[str, Any]) -> None:
        """Initialize email client for employee."""
        if self.provider == "microsoft":
            self._clients[employee_id] = MicrosoftGraphClient(
                client_id=config["client_id"],
                client_secret=config["client_secret"],
                tenant_id=config["tenant_id"]
            )
        # ... other providers

    async def perceive(self, employee_id: UUID) -> list[dict[str, Any]]:
        """Get new/unread emails as observations."""
        client = self._clients.get(employee_id)
        if not client:
            return []

        emails = await client.get_unread_emails(limit=50)

        return [
            {
                "type": "email_received",
                "source": "email",
                "timestamp": email.received_at.isoformat(),
                "data": {
                    "from": email.from_address,
                    "subject": email.subject,
                    "body": email.body[:1000],  # Truncate for LLM
                    "is_reply": email.is_reply,
                    "thread_id": email.thread_id,
                }
            }
            for email in emails
        ]

    async def execute_action(
        self,
        employee_id: UUID,
        action: str,
        parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute email actions."""
        client = self._clients.get(employee_id)
        if not client:
            return {"success": False, "error": "Not initialized"}

        if action == "send_email":
            result = await client.send_email(
                to=parameters["to"],
                subject=parameters["subject"],
                body=parameters["body"],
                reply_to=parameters.get("reply_to")
            )
            return {"success": True, "message_id": result.message_id}

        elif action == "reply_to_email":
            result = await client.reply(
                message_id=parameters["message_id"],
                body=parameters["body"]
            )
            return {"success": True, "message_id": result.message_id}

        return {"success": False, "error": f"Unknown action: {action}"}

    async def health_check(self) -> bool:
        """Check if email service is accessible."""
        # Check at least one client is healthy
        for client in self._clients.values():
            try:
                await client.ping()
                return True
            except Exception:
                continue
        return len(self._clients) == 0  # True if no clients (nothing to check)

    async def shutdown(self) -> None:
        """Close all email clients."""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
```

## Registering Capabilities

### Adding to CapabilityType Enum

```python
# empla/capabilities/__init__.py
from enum import Enum

class CapabilityType(Enum):
    EMAIL = "email"
    CALENDAR = "calendar"
    CRM = "crm"
    SLACK = "slack"
    # Add new capability types here
    MY_CAPABILITY = "my_capability"
```

### Registering with Registry

```python
from empla.capabilities import CapabilityRegistry, CapabilityType
from empla.capabilities.email import EmailCapability

# Create registry
registry = CapabilityRegistry()

# Register capability class
registry.register(CapabilityType.EMAIL, EmailCapability)

# Enable for specific employee
await registry.enable(
    capability_type=CapabilityType.EMAIL,
    employee_id=employee.id,
    config={"provider": "microsoft", ...}
)

# Use capability
observations = await registry.perceive(CapabilityType.EMAIL, employee.id)
result = await registry.execute(
    CapabilityType.EMAIL,
    employee.id,
    "send_email",
    {"to": "...", "subject": "...", "body": "..."}
)
```

## Observation Format

Observations from `perceive()` should follow this structure:

```python
{
    "type": "event_type",           # e.g., "email_received", "meeting_scheduled"
    "source": "capability_name",    # e.g., "email", "calendar"
    "timestamp": "ISO8601",         # When the event occurred
    "data": {                       # Event-specific data
        # ... depends on event type
    },
    "priority": "normal",           # Optional: "low", "normal", "high", "urgent"
}
```

## Testing Capabilities

### Unit Tests

```python
import pytest
from empla.capabilities.email import EmailCapability

async def test_email_perceive():
    capability = EmailCapability(provider="mock")

    # Mock the client
    capability._clients[employee_id] = MockEmailClient(
        emails=[
            MockEmail(from_addr="test@example.com", subject="Hello")
        ]
    )

    observations = await capability.perceive(employee_id)

    assert len(observations) == 1
    assert observations[0]["type"] == "email_received"
    assert observations[0]["data"]["from"] == "test@example.com"
```

### Integration with Simulated Capabilities

```python
from tests.simulation.capabilities import SimulatedEmailCapability

# Use in tests
registry = CapabilityRegistry()
registry.register(CapabilityType.EMAIL, SimulatedEmailCapability)
```

## Key Files

| File | Purpose |
|------|---------|
| `empla/capabilities/base.py` | BaseCapability interface |
| `empla/capabilities/registry.py` | CapabilityRegistry |
| `empla/capabilities/email.py` | Email capability |
| `empla/capabilities/__init__.py` | CapabilityType enum |
| `tests/simulation/capabilities.py` | Simulated capabilities for testing |

## Best Practices

1. **Always handle missing initialization** - Check if employee is initialized before operations
2. **Truncate large data** - Don't send full email bodies to LLM, truncate appropriately
3. **Return structured observations** - Follow the observation format for consistency
4. **Implement health_check** - Enable monitoring of capability health
5. **Clean shutdown** - Close connections, release resources in shutdown()
6. **Add to CapabilityType enum** - Don't use string literals for capability types
