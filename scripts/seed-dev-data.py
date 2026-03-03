#!/usr/bin/env python3
"""
Seed development data for empla.

Creates a dev tenant and admin user so you can log in to the dashboard.

Usage:
    uv run python scripts/seed-dev-data.py

Login credentials (dashboard):
    Email: admin@empla.dev
    Organization: empla-dev
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from empla.models.database import get_db
from empla.models.employee import Employee
from empla.models.tenant import Tenant, User


async def seed() -> None:
    """Create dev tenant and admin user if they don't exist."""
    async with get_db() as db:
        # Check if dev tenant already exists
        result = await db.execute(select(Tenant).where(Tenant.slug == "empla-dev"))
        tenant = result.scalar_one_or_none()

        if tenant is None:
            tenant = Tenant(
                name="empla Development",
                slug="empla-dev",
                status="active",
                settings={},
            )
            db.add(tenant)
            await db.flush()
            print(f"Created tenant: {tenant.name} (slug: {tenant.slug})")
        else:
            print(f"Tenant already exists: {tenant.name} (slug: {tenant.slug})")

        # Check if admin user already exists
        result = await db.execute(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == "admin@empla.dev",
            )
        )
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                tenant_id=tenant.id,
                email="admin@empla.dev",
                name="Navin (Admin)",
                role="admin",
                settings={},
            )
            db.add(user)
            print(f"Created user: {user.name} ({user.email})")
        else:
            print(f"User already exists: {user.name} ({user.email})")

        # Check if SalesAE employee already exists
        result = await db.execute(
            select(Employee).where(
                Employee.tenant_id == tenant.id,
                Employee.role == "sales_ae",
                Employee.email == "jordan.chen@empla.dev",
            )
        )
        employee = result.scalar_one_or_none()

        if employee is None:
            employee = Employee(
                tenant_id=tenant.id,
                name="Jordan Chen",
                role="sales_ae",
                email="jordan.chen@empla.dev",
                status="active",
                lifecycle_stage="autonomous",
                config={},
                capabilities=["email", "calendar", "crm"],
                performance_metrics={},
                created_by=user.id,
            )
            db.add(employee)
            await db.flush()
            print(f"Created employee: {employee.name} (role: {employee.role}, id: {employee.id})")
        else:
            print(f"Employee already exists: {employee.name} (id: {employee.id})")

        await db.commit()

    print()
    print("Login credentials:")
    print("  Email:        admin@empla.dev")
    print("  Organization: empla-dev")


if __name__ == "__main__":
    asyncio.run(seed())
