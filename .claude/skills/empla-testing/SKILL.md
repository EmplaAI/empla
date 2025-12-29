---
name: empla-testing
description: Testing patterns for empla including the simulation framework, pytest fixtures, and how to test autonomous employee behavior. Use when writing tests, fixing test failures, or setting up test infrastructure.
---

# empla Testing Guide

## Test Structure

```
tests/
├── unit/                    # Fast, isolated tests
│   ├── test_employees_*.py  # Employee class tests
│   ├── llm/                 # LLM service tests
│   └── ...
├── integration/             # Component interaction tests
│   ├── test_capabilities_loop_integration.py
│   └── test_employee_lifecycle.py
├── e2e/                     # End-to-end tests
│   ├── test_employee_lifecycle_e2e.py
│   └── test_sales_ae_autonomous.py
└── simulation/              # Simulation framework
    ├── capabilities.py      # Simulated capabilities
    ├── environment.py       # SimulatedEnvironment
    └── test_autonomous_behaviors.py
```

## Running Tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=empla --cov-report=html

# Specific file
uv run pytest tests/unit/test_employees_base.py

# Specific test
uv run pytest tests/unit/test_employees_base.py::test_employee_creation

# E2E tests only (require database)
uv run pytest tests/e2e/

# Skip slow tests
uv run pytest -m "not slow"

# Verbose output
uv run pytest -v

# Stop on first failure
uv run pytest -x
```

## Simulation Framework

The simulation framework lets you test autonomous behavior without real APIs.

### SimulatedEnvironment

```python
from tests.simulation import (
    SimulatedEnvironment,
    SimulatedEmail,
    SimulatedDeal,
    DealStage,
)

# Create environment with simulated data
env = SimulatedEnvironment()

# Add simulated emails
env.add_email(SimulatedEmail(
    from_addr="john@acme.com",
    subject="Re: Proposal",
    body="We're interested in moving forward",
    is_high_priority=True
))

# Add simulated CRM data
env.add_deal(SimulatedDeal(
    name="Acme Corp",
    stage=DealStage.NEGOTIATION,
    value=50000,
    probability=0.7
))

# Set pipeline metrics
env.set_pipeline_coverage(2.5)  # Below 3.0 target
```

### Testing with Simulated Capabilities

```python
from empla.employees import SalesAE
from empla.employees.config import EmployeeConfig
from tests.simulation import SimulatedEnvironment

async def test_sales_ae_low_pipeline_response():
    """Test that SalesAE forms intentions when pipeline is low."""

    # Setup simulated environment
    env = SimulatedEnvironment()
    env.set_pipeline_coverage(1.5)  # Below 3.0 target

    # Create employee with simulated capabilities
    config = EmployeeConfig(
        name="Test AE",
        role="sales_ae",
        email="test@company.com"
    )
    employee = SalesAE(config, capability_registry=env.registry)

    # Start without running continuous loop
    await employee.start(run_loop=False)

    try:
        # Run single cycle
        await employee.run_once()

        # Verify employee recognized low pipeline
        pipeline_belief = await employee.beliefs.get("pipeline", "coverage")
        assert pipeline_belief is not None

        # Verify employee formed appropriate intentions
        # (specific assertions depend on implementation)

    finally:
        await employee.stop()
```

### Simulated Capabilities

```python
from tests.simulation.capabilities import (
    SimulatedEmailCapability,
    SimulatedCRMCapability,
    SimulatedCalendarCapability,
)

# Capabilities return simulated data
email_cap = SimulatedEmailCapability()
emails = await email_cap.perceive(employee_id)
# Returns: [SimulatedEmail(...), ...]

# You can configure responses
email_cap.set_response("send_email", {"success": True, "message_id": "123"})
result = await email_cap.execute_action("send_email", {...})
```

## Database Test Fixtures

### Using Real Database (E2E Tests)

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from empla.models.database import get_engine, get_sessionmaker

@pytest.fixture
async def db_session():
    """Provides a database session for testing."""
    engine = get_engine("postgresql+asyncpg://localhost/empla_test")
    sessionmaker = get_sessionmaker(engine)

    async with sessionmaker() as session:
        yield session
        await session.rollback()  # Clean up after test

    await engine.dispose()
```

### Creating Test Tenants/Employees

```python
from uuid import uuid4
from empla.models.tenant import Tenant
from empla.models.employee import Employee

@pytest.fixture
async def tenant(db_session):
    """Create a test tenant."""
    tenant = Tenant(
        id=uuid4(),
        name="Test Company",
        domain="test-company.com"
    )
    db_session.add(tenant)
    await db_session.flush()
    return tenant

@pytest.fixture
async def employee(db_session, tenant):
    """Create a test employee."""
    employee = Employee(
        tenant_id=tenant.id,
        name="Test Employee",
        role="sales_ae",
        email="test@test-company.com"
    )
    db_session.add(employee)
    await db_session.flush()
    return employee
```

## Testing LLM Interactions

### Mocking LLM Responses

```python
from unittest.mock import AsyncMock, patch

async def test_belief_extraction():
    mock_llm = AsyncMock()
    mock_llm.generate_structured.return_value = {
        "subject": "Acme Corp",
        "predicate": "interest_level",
        "object": "high",
        "confidence": 0.9
    }

    with patch("empla.bdi.beliefs.LLMService", return_value=mock_llm):
        # Test belief extraction logic
        pass
```

### Testing with Real LLM (E2E)

```python
import os
import pytest

requires_llm = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY"
)

@requires_llm
async def test_llm_belief_extraction():
    """Test that LLM correctly extracts beliefs from text."""
    # This test uses real LLM API
    pass
```

## Common Test Patterns

### Testing Async Code

```python
import pytest

# pytest-asyncio handles async tests automatically
async def test_async_operation():
    result = await some_async_function()
    assert result == expected
```

### Testing Exceptions

```python
import pytest
from empla.employees.exceptions import EmployeeNotStartedError

async def test_run_once_before_start():
    employee = SalesAE(config)

    with pytest.raises(EmployeeNotStartedError):
        await employee.run_once()
```

### Parameterized Tests

```python
import pytest

@pytest.mark.parametrize("pipeline_coverage,should_act", [
    (1.0, True),   # Low pipeline - should act
    (2.5, True),   # Below target - should act
    (3.5, False),  # Above target - no action needed
])
async def test_pipeline_response(pipeline_coverage, should_act):
    env = SimulatedEnvironment()
    env.set_pipeline_coverage(pipeline_coverage)
    # ... test logic
```

## Debugging Test Failures

### Common Issues

1. **Database connection errors**
   ```bash
   # Ensure PostgreSQL is running
   pg_isready

   # Create test database if needed
   createdb empla_test
   ```

2. **Missing LLM API key**
   ```bash
   # Set for E2E tests
   export OPENAI_API_KEY=sk-...
   ```

3. **Async cleanup issues**
   ```python
   # Always use try/finally for cleanup
   try:
       await employee.start(run_loop=False)
       # test logic
   finally:
       await employee.stop()
   ```

4. **Database constraint violations**
   - Check that tenant exists before creating employee
   - Check enum values match database constraints

### Viewing Test Output

```bash
# Show print statements
uv run pytest -s

# Show local variables on failure
uv run pytest -l

# Drop into debugger on failure
uv run pytest --pdb
```

## Coverage Goals

- **Unit tests**: >80% coverage
- **Integration tests**: Cover all component interactions
- **E2E tests**: Cover critical user journeys

```bash
# Check coverage
uv run pytest --cov=empla --cov-report=term-missing

# HTML report
uv run pytest --cov=empla --cov-report=html
open htmlcov/index.html
```
