"""
empla.api.v1.endpoints.employee_control - Employee Lifecycle Control Endpoints

REST API endpoints for starting, stopping, and controlling digital employees.
Pause/resume work via DB-only updates — the employee subprocess reads its
status from DB each cycle (pause-via-DB pattern).
"""

import logging
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from empla.api.deps import CurrentUser, DBSession
from empla.api.v1.schemas.employee import (
    EmployeeStatus,
    EmployeeStatusResponse,
    LifecycleStage,
)
from empla.models.employee import Employee
from empla.services.employee_manager import UnsupportedRoleError, get_employee_manager

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

    Spawns the employee as a subprocess and starts the proactive execution loop.
    """
    employee = await get_employee_for_tenant(db, employee_id, auth.tenant_id)
    manager = get_employee_manager()

    try:
        runtime_status = await manager.start_employee(employee_id, auth.tenant_id, db)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e
    except UnsupportedRoleError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    await db.refresh(employee)

    logger.info(
        f"Employee {employee_id} started via API",
        extra={"employee_id": str(employee_id), "user_id": str(auth.user_id)},
    )

    return EmployeeStatusResponse(
        id=employee.id,
        name=employee.name,
        status=cast(EmployeeStatus, employee.status),
        lifecycle_stage=cast(LifecycleStage, employee.lifecycle_stage),
        is_running=runtime_status.get("is_running", True),
        is_paused=employee.status == "paused",
        has_error=runtime_status.get("has_error", False),
        last_error=runtime_status.get("last_error"),
    )


@router.post("/{employee_id}/stop", response_model=EmployeeStatusResponse)
async def stop_employee(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> EmployeeStatusResponse:
    """
    Stop a running employee.

    Sends SIGTERM to the employee subprocess for graceful shutdown.
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

    await db.refresh(employee)

    return EmployeeStatusResponse(
        id=employee.id,
        name=employee.name,
        status=cast(EmployeeStatus, employee.status),
        lifecycle_stage=cast(LifecycleStage, employee.lifecycle_stage),
        is_running=False,
        is_paused=False,
        has_error=False,
    )


@router.post("/{employee_id}/pause", response_model=EmployeeStatusResponse)
async def pause_employee(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> EmployeeStatusResponse:
    """
    Pause a running employee.

    Sets DB status to 'paused'. The employee subprocess reads this each
    cycle and sleeps until status changes back to 'active'.
    """
    employee = await get_employee_for_tenant(db, employee_id, auth.tenant_id)
    manager = get_employee_manager()

    try:
        await manager.pause_employee(employee_id, db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    await db.refresh(employee)
    runtime_status = manager.get_status(employee_id)

    logger.info(
        f"Employee {employee_id} paused via API",
        extra={"employee_id": str(employee_id), "user_id": str(auth.user_id)},
    )

    return EmployeeStatusResponse(
        id=employee.id,
        name=employee.name,
        status=cast(EmployeeStatus, employee.status),
        lifecycle_stage=cast(LifecycleStage, employee.lifecycle_stage),
        is_running=runtime_status.get("is_running", False),
        is_paused=employee.status == "paused",
        has_error=runtime_status.get("has_error", False),
        last_error=runtime_status.get("last_error"),
    )


@router.post("/{employee_id}/resume", response_model=EmployeeStatusResponse)
async def resume_employee(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> EmployeeStatusResponse:
    """
    Resume a paused employee.

    Sets DB status back to 'active'. The employee subprocess picks this
    up on its next status check.
    """
    employee = await get_employee_for_tenant(db, employee_id, auth.tenant_id)
    manager = get_employee_manager()

    try:
        await manager.resume_employee(employee_id, db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    await db.refresh(employee)
    runtime_status = manager.get_status(employee_id)

    logger.info(
        f"Employee {employee_id} resumed via API",
        extra={"employee_id": str(employee_id), "user_id": str(auth.user_id)},
    )

    return EmployeeStatusResponse(
        id=employee.id,
        name=employee.name,
        status=cast(EmployeeStatus, employee.status),
        lifecycle_stage=cast(LifecycleStage, employee.lifecycle_stage),
        is_running=runtime_status.get("is_running", False),
        is_paused=employee.status == "paused",
        has_error=runtime_status.get("has_error", False),
        last_error=runtime_status.get("last_error"),
    )


@router.get("/{employee_id}/status", response_model=EmployeeStatusResponse)
async def get_employee_status(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> EmployeeStatusResponse:
    """
    Get runtime status for an employee.

    Combines DB status with subprocess health information.
    """
    employee = await get_employee_for_tenant(db, employee_id, auth.tenant_id)
    manager = get_employee_manager()
    runtime_status = manager.get_status(employee_id)

    return EmployeeStatusResponse(
        id=employee.id,
        name=employee.name,
        status=cast(EmployeeStatus, employee.status),
        lifecycle_stage=cast(LifecycleStage, employee.lifecycle_stage),
        is_running=runtime_status.get("is_running", False),
        is_paused=employee.status == "paused",
        has_error=runtime_status.get("has_error", False),
        last_error=runtime_status.get("last_error"),
    )


@router.get(
    "/{employee_id}/health",
    responses={
        200: {"description": "Employee health data"},
        503: {"description": "Employee health endpoint not reachable"},
    },
)
async def get_employee_health(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> dict[str, Any]:
    """
    Proxy health check to the employee subprocess.

    Returns the health data from the employee's health endpoint,
    or 503 if the employee is not reachable.
    """
    await get_employee_for_tenant(db, employee_id, auth.tenant_id)
    manager = get_employee_manager()

    health = await manager.get_health(employee_id)
    if health is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Employee health endpoint is not reachable",
        )

    return health
