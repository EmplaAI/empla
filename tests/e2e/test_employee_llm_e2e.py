"""
LLM-Based E2E Employee Tests.

Tests that use REAL LLM calls to validate employee reasoning/generation
across multiple providers (Claude, OpenAI, Azure OpenAI, Gemini).

These tests:
- Use REAL LLM API calls (requires API keys)
- Use SIMULATED external services (email, CRM, calendar)
- Skip gracefully when API keys are not set
- Are parametrized to test all available providers
"""

import logging
import os
from uuid import uuid4

import pytest
from sqlalchemy import event

from empla.employees import CustomerSuccessManager, SalesAE
from empla.employees.config import EmployeeConfig, LLMSettings, LoopSettings
from empla.llm import LLMService
from empla.llm.config import LLMConfig
from empla.models.database import get_engine, get_sessionmaker
from empla.models.tenant import Tenant, User
from tests.simulation import (
    SimulatedEnvironment,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Skip conditions based on available API keys
# ============================================================================


def has_anthropic_key() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def has_openai_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def has_azure_openai_key() -> bool:
    return bool(
        os.getenv("AZURE_OPENAI_API_KEY")
        and os.getenv("AZURE_OPENAI_ENDPOINT")
        and os.getenv("AZURE_OPENAI_DEPLOYMENT")
    )


def has_vertex_config() -> bool:
    return bool(os.getenv("VERTEX_PROJECT_ID"))


def has_any_llm_key() -> bool:
    return any([
        has_anthropic_key(),
        has_openai_key(),
        has_azure_openai_key(),
        has_vertex_config(),
    ])


# Skip entire module if no LLM keys available
pytestmark = pytest.mark.skipif(
    not has_any_llm_key(),
    reason="No LLM API keys configured (set ANTHROPIC_API_KEY, OPENAI_API_KEY, "
    "AZURE_OPENAI_API_KEY+AZURE_OPENAI_ENDPOINT+AZURE_OPENAI_DEPLOYMENT, "
    "or VERTEX_PROJECT_ID)",
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def session():
    """Create a test database session with transaction isolation."""
    engine = get_engine(echo=False)
    conn = await engine.connect()
    trans = await conn.begin()
    sessionmaker = get_sessionmaker(engine)
    session = sessionmaker(bind=conn)
    nested = await conn.begin_nested()

    @event.listens_for(session.sync_session, "after_transaction_end")
    def restart_savepoint(_session, transaction):
        if transaction.nested and not transaction._parent.nested:
            conn.sync_connection.begin_nested()

    yield session

    await session.close()
    if nested.is_active:
        await nested.rollback()
    if trans.is_active:
        await trans.rollback()
    await conn.close()
    await engine.dispose()


@pytest.fixture
async def tenant_and_user(session):
    """Create test tenant and user in the database."""
    tenant = Tenant(
        id=uuid4(),
        name="LLM Test Company",
        slug="llm-test-company",
        status="active",
    )
    session.add(tenant)

    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email="admin@llm-test-company.com",
        name="Admin User",
        role="admin",
    )
    session.add(user)
    await session.commit()

    return tenant, user


@pytest.fixture
def simulated_environment():
    """Create a fresh simulated environment."""
    return SimulatedEnvironment()


@pytest.fixture(
    params=[
        pytest.param("claude", marks=pytest.mark.skipif(
            not has_anthropic_key(), reason="ANTHROPIC_API_KEY not set"
        )),
        pytest.param("openai", marks=pytest.mark.skipif(
            not has_openai_key(), reason="OPENAI_API_KEY not set"
        )),
        pytest.param("azure", marks=pytest.mark.skipif(
            not has_azure_openai_key(), reason="Azure OpenAI credentials not set"
        )),
        pytest.param("gemini", marks=pytest.mark.skipif(
            not has_vertex_config(), reason="VERTEX_PROJECT_ID not set"
        )),
    ]
)
def llm_provider(request):
    """Parametrized fixture to test all available LLM providers."""
    return request.param


@pytest.fixture
def llm_config(llm_provider) -> LLMConfig:
    """Create LLM config for the current provider."""
    model_map = {
        "claude": "claude-sonnet-4",
        "openai": "gpt-4o-mini",
        "azure": "gpt-4o",  # Azure deployment name set separately
        "gemini": "gemini-2.0-flash",
    }

    return LLMConfig(
        primary_model=model_map[llm_provider],
        fallback_model=None,  # Test each provider in isolation
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        azure_openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        vertex_project_id=os.getenv("VERTEX_PROJECT_ID"),
    )


@pytest.fixture
def llm_settings(llm_provider) -> LLMSettings:
    """Create LLM settings for employee config."""
    model_map = {
        "claude": "claude-sonnet-4",
        "openai": "gpt-4o-mini",
        "azure": "gpt-4o",
        "gemini": "gemini-2.0-flash",
    }
    return LLMSettings(
        primary_model=model_map[llm_provider],
        fallback_model=None,
    )


# ============================================================================
# Part 1: Basic LLM Integration Tests
# ============================================================================


class TestLLMServiceIntegration:
    """Tests for basic LLM service functionality across providers."""

    @pytest.mark.asyncio
    async def test_llm_service_generates_text(self, llm_config, llm_provider):
        """Verify LLM service can generate text with each provider."""
        llm = LLMService(llm_config)

        response = await llm.generate(
            prompt="Say 'Hello, test successful!' and nothing else.",
            max_tokens=50,
            temperature=0.1,
        )

        assert response.content is not None
        assert len(response.content) > 0
        assert response.usage.total_tokens > 0

        logger.info(
            f"LLM {llm_provider} response: {response.content[:100]}..."
        )

    @pytest.mark.asyncio
    async def test_llm_service_generates_structured_output(
        self, llm_config, llm_provider
    ):
        """Verify LLM service can generate structured output."""
        from pydantic import BaseModel

        class TestOutput(BaseModel):
            greeting: str
            number: int

        llm = LLMService(llm_config)

        _response, parsed = await llm.generate_structured(
            prompt="Generate a greeting and a random number between 1-100.",
            response_format=TestOutput,
            max_tokens=100,
            temperature=0.5,
        )

        assert parsed is not None
        assert isinstance(parsed.greeting, str)
        assert isinstance(parsed.number, int)
        assert 1 <= parsed.number <= 100

        logger.info(
            f"LLM {llm_provider} structured output: {parsed}"
        )

    @pytest.mark.asyncio
    async def test_llm_service_handles_error_gracefully(
        self, llm_config, llm_provider
    ):
        """Verify LLM service handles errors without crashing."""
        llm = LLMService(llm_config)

        # Request with very low max_tokens should still work or fail gracefully
        try:
            response = await llm.generate(
                prompt="Write a long essay about AI.",
                max_tokens=10,  # Very limited
                temperature=0.1,
            )
            # If it succeeds, content should be truncated
            assert response.content is not None
        except Exception as e:
            # Some providers may reject very low token limits
            logger.info(f"Provider {llm_provider} rejected low token limit: {e}")


# ============================================================================
# Part 2: SalesAE LLM Reasoning Tests
# ============================================================================


class TestSalesAEWithLLM:
    """Tests for SalesAE using real LLM for reasoning."""

    @pytest.mark.asyncio
    async def test_sales_ae_llm_initialization(
        self, tenant_and_user, llm_settings, llm_provider
    ):
        """Verify SalesAE can initialize with LLM settings."""
        tenant, _ = tenant_and_user

        config = EmployeeConfig(
            name=f"LLM Test Sales AE ({llm_provider})",
            role="sales_ae",
            email="sales-llm-test@test-company.com",
            tenant_id=tenant.id,
            llm=llm_settings,
            loop=LoopSettings(cycle_interval_seconds=60),
        )

        employee = SalesAE(config)

        try:
            await employee.start()

            # Verify employee started with LLM configured
            assert employee._is_running
            assert employee._llm is not None

            # Run a cycle to ensure LLM is being used
            await employee.run_once()

            logger.info(
                f"SalesAE with {llm_provider} completed cycle successfully"
            )

        finally:
            if employee._is_running:
                await employee.stop()


# ============================================================================
# Part 3: CSM LLM Reasoning Tests
# ============================================================================


class TestCSMWithLLM:
    """Tests for CSM using real LLM for reasoning."""

    @pytest.mark.asyncio
    async def test_csm_llm_initialization(
        self, tenant_and_user, llm_settings, llm_provider
    ):
        """Verify CSM can initialize with LLM settings."""
        tenant, _ = tenant_and_user

        config = EmployeeConfig(
            name=f"LLM Test CSM ({llm_provider})",
            role="csm",
            email="csm-llm-test@test-company.com",
            tenant_id=tenant.id,
            llm=llm_settings,
            loop=LoopSettings(cycle_interval_seconds=60),
        )

        employee = CustomerSuccessManager(config)

        try:
            await employee.start()

            assert employee._is_running
            assert employee._llm is not None

            await employee.run_once()

            logger.info(
                f"CSM with {llm_provider} completed cycle successfully"
            )

        finally:
            if employee._is_running:
                await employee.stop()


# ============================================================================
# Part 4: Cross-Provider Comparison Tests
# ============================================================================


class TestCrossProviderConsistency:
    """Tests to verify consistent behavior across LLM providers."""

    @pytest.mark.asyncio
    async def test_belief_extraction_consistency(
        self, llm_config, llm_provider
    ):
        """Verify belief extraction works consistently across providers."""
        from pydantic import BaseModel, Field

        class ExtractedBelief(BaseModel):
            subject: str = Field(description="What the belief is about")
            confidence: float = Field(
                description="Confidence level 0.0-1.0",
                ge=0.0,
                le=1.0,
            )
            description: str = Field(description="Brief description")

        llm = LLMService(llm_config)

        prompt = """
        Based on this observation: "Customer responded within 5 minutes to our demo request email"
        Extract a belief about the customer's interest level.
        """

        _response, belief = await llm.generate_structured(
            prompt=prompt,
            response_format=ExtractedBelief,
            system="You are an AI that extracts beliefs from observations.",
            max_tokens=200,
        )

        assert belief is not None
        assert 0.0 <= belief.confidence <= 1.0
        assert len(belief.subject) > 0
        assert len(belief.description) > 0

        logger.info(
            f"Provider {llm_provider} extracted belief: "
            f"subject={belief.subject}, confidence={belief.confidence}"
        )

    @pytest.mark.asyncio
    async def test_email_generation_consistency(
        self, llm_config, llm_provider
    ):
        """Verify email generation works across providers."""
        from pydantic import BaseModel

        class GeneratedEmail(BaseModel):
            subject: str
            body: str

        llm = LLMService(llm_config)

        prompt = """
        Generate a professional follow-up email for a sales prospect who:
        - Attended a product demo last week
        - Showed interest in the enterprise plan
        - Asked about integration capabilities

        Keep it brief and professional.
        """

        _response, email = await llm.generate_structured(
            prompt=prompt,
            response_format=GeneratedEmail,
            system="You are a professional sales AI assistant.",
            max_tokens=300,
        )

        assert email is not None
        assert len(email.subject) > 0
        assert len(email.body) > 0
        assert "@" not in email.subject  # Subject shouldn't contain email addresses

        logger.info(
            f"Provider {llm_provider} generated email: subject={email.subject}"
        )
