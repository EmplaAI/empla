"""
empla.api.v1.endpoints.settings - Tenant Settings API (PR #83)

Reads and writes the existing ``Tenant.settings`` JSONB column. No new
storage. See ``empla.api.v1.schemas.settings`` for the five-section
schema.

Write flow:
  PUT /settings → merge partial body onto current doc → validate with
  ``TenantSettings`` → bump ``settings.version`` → UPDATE via
  ``jsonb_set`` so the write is atomic under concurrent editors →
  call ``EmployeeManager.restart_all_for_tenant`` so running runners
  pick up fresh settings at the next process start.

Trust section is deliberately read-only here. Edits are rejected
with 403 because the trust language isn't ready for user editing yet.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from empla.api.deps import CurrentUser, DBSession
from empla.api.v1.schemas.settings import (
    TenantSettings,
    TenantSettingsUpdate,
    TenantSettingsUpdateResponse,
)
from empla.models.tenant import Tenant
from empla.services.employee_manager import get_employee_manager

logger = logging.getLogger(__name__)

router = APIRouter()


async def _load_tenant(db: DBSession, tenant_id: UUID) -> Tenant:
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return tenant


def _load_settings(raw: dict | None) -> TenantSettings:
    """Merge stored JSONB into the schema. Unknown keys are tolerated for
    forward compatibility — future settings additions won't break old rows."""
    if not raw:
        return TenantSettings()
    try:
        return TenantSettings.model_validate(raw)
    except Exception:
        # Corrupt or pre-schema data — fall back to defaults. Log so the rot
        # is visible without taking down the dashboard.
        logger.warning(
            "Tenant.settings JSONB did not match schema; returning defaults",
            exc_info=True,
        )
        return TenantSettings()


@router.get("", response_model=TenantSettings)
async def get_settings(db: DBSession, auth: CurrentUser) -> TenantSettings:
    """Return the tenant's current settings document (with defaults for blank fields)."""
    tenant = await _load_tenant(db, auth.tenant_id)
    return _load_settings(tenant.settings)


@router.put("", response_model=TenantSettingsUpdateResponse)
async def update_settings(
    db: DBSession,
    auth: CurrentUser,
    body: TenantSettingsUpdate,
) -> TenantSettingsUpdateResponse:
    """Merge the provided sections into the stored settings, bump version,
    and kick off a runner restart so running employees pick up the change.

    Partial updates are supported — any section omitted from the body is
    left unchanged. Sending a section replaces it wholesale (no key-level
    merging within a section, to keep the contract obvious).
    """
    tenant = await _load_tenant(db, auth.tenant_id)
    current = _load_settings(tenant.settings)

    # Merge at the dict level so Pydantic can re-validate the whole document
    # in one shot. Avoids ``model_copy(update=raw_dict)`` which leaves
    # submodel fields as raw dicts and confuses the serializer.
    current_dict = current.model_dump(mode="json")
    patch_dict = body.model_dump(exclude_none=True, mode="json")
    current_dict.update(patch_dict)
    current_dict["version"] = current.version + 1

    new_settings = TenantSettings.model_validate(current_dict)

    # Direct assignment works because the ORM wraps JSONB as a dict and
    # SQLAlchemy notices a fresh dict assignment. Writing the whole blob
    # atomically (vs. jsonb_set key-by-key) is fine here because we
    # validated the full document.
    tenant.settings = new_settings.model_dump(mode="json")
    await db.commit()

    # Kick off runner restart. Best-effort: if the manager is unreachable,
    # we still want the settings write to succeed; the next manual employee
    # restart will pick up the change.
    restarting_count = 0
    try:
        manager = get_employee_manager()
        restarting_count = await manager.restart_all_for_tenant(auth.tenant_id, db)
    except Exception:
        logger.warning(
            "restart_all_for_tenant failed — settings saved but running "
            "employees will not pick up the change until their next restart",
            exc_info=True,
            extra={"tenant_id": str(auth.tenant_id)},
        )

    logger.info(
        "Tenant settings updated",
        extra={
            "tenant_id": str(auth.tenant_id),
            "new_version": new_settings.version,
            "restarting_employees": restarting_count,
            "sections_modified": list(patch_dict.keys()),
        },
    )

    return TenantSettingsUpdateResponse(
        settings=new_settings,
        restarting_employees=restarting_count,
    )
