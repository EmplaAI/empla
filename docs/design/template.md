# [Feature Name]

**Status:** Draft | In Progress | Implemented | Deprecated

**Author:** [Name]

**Date:** YYYY-MM-DD

**Related:**
- ADRs: [Links to relevant ADRs]
- Issues: [Links to GitHub issues]
- PRs: [Links to pull requests]

---

## Overview

High-level summary of what this feature does and why it exists.

**In one sentence:** [Concise description]

**Target Users:** [Who will use this?]

**Success Criteria:** [How do we know this works?]

---

## Problem

### Current State
What's the situation today? What problem are we solving?

- Pain point 1
- Pain point 2
- Current workaround (if any)

### User Stories
Who needs this and why?

**As a** [role]
**I want** [capability]
**So that** [benefit]

**As a** [role]
**I want** [capability]
**So that** [benefit]

### Requirements
What must this feature do?

**Functional Requirements:**
- FR-1: Requirement description
- FR-2: Requirement description
- FR-3: Requirement description

**Non-Functional Requirements:**
- NFR-1: Performance/Scale requirement
- NFR-2: Security requirement
- NFR-3: Reliability requirement

---

## Solution

### High-Level Approach
How are we solving this problem?

[2-3 paragraph explanation of the approach]

### Architecture Diagram
```
[ASCII diagram or link to visual diagram]
```

### Component Overview
What are the major pieces?

**Component 1: [Name]**
- Purpose: What does it do?
- Responsibilities: What is it responsible for?
- Dependencies: What does it need?

**Component 2: [Name]**
- Purpose: ...
- Responsibilities: ...
- Dependencies: ...

---

## API Design

### Public API

```python
# Example: Employee creation API

async def create_employee(
    name: str,
    role: EmployeeRole,
    config: Optional[EmployeeConfig] = None
) -> Employee:
    """
    Create and initialize a new digital employee.

    Args:
        name: Employee display name
        role: Employee role (sales_ae, csm, pm, etc.)
        config: Optional configuration (uses defaults if not provided)

    Returns:
        Fully initialized Employee ready for onboarding

    Raises:
        ValidationError: If name/role validation fails
        ProvisioningError: If email provisioning fails

    Example:
        >>> employee = await create_employee(
        ...     name="Jordan Chen",
        ...     role=EmployeeRole.SALES_AE
        ... )
        >>> print(employee.email)
        jordan.chen@company.com
    """
```

### Internal APIs
```python
# Example: Internal belief storage API

class BeliefStorage(Protocol):
    """Interface for belief persistence"""

    async def store_belief(self, employee_id: UUID, belief: Belief) -> None:
        """Store a belief for an employee"""

    async def get_beliefs(
        self,
        employee_id: UUID,
        filters: Optional[BeliefFilter] = None
    ) -> List[Belief]:
        """Retrieve beliefs for an employee"""
```

---

## Data Models

### Database Schema

```sql
-- Example: Employee profile table

CREATE TABLE employee_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    role VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_email CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'),
    CONSTRAINT valid_status CHECK (status IN ('onboarding', 'active', 'inactive', 'offboarded'))
);

CREATE INDEX idx_employee_status ON employee_profiles(status);
CREATE INDEX idx_employee_created_at ON employee_profiles(created_at DESC);
```

### Pydantic Models

```python
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from uuid import UUID
from enum import Enum

class EmployeeStatus(str, Enum):
    """Employee lifecycle status"""
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    INACTIVE = "inactive"
    OFFBOARDED = "offboarded"

class EmployeeRole(str, Enum):
    """Pre-defined employee roles"""
    SALES_AE = "sales_ae"
    CSM = "csm"
    PM = "pm"
    RECRUITER = "recruiter"
    EA = "ea"

class EmployeeProfile(BaseModel):
    """Employee profile data model"""

    id: UUID
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    role: EmployeeRole
    status: EmployeeStatus = EmployeeStatus.ONBOARDING
    created_at: datetime
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Jordan Chen",
                "email": "jordan.chen@company.com",
                "role": "sales_ae",
                "status": "onboarding",
                "created_at": "2025-10-26T10:00:00Z",
                "updated_at": "2025-10-26T10:00:00Z"
            }
        }
```

---

## Implementation Plan

### Phase 1: Core Foundation (Week 1)
- [ ] Task 1: Database schema and migrations
- [ ] Task 2: Pydantic models
- [ ] Task 3: Core business logic
- [ ] Task 4: Unit tests (>80% coverage)

**Deliverable:** Core functionality working, fully tested

### Phase 2: Integration (Week 2)
- [ ] Task 1: API endpoints
- [ ] Task 2: Integration with existing systems
- [ ] Task 3: Integration tests
- [ ] Task 4: E2E tests

**Deliverable:** Feature integrated and validated end-to-end

### Phase 3: Polish (Week 3)
- [ ] Task 1: Error handling and edge cases
- [ ] Task 2: Performance optimization
- [ ] Task 3: Documentation
- [ ] Task 4: Examples and guides

**Deliverable:** Production-ready feature

---

## Testing Strategy

### Unit Tests
**Coverage Target:** >80%

**Key Test Cases:**
- Happy path: Normal operation
- Edge cases: Boundary conditions
- Error cases: Invalid inputs, failures
- Concurrency: Race conditions (if applicable)

**Example:**
```python
async def test_create_employee_success():
    """Test successful employee creation"""
    employee = await create_employee(
        name="Jordan Chen",
        role=EmployeeRole.SALES_AE
    )

    assert employee.name == "Jordan Chen"
    assert employee.email == "jordan.chen@company.com"
    assert employee.status == EmployeeStatus.ONBOARDING
```

### Integration Tests
**What to test:**
- Component interactions
- Database operations
- External API calls (mocked)

### E2E Tests
**Scenarios:**
- Complete user workflows
- Multi-step operations
- Real-world use cases

---

## Migration Path

### Breaking Changes
List any breaking changes and how to handle them.

**Change 1:**
- **Old Behavior:** ...
- **New Behavior:** ...
- **Migration:** ...

### Deployment Steps
1. Step 1: Run database migrations
2. Step 2: Deploy new code
3. Step 3: Verify functionality
4. Step 4: Monitor for issues

### Rollback Plan
If something goes wrong:
1. Rollback step 1
2. Rollback step 2
3. Verification steps

---

## Performance Considerations

### Expected Load
- Requests per second: ...
- Data volume: ...
- Concurrent users: ...

### Optimization Strategies
- Caching approach
- Database indexing
- Query optimization
- Async operations

### Monitoring
**Key Metrics:**
- Latency (p50, p95, p99)
- Error rate
- Resource usage (CPU, memory, DB connections)

---

## Security Considerations

### Authentication & Authorization
- Who can access this feature?
- What permissions are required?
- How is access controlled?

### Data Protection
- What sensitive data is involved?
- How is it encrypted/protected?
- Compliance requirements (GDPR, etc.)

### Potential Threats
- Threat 1: Description and mitigation
- Threat 2: Description and mitigation

---

## Open Questions

- [ ] Question 1: What needs to be decided?
- [ ] Question 2: What needs to be clarified?
- [ ] Question 3: What are the unknowns?

**Decisions Needed By:** YYYY-MM-DD

---

## Future Enhancements

Features we're NOT building now but might later:

- Enhancement 1: Description
- Enhancement 2: Description
- Enhancement 3: Description

---

## References

- [Related documentation](link)
- [Research paper](link)
- [Similar implementation](link)
- [Inspiration source](link)

---

**Created:** YYYY-MM-DD
**Last Updated:** YYYY-MM-DD
**Implementation Status:** [Not Started | In Progress | Complete]
**Version:** 1.0
