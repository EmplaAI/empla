"""
empla.api.v1.endpoints.employees - Employee CRUD Endpoints

REST API endpoints for managing digital employees.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from empla.api.deps import CurrentUser, DBSession
from empla.api.v1.schemas.employee import (
    EmployeeCreate,
    EmployeeListResponse,
    EmployeeResponse,
    EmployeeUpdate,
)
from empla.models.employee import Employee, EmployeeGoal

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=EmployeeListResponse)
async def list_employees(
    db: DBSession,
    auth: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    role_filter: Annotated[str | None, Query(alias="role")] = None,
) -> EmployeeListResponse:
    """
    List employees for the current tenant.

    Args:
        db: Database session
        auth: Current user context
        page: Page number (1-indexed)
        page_size: Items per page (max 100)
        status_filter: Filter by status (onboarding, active, paused, terminated)
        role_filter: Filter by role (sales_ae, csm, pm, etc.)

    Returns:
        Paginated list of employees
    """
    # Base query scoped to tenant
    query = select(Employee).where(
        Employee.tenant_id == auth.tenant_id,
        Employee.deleted_at.is_(None),
    )

    # Apply filters
    if status_filter:
        query = query.where(Employee.status == status_filter)
    if role_filter:
        query = query.where(Employee.role == role_filter)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(Employee.created_at.desc()).offset(offset).limit(page_size)

    # Execute
    result = await db.execute(query)
    employees = result.scalars().all()

    # Calculate pages
    pages = (total + page_size - 1) // page_size if total > 0 else 1

    # Check runtime status for each employee

    items = []
    for emp in employees:
        response = EmployeeResponse.model_validate(emp)
        response.is_running = emp.status == "active"
        items.append(response)

    return EmployeeListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    db: DBSession,
    auth: CurrentUser,
    data: EmployeeCreate,
) -> EmployeeResponse:
    """
    Create a new digital employee.

    For built-in roles (``sales_ae``, ``csm``, ``pm``, ``sdr``,
    ``recruiter``) the runtime resolves goals + personality + capabilities
    from ``ROLE_CATALOG``; ``role_description`` and ``goals`` in the body
    are ignored. For ``role='custom'`` the body MUST carry both
    ``role_description`` (interpolated into the LLM system prompt) and
    a non-empty ``goals`` list — these are persisted on the Employee row
    and seeded as ``EmployeeGoal`` rows so the runner reads them on
    start. There is no separate "custom role" table; each custom
    employee is one-off.

    Returns 422 when ``role='custom'`` lacks the required custom-role
    fields, 409 on duplicate email.
    """
    # Prompt-bound field gate: role_description, goals, and
    # config["role_description"] are interpolated into the LLM system
    # prompt (via identity.py). Only admins may supply these — members
    # get their prompt-influencing state from ROLE_CATALOG defaults.
    _has_prompt_fields = bool(
        data.role_description or data.goals or (data.config or {}).get("role_description")
    )
    if _has_prompt_fields and auth.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Admin access required to set role_description, goals, or "
                "config.role_description. Members use built-in role defaults."
            ),
        )

    # Custom-role-specific: require both fields.
    if data.role == "custom":
        if not data.role_description:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="role_description is required when role='custom'",
            )
        if not data.goals:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="goals must be a non-empty list when role='custom'",
            )

    # Check for duplicate email
    existing = await db.execute(
        select(Employee).where(
            Employee.tenant_id == auth.tenant_id,
            Employee.email == data.email,
            Employee.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Employee with email {data.email} already exists",
        )

    # Materialize role_description into Employee.config JSONB. The runner's
    # config builder reads it from db_config["role_description"] (see
    # empla/runner/main.py) — we don't have a top-level column for it.
    db_config = dict(data.config or {})
    if data.role == "custom" and data.role_description:
        db_config["role_description"] = data.role_description

    # Create employee
    employee = Employee(
        tenant_id=auth.tenant_id,
        name=data.name,
        role=data.role,
        email=data.email,
        capabilities=data.capabilities,
        personality=data.personality,
        config=db_config,
        status="onboarding",
        lifecycle_stage="shadow",
        created_by=auth.user_id,
    )

    db.add(employee)
    await db.flush()  # assign employee.id without committing — we still need
    # to attach goals before the single commit below

    # Seed EmployeeGoal rows from request. For custom roles this is the only
    # source of truth; for built-ins we accept goals as an override (rare,
    # but admins can shape a built-in's goals at creation time).
    if data.goals:
        for g in data.goals:
            db.add(
                EmployeeGoal(
                    tenant_id=auth.tenant_id,
                    employee_id=employee.id,
                    goal_type=g.goal_type,
                    description=g.description,
                    priority=g.priority,
                    target=g.target,
                )
            )

    await db.commit()
    await db.refresh(employee)

    logger.info(
        f"Created employee {employee.id}",
        extra={
            "employee_id": str(employee.id),
            "tenant_id": str(auth.tenant_id),
            "role": data.role,
            "goals_seeded": len(data.goals or []),
        },
    )

    # New employees are never running, but check for consistency with other endpoints

    response = EmployeeResponse.model_validate(employee)
    response.is_running = employee.status == "active"

    return response


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> EmployeeResponse:
    """
    Get a specific employee by ID.

    Args:
        db: Database session
        auth: Current user context
        employee_id: Employee UUID

    Returns:
        Employee details

    Raises:
        HTTPException: If employee not found
    """
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == auth.tenant_id,
            Employee.deleted_at.is_(None),
        )
    )
    employee = result.scalar_one_or_none()

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    # Check runtime status

    response = EmployeeResponse.model_validate(employee)
    response.is_running = employee.status == "active"

    return response


@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
    data: EmployeeUpdate,
) -> EmployeeResponse:
    """
    Update an employee.

    Args:
        db: Database session
        auth: Current user context
        employee_id: Employee UUID
        data: Update data

    Returns:
        Updated employee

    Raises:
        HTTPException: If employee not found or email conflict
    """
    # Fetch employee
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == auth.tenant_id,
            Employee.deleted_at.is_(None),
        )
    )
    employee = result.scalar_one_or_none()

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    # Check email uniqueness if changing
    if data.email and data.email != employee.email:
        existing = await db.execute(
            select(Employee).where(
                Employee.tenant_id == auth.tenant_id,
                Employee.email == data.email,
                Employee.id != employee_id,
                Employee.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Employee with email {data.email} already exists",
            )

    # Capture original status before applying updates
    previous_status = employee.status

    # Prompt-bound field gate for updates. Same rationale as POST:
    # role_description, goals, and config["role_description"] land in the
    # system prompt. Non-admins must not set them via PUT.
    update_data = data.model_dump(exclude_unset=True)
    _config_update = update_data.get("config")
    _has_prompt_fields = bool(
        _config_update
        and isinstance(_config_update, dict)
        and _config_update.get("role_description")
    )
    if _has_prompt_fields and auth.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required to modify config.role_description",
        )

    # Apply updates
    for field, value in update_data.items():
        setattr(employee, field, value)

    # Handle status transitions: set activated_at only on transition into active
    if data.status == "active" and previous_status != "active":
        employee.activated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(employee)

    logger.info(
        f"Updated employee {employee.id}",
        extra={"employee_id": str(employee.id), "updates": list(update_data.keys())},
    )

    # Check runtime status

    response = EmployeeResponse.model_validate(employee)
    response.is_running = employee.status == "active"

    return response


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(
    db: DBSession,
    auth: CurrentUser,
    employee_id: UUID,
) -> None:
    """
    Soft delete an employee.

    Args:
        db: Database session
        auth: Current user context
        employee_id: Employee UUID

    Raises:
        HTTPException: If employee not found
    """
    # Fetch employee
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == auth.tenant_id,
            Employee.deleted_at.is_(None),
        )
    )
    employee = result.scalar_one_or_none()

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    # Soft delete
    employee.deleted_at = datetime.now(UTC)
    employee.status = "terminated"

    await db.commit()

    logger.info(
        f"Deleted employee {employee.id}",
        extra={"employee_id": str(employee.id), "tenant_id": str(auth.tenant_id)},
    )
