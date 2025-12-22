"""
empla.api.v1.endpoints.employee_control - Employee Lifecycle Control Endpoints

REST API endpoints for starting, stopping, and controlling digital employees.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from empla.api.deps import CurrentUser, DBSession
from empla.api.v1.schemas.employee import EmployeeStatusResponse
from empla.models.employee import Employee
from empla.services.employee_manager import get_employee_manager

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_employee_for_tenant(
    db: DBSession,
    employee_id: UUID,
    tenant_id: UUID,
) -> Employee:
    """
    Fetch employee and verify it belongs to the tenant.

    Args:
        db: Database session
        employee_id: Employee UUID
        tenant_id: Tenant UUID

    Returns:
        Employee if found and belongs to tenant

    Raises:
        HTTPException: If employee not found or doesn't belong to tenant
    """
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == tenant_id,
            Employee.deleted_at.is_(None),
        )
    )
    employee = result.scalar_one_or_none()

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    return employee


@router.post("/{employee_id}/start", response_model=EmployeeStatusResponse)
async def start_employee(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> EmployeeStatusResponse:
    """
    Start a digital employee.

    Initializes the employee and starts the proactive execution loop.

    Args:
        db: Database session
        auth: Current user context
        employee_id: Employee UUID

    Returns:
        Employee status including runtime information

    Raises:
        HTTPException: If employee not found or already running
    """
    employee = await get_employee_for_tenant(db, employee_id, auth.tenant_id)
    manager = get_employee_manager()

    try:
        runtime_status = await manager.start_employee(employee_id, db)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Refresh to get updated status from manager
    await db.refresh(employee)

    logger.info(
        f"Employee {employee_id} started via API",
        extra={"employee_id": str(employee_id), "user_id": str(auth.user_id)},
    )

    return EmployeeStatusResponse(
        id=employee.id,
        name=employee.name,
        status=employee.status,
        lifecycle_stage=employee.lifecycle_stage,
        is_running=runtime_status.get("is_running", True),
    )


@router.post("/{employee_id}/stop", response_model=EmployeeStatusResponse)
async def stop_employee(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> EmployeeStatusResponse:
    """
    Stop a running employee.

    Gracefully shuts down the employee's execution loop.

    Args:
        db: Database session
        auth: Current user context
        employee_id: Employee UUID

    Returns:
        Final employee status

    Raises:
        HTTPException: If employee not found or not running
    """
    employee = await get_employee_for_tenant(db, employee_id, auth.tenant_id)
    manager = get_employee_manager()

    try:
        await manager.stop_employee(employee_id, db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    logger.info(
        f"Employee {employee_id} stopped via API",
        extra={"employee_id": str(employee_id), "user_id": str(auth.user_id)},
    )

    # Refresh employee from database
    await db.refresh(employee)

    return EmployeeStatusResponse(
        id=employee.id,
        name=employee.name,
        status=employee.status,
        lifecycle_stage=employee.lifecycle_stage,
        is_running=False,
    )


@router.post("/{employee_id}/pause", response_model=EmployeeStatusResponse)
async def pause_employee(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> EmployeeStatusResponse:
    """
    Pause a running employee.

    The employee remains in memory but stops executing cycles.

    Args:
        db: Database session
        auth: Current user context
        employee_id: Employee UUID

    Returns:
        Employee status

    Raises:
        HTTPException: If employee not found or not running
    """
    employee = await get_employee_for_tenant(db, employee_id, auth.tenant_id)
    manager = get_employee_manager()

    try:
        await manager.pause_employee(employee_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Update database status
    employee.status = "paused"
    await db.commit()

    logger.info(
        f"Employee {employee_id} paused via API",
        extra={"employee_id": str(employee_id), "user_id": str(auth.user_id)},
    )

    return EmployeeStatusResponse(
        id=employee.id,
        name=employee.name,
        status="paused",
        lifecycle_stage=employee.lifecycle_stage,
        is_running=True,  # Still running but paused
    )


@router.post("/{employee_id}/resume", response_model=EmployeeStatusResponse)
async def resume_employee(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> EmployeeStatusResponse:
    """
    Resume a paused employee.

    Args:
        db: Database session
        auth: Current user context
        employee_id: Employee UUID

    Returns:
        Employee status

    Raises:
        HTTPException: If employee not found or not paused
    """
    employee = await get_employee_for_tenant(db, employee_id, auth.tenant_id)
    manager = get_employee_manager()

    try:
        await manager.resume_employee(employee_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Update database status
    employee.status = "active"
    await db.commit()

    logger.info(
        f"Employee {employee_id} resumed via API",
        extra={"employee_id": str(employee_id), "user_id": str(auth.user_id)},
    )

    return EmployeeStatusResponse(
        id=employee.id,
        name=employee.name,
        status="active",
        lifecycle_stage=employee.lifecycle_stage,
        is_running=True,
    )


@router.get("/{employee_id}/status", response_model=EmployeeStatusResponse)
async def get_employee_status(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> EmployeeStatusResponse:
    """
    Get runtime status for an employee.

    Args:
        db: Database session
        auth: Current user context
        employee_id: Employee UUID

    Returns:
        Employee runtime status

    Raises:
        HTTPException: If employee not found
    """
    employee = await get_employee_for_tenant(db, employee_id, auth.tenant_id)
    manager = get_employee_manager()
    runtime_status = manager.get_status(employee_id)

    return EmployeeStatusResponse(
        id=employee.id,
        name=employee.name,
        status=employee.status,
        lifecycle_stage=employee.lifecycle_stage,
        is_running=runtime_status.get("is_running", False),
    )
