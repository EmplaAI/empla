"""
Integration tests for ComputeCapability with CapabilityRegistry.

Follows the same pattern as test_workspace_capability_integration.py.
"""

import sys
from uuid import uuid4

import pytest

from empla.capabilities import (
    CAPABILITY_COMPUTE,
    CAPABILITY_WORKSPACE,
    Action,
    CapabilityRegistry,
    ComputeCapability,
    ComputeConfig,
    WorkspaceCapability,
    WorkspaceConfig,
)


@pytest.mark.asyncio
async def test_compute_capability_registration():
    """Test registering ComputeCapability with registry."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_COMPUTE, ComputeCapability)

    assert CAPABILITY_COMPUTE in registry._capabilities
    assert registry._capabilities[CAPABILITY_COMPUTE] == ComputeCapability


@pytest.mark.asyncio
async def test_compute_capability_enable_for_employee(tmp_path):
    """Test enabling ComputeCapability for an employee."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_COMPUTE, ComputeCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = ComputeConfig(
        workspace_base_path=str(tmp_path),
        python_path=sys.executable,
    )

    capability = await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_COMPUTE,
        config=config,
    )

    assert capability is not None
    assert capability.capability_type == CAPABILITY_COMPUTE
    assert capability._initialized is True
    assert employee_id in registry._instances
    assert CAPABILITY_COMPUTE in registry._instances[employee_id]


@pytest.mark.asyncio
async def test_compute_perceive_via_registry(tmp_path):
    """Test perceiving via registry with ComputeCapability (always empty)."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_COMPUTE, ComputeCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = ComputeConfig(
        workspace_base_path=str(tmp_path),
        python_path=sys.executable,
    )

    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_COMPUTE,
        config=config,
    )

    observations = await registry.perceive_all(employee_id)
    assert isinstance(observations, list)
    assert observations == []


@pytest.mark.asyncio
async def test_compute_execute_via_registry(tmp_path):
    """Test executing compute action via registry."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_COMPUTE, ComputeCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = ComputeConfig(
        workspace_base_path=str(tmp_path),
        python_path=sys.executable,
    )

    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_COMPUTE,
        config=config,
    )

    action = Action(
        capability="compute",
        operation="execute_script",
        parameters={"code": "print(2 + 2)"},
    )
    result = await registry.execute_action(employee_id, action)
    assert result.success is True
    assert "4" in result.output["stdout"]


@pytest.mark.asyncio
async def test_compute_disable_for_employee(tmp_path):
    """Test disabling ComputeCapability for an employee."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_COMPUTE, ComputeCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = ComputeConfig(
        workspace_base_path=str(tmp_path),
        python_path=sys.executable,
    )

    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_COMPUTE,
        config=config,
    )

    assert CAPABILITY_COMPUTE in registry._instances[employee_id]

    await registry.disable_for_employee(employee_id, CAPABILITY_COMPUTE)
    assert CAPABILITY_COMPUTE not in registry._instances[employee_id]


@pytest.mark.asyncio
async def test_compute_health_check(tmp_path):
    """Test health check for ComputeCapability via registry."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_COMPUTE, ComputeCapability)

    tenant_id = uuid4()
    employee_id = uuid4()
    config = ComputeConfig(
        workspace_base_path=str(tmp_path),
        python_path=sys.executable,
    )

    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_COMPUTE,
        config=config,
    )

    health = registry.health_check(employee_id)
    assert len(health) == 1
    assert health[CAPABILITY_COMPUTE] is True


@pytest.mark.asyncio
async def test_compute_and_workspace_coexist(tmp_path):
    """Test compute + workspace capabilities for same employee."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_COMPUTE, ComputeCapability)
    registry.register(CAPABILITY_WORKSPACE, WorkspaceCapability)

    tenant_id = uuid4()
    employee_id = uuid4()

    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_COMPUTE,
        config=ComputeConfig(
            workspace_base_path=str(tmp_path),
            python_path=sys.executable,
        ),
    )

    await registry.enable_for_employee(
        employee_id=employee_id,
        tenant_id=tenant_id,
        capability_type=CAPABILITY_WORKSPACE,
        config=WorkspaceConfig(base_path=str(tmp_path)),
    )

    health = registry.health_check(employee_id)
    assert health[CAPABILITY_COMPUTE] is True
    assert health[CAPABILITY_WORKSPACE] is True


@pytest.mark.asyncio
async def test_two_employees_isolated_compute(tmp_path):
    """Test that two employees have isolated compute workspaces."""
    registry = CapabilityRegistry()
    registry.register(CAPABILITY_COMPUTE, ComputeCapability)

    tenant_id = uuid4()
    emp1 = uuid4()
    emp2 = uuid4()

    for emp_id in [emp1, emp2]:
        await registry.enable_for_employee(
            employee_id=emp_id,
            tenant_id=tenant_id,
            capability_type=CAPABILITY_COMPUTE,
            config=ComputeConfig(
                workspace_base_path=str(tmp_path),
                python_path=sys.executable,
            ),
        )

    # Employee 1 writes a file via script
    write_action = Action(
        capability="compute",
        operation="execute_script",
        parameters={"code": "open('secret.txt', 'w').write('emp1 only')"},
    )
    await registry.execute_action(emp1, write_action)

    # Employee 2 should NOT see the file
    read_action = Action(
        capability="compute",
        operation="execute_script",
        parameters={"code": "print(open('secret.txt').read())"},
    )
    result = await registry.execute_action(emp2, read_action)
    assert result.success is False  # FileNotFoundError
