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
from empla.capabilities.base import (
    BaseCapability,
    Action,
    ActionResult,
    Observation,
)

# Define a constant for your capability type
CAPABILITY_MY_TYPE: str = "my_type"

class MyCapability(BaseCapability):
    """Custom capability implementation."""

    @property
    def capability_type(self) -> str:
        return CAPABILITY_MY_TYPE

    async def initialize(self) -> None:
        """Initialize capability (set up API clients, etc.)."""
        self._initialized = True

    async def perceive(self) -> list[Observation]:
        """
        Gather observations from this capability.

        Called by the proactive loop to get new information.
        Returns observations that will be processed into beliefs.
        """
        return []

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        """
        Execute an action through this capability.

        Called when an intention needs to interact with this capability.
        """
        return ActionResult(success=True, output={})

    async def shutdown(self) -> None:
        """Clean up resources."""
        pass
```

## Example: Email Capability

```python
from empla.capabilities.base import BaseCapability, CAPABILITY_EMAIL

class EmailCapability(BaseCapability):
    """Email integration capability."""

    @property
    def capability_type(self) -> str:
        return CAPABILITY_EMAIL

    async def initialize(self) -> None:
        """Initialize email client using self.config."""
        provider = self.config.settings.get("provider", "microsoft")
        if provider == "microsoft":
            self._client = MicrosoftGraphClient(
                client_id=self.config.settings["client_id"],
                client_secret=self.config.settings["client_secret"],
            )
        self._initialized = True

    async def perceive(self) -> list[Observation]:
        """Get new/unread emails as observations."""
        if not self._initialized:
            return []

        emails = await self._client.get_unread_emails(limit=50)

        return [
            Observation(
                employee_id=self.employee_id,
                tenant_id=self.tenant_id,
                observation_type="email_received",
                source="email",
                content={
                    "from": email.from_address,
                    "subject": email.subject,
                    "body": email.body[:1000],  # Truncate for LLM
                },
                timestamp=email.received_at,
                priority=7,
            )
            for email in emails
        ]

    async def _execute_action_impl(self, action: Action) -> ActionResult:
        """Execute email actions."""
        if action.operation == "send_email":
            result = await self._client.send_email(
                to=action.parameters["to"],
                subject=action.parameters["subject"],
                body=action.parameters["body"],
            )
            return ActionResult(success=True, output={"message_id": result.message_id})

        return ActionResult(success=False, error=f"Unknown operation: {action.operation}")

    async def shutdown(self) -> None:
        """Close email client."""
        if hasattr(self, "_client"):
            await client.close()
            await self._client.close()
```

## Registering Capabilities

### Defining Capability Type Constants

Capability types are plain strings. Well-known constants are defined in
`empla/capabilities/base.py` for discoverability, but any string is valid:

```python
# empla/capabilities/base.py — well-known constants
CAPABILITY_EMAIL: str = "email"
CAPABILITY_CALENDAR: str = "calendar"
CAPABILITY_CRM: str = "crm"

# To add a new capability, just define a constant (no enum changes needed):
CAPABILITY_SLACK: str = "slack"
CAPABILITY_MY_CAPABILITY: str = "my_capability"
```

### Registering with Registry

```python
from empla.capabilities import CapabilityRegistry, CAPABILITY_EMAIL
from empla.capabilities.email import EmailCapability

# Create registry
registry = CapabilityRegistry()

# Register capability class
registry.register(CAPABILITY_EMAIL, EmailCapability)

# Enable for specific employee
await registry.enable_for_employee(
    capability_type=CAPABILITY_EMAIL,
    employee_id=employee.id,
    tenant_id=employee.tenant_id,
    config=EmailConfig(...)
)

# Perceive environment
observations = await registry.perceive_all(employee.id)

# Execute action
result = await registry.execute_action(employee.id, action)
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
from empla.capabilities import CapabilityRegistry, CAPABILITY_EMAIL

# Use in tests
registry = CapabilityRegistry()
registry.register(CAPABILITY_EMAIL, SimulatedEmailCapability)
```

## Key Files

| File | Purpose |
|------|---------|
| `empla/capabilities/base.py` | BaseCapability interface |
| `empla/capabilities/registry.py` | CapabilityRegistry |
| `empla/capabilities/email.py` | Email capability |
| `empla/capabilities/__init__.py` | Capability constants + re-exports |
| `tests/simulation/capabilities.py` | Simulated capabilities for testing |

## Best Practices

1. **Always handle missing initialization** - Check if employee is initialized before operations
2. **Truncate large data** - Don't send full email bodies to LLM, truncate appropriately
3. **Return structured observations** - Follow the observation format for consistency
4. **Implement health_check** - Enable monitoring of capability health
5. **Clean shutdown** - Close connections, release resources in shutdown()
6. **Use well-known constants** - Import `CAPABILITY_EMAIL` etc. instead of raw string literals for discoverability
