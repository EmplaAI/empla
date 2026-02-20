"""
Integration tests for EmailCapability with CapabilityRegistry.
"""

from uuid import uuid4

import pytest

from empla.capabilities import (
    CAPABILITY_EMAIL,
    Action,
    CapabilityRegistry,
    EmailCapability,
    EmailConfig,
    EmailProvider,
)


@pytest.mark.asyncio
async def test_email_capability_registration():
    """Test registering EmailCapability with registry"""
    registry = CapabilityRegistry()

    # Register email capability
    registry.register(CAPABILITY_EMAIL, EmailCapability)

    assert CAPABILITY_EMAIL in registry._capabilities
    assert registry._capabilities[CAPABILITY_EMAIL] == EmailCapability


@pytest.mark.asyncio
async def test_email_capability_enable_for_employee():
    """Test enabling EmailCapability for an employee"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, EmailCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="employee@company.com",
        credentials={},
    )

    # Enable capability
    capability = await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )

    assert capability is not None
    assert capability.capability_type == CAPABILITY_EMAIL
    assert capability._initialized is True
    assert employee_id in registry._instances
    assert CAPABILITY_EMAIL in registry._instances[employee_id]


@pytest.mark.asyncio
async def test_email_capability_perceive_via_registry():
    """Test perceiving via registry with EmailCapability"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, EmailCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="employee@company.com",
        credentials={},
    )

    # Enable capability
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )

    # Perceive via registry
    observations = await registry.perceive_all(employee_id)

    # Should return empty list (no actual emails in placeholder implementation)
    assert isinstance(observations, list)
    assert len(observations) == 0


@pytest.mark.asyncio
async def test_email_capability_execute_action_via_registry():
    """Test executing email action via registry"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, EmailCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="employee@company.com",
        credentials={},
        signature="Best regards,\nTest Employee",
    )

    # Enable capability
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )

    # Execute action via registry
    action = Action(
        capability="email",
        operation="send_email",
        parameters={
            "to": ["customer@example.com"],
            "subject": "Thank you for your inquiry",
            "body": "We appreciate your interest in our product.",
        },
    )

    result = await registry.execute_action(employee_id, action)

    assert result.success is True
    assert "sent_at" in result.metadata


@pytest.mark.asyncio
async def test_email_capability_disable_for_employee():
    """Test disabling EmailCapability for an employee"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, EmailCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="employee@company.com",
        credentials={},
    )

    # Enable capability
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )

    assert CAPABILITY_EMAIL in registry._instances[employee_id]

    # Disable capability
    await registry.disable_for_employee(employee_id, CAPABILITY_EMAIL)

    assert CAPABILITY_EMAIL not in registry._instances[employee_id]


@pytest.mark.asyncio
async def test_email_capability_health_check():
    """Test health check for EmailCapability via registry"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, EmailCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="employee@company.com",
        credentials={},
    )

    # Enable capability
    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config,
    )

    # Health check
    health = registry.health_check(employee_id)

    assert len(health) == 1
    assert health[CAPABILITY_EMAIL] is True


@pytest.mark.asyncio
async def test_multiple_providers():
    """Test EmailCapability with different providers"""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_EMAIL, EmailCapability)

    tenant_id = uuid4()

    # Employee 1 with Microsoft Graph
    employee1_id = uuid4()
    config1 = EmailConfig(
        provider=EmailProvider.MICROSOFT_GRAPH,
        email_address="employee1@company.com",
        credentials={},
    )

    await registry.enable_for_employee(
        employee_id=employee1_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config1,
    )

    # Employee 2 with Gmail
    employee2_id = uuid4()
    config2 = EmailConfig(
        provider=EmailProvider.GMAIL,
        email_address="employee2@company.com",
        credentials={},
    )

    await registry.enable_for_employee(
        employee_id=employee2_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=config2,
    )

    # Both should be healthy
    health1 = registry.health_check(employee1_id)
    health2 = registry.health_check(employee2_id)

    assert health1[CAPABILITY_EMAIL] is True
    assert health2[CAPABILITY_EMAIL] is True
