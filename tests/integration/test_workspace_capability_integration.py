"""
Integration tests for WorkspaceCapability with CapabilityRegistry.

Follows the same pattern as test_email_capability_integration.py.
"""

from uuid import uuid4

import pytest

from empla.capabilities import (
    CAPABILITY_EMAIL,
    CAPABILITY_WORKSPACE,
    Action,
    CapabilityRegistry,
    EmailCapability,
    EmailConfig,
    EmailProvider,
    WorkspaceCapability,
    WorkspaceConfig,
)


@pytest.mark.asyncio
async def test_workspace_capability_registration():
    """Test registering WorkspaceCapability with registry."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_WORKSPACE, WorkspaceCapability)

    assert CAPABILITY_WORKSPACE in registry._capabilities
    assert registry._capabilities[CAPABILITY_WORKSPACE] == WorkspaceCapability


@pytest.mark.asyncio
async def test_workspace_capability_enable_for_employee(tmp_path):
    """Test enabling WorkspaceCapability for an employee."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_WORKSPACE, WorkspaceCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = WorkspaceConfig(base_path=str(tmp_path))

    capability = await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_WORKSPACE,
        config=config,
    )

    assert capability is not None
    assert capability.capability_type == CAPABILITY_WORKSPACE
    assert capability._initialized is True
    assert employee_id in registry._instances
    assert CAPABILITY_WORKSPACE in registry._instances[employee_id]


@pytest.mark.asyncio
async def test_workspace_perceive_via_registry(tmp_path):
    """Test perceiving via registry with WorkspaceCapability."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_WORKSPACE, WorkspaceCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = WorkspaceConfig(base_path=str(tmp_path))

    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_WORKSPACE,
        config=config,
    )

    observations = await registry.perceive_all(employee_id)
    assert isinstance(observations, list)


@pytest.mark.asyncio
async def test_workspace_execute_via_registry(tmp_path):
    """Test executing workspace action via registry."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_WORKSPACE, WorkspaceCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = WorkspaceConfig(base_path=str(tmp_path))

    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_WORKSPACE,
        config=config,
    )

    # Write a file
    action = Action(
        capability="workspace",
        operation="write_file",
        parameters={"path": "notes/test.md", "content": "# Integration Test"},
    )
    result = await registry.execute_action(employee_id, action)
    assert result.success is True

    # Read it back
    read_action = Action(
        capability="workspace",
        operation="read_file",
        parameters={"path": "notes/test.md"},
    )
    result = await registry.execute_action(employee_id, read_action)
    assert result.success is True
    assert result.output["content"] == "# Integration Test"


@pytest.mark.asyncio
async def test_workspace_disable_for_employee(tmp_path):
    """Test disabling WorkspaceCapability for an employee."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_WORKSPACE, WorkspaceCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = WorkspaceConfig(base_path=str(tmp_path))

    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_WORKSPACE,
        config=config,
    )

    assert CAPABILITY_WORKSPACE in registry._instances[employee_id]

    await registry.disable_for_employee(employee_id, CAPABILITY_WORKSPACE)
    assert CAPABILITY_WORKSPACE not in registry._instances[employee_id]


@pytest.mark.asyncio
async def test_workspace_health_check(tmp_path):
    """Test health check for WorkspaceCapability via registry."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_WORKSPACE, WorkspaceCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = WorkspaceConfig(base_path=str(tmp_path))

    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_WORKSPACE,
        config=config,
    )

    health = registry.health_check(employee_id)
    assert len(health) == 1
    assert health[CAPABILITY_WORKSPACE] is True


@pytest.mark.asyncio
async def test_workspace_and_email_coexist(tmp_path):
    """Test workspace + email capabilities for same employee."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_WORKSPACE, WorkspaceCapability)
    registry.register(CAPABILITY_EMAIL, EmailCapability)

    tenant_id = uuid4()
    employee_id = uuid4()

    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_WORKSPACE,
        config=WorkspaceConfig(base_path=str(tmp_path)),
    )

    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_EMAIL,
        config=EmailConfig(
            provider=EmailProvider.MICROSOFT_GRAPH,
            email_address="emp@company.com",
            credentials={},
        ),
    )

    health = registry.health_check(employee_id)
    assert health[CAPABILITY_WORKSPACE] is True
    assert health[CAPABILITY_EMAIL] is True


@pytest.mark.asyncio
async def test_two_employees_isolated_workspaces(tmp_path):
    """Test that two employees have isolated workspaces."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_WORKSPACE, WorkspaceCapability)

    tenant_id = uuid4()
    emp1 = uuid4()
    emp2 = uuid4()

    await registry.enable_for_employee(
        employee_id=emp1,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_WORKSPACE,
        config=WorkspaceConfig(base_path=str(tmp_path)),
    )

    await registry.enable_for_employee(
        employee_id=emp2,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_WORKSPACE,
        config=WorkspaceConfig(base_path=str(tmp_path)),
    )

    # Employee 1 writes a file
    write_action = Action(
        capability="workspace",
        operation="write_file",
        parameters={"path": "notes/secret.txt", "content": "emp1 only"},
    )
    await registry.execute_action(emp1, write_action)

    # Employee 2 should NOT see it
    read_action = Action(
        capability="workspace",
        operation="read_file",
        parameters={"path": "notes/secret.txt"},
    )
    result = await registry.execute_action(emp2, read_action)
    assert result.success is False  # File not found in emp2's workspace
