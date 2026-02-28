"""
empla.models - SQLAlchemy Database Models

This package contains all SQLAlchemy ORM models for empla's database schema.

Models are organized by domain:
- base: Base model classes with common functionality
- tenant: Multi-tenancy (Tenant, User)
- employee: Digital employees (Employee, EmployeeGoal, EmployeeIntention)
- belief: BDI beliefs (Belief, BeliefHistory)
- memory: Memory systems (EpisodicMemory, SemanticMemory, ProceduralMemory, WorkingMemory)
- audit: Observability (AuditLog, Metric)

Usage:
    >>> from empla.models import Employee, EmployeeGoal
    >>> from empla.models.database import get_db
    >>>
    >>> async with get_db() as db:
    ...     employees = await db.query(Employee).all()
"""

from empla.models.activity import ActivityEventType, EmployeeActivity
from empla.models.audit import AuditLog, Metric
from empla.models.base import Base
from empla.models.belief import Belief, BeliefHistory
from empla.models.employee import Employee, EmployeeGoal, EmployeeIntention
from empla.models.integration import (
    CredentialStatus,
    CredentialType,
    Integration,
    IntegrationAuthType,
    IntegrationCredential,
    IntegrationOAuthState,
    IntegrationProvider,
    IntegrationStatus,
)
from empla.models.memory import (
    EpisodicMemory,
    ProceduralMemory,
    SemanticMemory,
    WorkingMemory,
)
from empla.models.tenant import Tenant, User

__all__ = [
    "ActivityEventType",
    "AuditLog",
    "Base",
    "Belief",
    "BeliefHistory",
    "CredentialStatus",
    "CredentialType",
    "Employee",
    "EmployeeActivity",
    "EmployeeGoal",
    "EmployeeIntention",
    "EpisodicMemory",
    "Integration",
    "IntegrationAuthType",
    "IntegrationCredential",
    "IntegrationOAuthState",
    "IntegrationProvider",
    "IntegrationStatus",
    "Metric",
    "ProceduralMemory",
    "SemanticMemory",
    "Tenant",
    "User",
    "WorkingMemory",
]
