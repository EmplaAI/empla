"""
empla.employees.base - Base Digital Employee

The foundational class for all digital employees.
Ties together BDI, Memory, Capabilities, and the Proactive Loop.

Example:
    >>> from empla.employees import SalesAE
    >>> from empla.employees.config import EmployeeConfig
    >>>
    >>> config = EmployeeConfig(
    ...     name="Jordan Chen",
    ...     role="sales_ae",
    ...     email="jordan@company.com"
    ... )
    >>> employee = SalesAE(config)
    >>> await employee.start()
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from empla.bdi import BeliefSystem, GoalSystem, IntentionStack
from empla.capabilities import CapabilityRegistry, CapabilityType
from empla.core.loop import LoopConfig, ProactiveExecutionLoop
from empla.core.memory import (
    EpisodicMemorySystem,
    ProceduralMemorySystem,
    SemanticMemorySystem,
    WorkingMemory,
)
from empla.employees.config import EmployeeConfig, GoalConfig
from empla.employees.exceptions import (
    EmployeeConfigError,
    EmployeeNotStartedError,
    EmployeeStartupError,
)
from empla.employees.personality import Personality
from empla.llm import LLMConfig, LLMService
from empla.models.database import get_engine, get_sessionmaker
from empla.models.employee import Employee as EmployeeModel

logger = logging.getLogger(__name__)


class MemorySystem:
    """
    Container for all memory subsystems.

    Aggregates the four types of memory:
    - Episodic: Specific experiences and events
    - Semantic: Facts and knowledge
    - Procedural: Skills and how-to knowledge
    - Working: Short-term active context

    This is a convenience wrapper that ensures all memory systems
    share the same database session and employee context.

    Args:
        session: Database session for all memory operations
        employee_id: ID of the employee who owns these memories
        tenant_id: Tenant ID for multi-tenancy isolation
    """

    def __init__(
        self,
        session: AsyncSession,
        employee_id: UUID,
        tenant_id: UUID,
    ) -> None:
        self.episodic = EpisodicMemorySystem(session, employee_id, tenant_id)
        self.semantic = SemanticMemorySystem(session, employee_id, tenant_id)
        self.procedural = ProceduralMemorySystem(session, employee_id, tenant_id)
        self.working = WorkingMemory(session, employee_id, tenant_id)


class DigitalEmployee(ABC):
    """
    Base class for all digital employees.

    This class ties together all empla components:
    - BDI Engine (beliefs, goals, intentions)
    - Memory Systems (episodic, semantic, procedural, working)
    - Capabilities (email, calendar, CRM, etc.)
    - Proactive Loop (continuous autonomous operation)

    Subclasses should implement:
    - default_personality: Personality template for the role
    - default_goals: Default goals for the role
    - default_capabilities: Enabled capabilities
    - on_start(): Custom initialization logic
    - on_stop(): Custom cleanup logic

    Example:
        >>> class CustomEmployee(DigitalEmployee):
        ...     @property
        ...     def default_personality(self) -> Personality:
        ...         return Personality(extraversion=0.8)
        ...
        ...     @property
        ...     def default_goals(self) -> list[GoalConfig]:
        ...         return [GoalConfig(description="My goal", priority=8)]
        ...
        ...     @property
        ...     def default_capabilities(self) -> list[str]:
        ...         return ["email", "calendar"]
    """

    def __init__(
        self,
        config: EmployeeConfig,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        """
        Initialize digital employee.

        Args:
            config: Employee configuration
            capability_registry: Optional pre-configured capability registry.
                If provided, this registry is used instead of creating a new one.
                Useful for testing with simulated capabilities.
        """
        self.config = config
        self._employee_id: UUID | None = None
        self._tenant_id: UUID = config.tenant_id or uuid4()

        # Injected dependencies (for testing)
        self._injected_capabilities = capability_registry

        # Database (initialized in start(), cleaned up in stop())
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None
        self._session: AsyncSession | None = None

        # Components (initialized in start())
        self._llm: LLMService | None = None
        self._beliefs: BeliefSystem | None = None
        self._goals: GoalSystem | None = None
        self._intentions: IntentionStack | None = None
        self._memory: MemorySystem | None = None
        self._capabilities: CapabilityRegistry | None = None
        self._loop: ProactiveExecutionLoop | None = None
        self._db_employee: EmployeeModel | None = None

        # State
        self._is_running = False
        self._started_at: datetime | None = None
        self._loop_task: asyncio.Task[None] | None = None

    # =========================================================================
    # Abstract Properties - Subclasses must implement
    # =========================================================================

    @property
    @abstractmethod
    def default_personality(self) -> Personality:
        """Default personality for this role."""
        ...

    @property
    @abstractmethod
    def default_goals(self) -> list[GoalConfig]:
        """Default goals for this role."""
        ...

    @property
    @abstractmethod
    def default_capabilities(self) -> list[str]:
        """Default capabilities for this role."""
        ...

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def employee_id(self) -> UUID:
        """Employee ID (set after start)."""
        if self._employee_id is None:
            raise EmployeeNotStartedError(
                f"Cannot access employee_id on {self.name}: call start() first"
            )
        return self._employee_id

    @property
    def tenant_id(self) -> UUID:
        """Tenant ID."""
        return self._tenant_id

    @property
    def name(self) -> str:
        """Employee name."""
        return self.config.name

    @property
    def role(self) -> str:
        """Employee role."""
        return self.config.role

    @property
    def email(self) -> str:
        """Employee email."""
        return self.config.email

    @property
    def personality(self) -> Personality:
        """Effective personality (config override or default)."""
        return self.config.personality or self.default_personality

    @property
    def is_running(self) -> bool:
        """Whether the employee is currently running."""
        return self._is_running

    @property
    def llm(self) -> LLMService:
        """LLM service."""
        if self._llm is None:
            raise EmployeeNotStartedError(f"Cannot access LLM on {self.name}: call start() first")
        return self._llm

    @property
    def beliefs(self) -> BeliefSystem:
        """Belief system."""
        if self._beliefs is None:
            raise EmployeeNotStartedError(
                f"Cannot access beliefs on {self.name}: call start() first"
            )
        return self._beliefs

    @property
    def goals(self) -> GoalSystem:
        """Goal system."""
        if self._goals is None:
            raise EmployeeNotStartedError(f"Cannot access goals on {self.name}: call start() first")
        return self._goals

    @property
    def intentions(self) -> IntentionStack:
        """Intention stack."""
        if self._intentions is None:
            raise EmployeeNotStartedError(
                f"Cannot access intentions on {self.name}: call start() first"
            )
        return self._intentions

    @property
    def memory(self) -> MemorySystem:
        """Memory systems."""
        if self._memory is None:
            raise EmployeeNotStartedError(
                f"Cannot access memory on {self.name}: call start() first"
            )
        return self._memory

    @property
    def capabilities(self) -> CapabilityRegistry:
        """Capability registry."""
        if self._capabilities is None:
            raise EmployeeNotStartedError(
                f"Cannot access capabilities on {self.name}: call start() first"
            )
        return self._capabilities

    # =========================================================================
    # Lifecycle Methods
    # =========================================================================

    async def start(self, run_loop: bool = True) -> None:
        """
        Start the digital employee.

        This initializes all components and starts the proactive loop.

        Args:
            run_loop: Whether to start the proactive loop (default True).
                WARNING: If True, this method blocks until stop() is called.
                For background operation, set run_loop=False and call
                the loop separately.

        Raises:
            EmployeeStartupError: If initialization fails
            EmployeeConfigError: If configuration is invalid

        Example:
            >>> # Blocking mode (typical for production)
            >>> await employee.start()  # Runs forever

            >>> # Non-blocking mode (for testing/control)
            >>> await employee.start(run_loop=False)
            >>> await employee.run_once()  # Manual cycle
            >>> await employee.stop()
        """
        if self._is_running:
            logger.warning(f"Employee {self.name} is already running")
            return

        logger.info(f"Starting employee: {self.name} ({self.role})")

        try:
            # Validate configuration before starting
            await self._validate_config()

            # Initialize database engine and session
            # Session is kept open for the employee's lifetime (closed in stop())
            self._engine = get_engine()
            self._sessionmaker = get_sessionmaker(self._engine)
            self._session = self._sessionmaker()

            # Create or load employee record
            await self._init_employee_record(self._session)

            # Initialize LLM service
            await self._init_llm()

            # Initialize BDI components
            await self._init_bdi(self._session)

            # Initialize memory systems
            await self._init_memory(self._session)

            # Initialize capabilities
            await self._init_capabilities()

            # Create default goals
            await self._create_default_goals()

            # Create proactive loop
            await self._init_loop()

            # Mark as running
            self._is_running = True
            self._started_at = datetime.now(UTC)

            # Custom start logic (wrapped in try/except for cleanup)
            try:
                await self.on_start()
            except Exception as e:
                logger.error(f"on_start() hook failed for {self.name}: {e}", exc_info=True)
                # Clean up since on_start failed
                self._is_running = False
                await self._cleanup_on_error()
                raise EmployeeStartupError(f"on_start() failed: {e}") from e

            # Commit all initialization changes
            await self._session.commit()

            logger.info(f"Employee {self.name} started successfully")

            # Start the loop (blocks if run_loop=True)
            if run_loop:
                await self._run_loop()

        except EmployeeStartupError:
            # Re-raise startup errors directly
            raise
        except EmployeeConfigError:
            # Re-raise config errors directly
            raise
        except Exception as e:
            logger.error(f"Failed to start employee {self.name}: {e}", exc_info=True)
            # Clean up any partial initialization
            await self._cleanup_on_error()
            raise EmployeeStartupError(f"Employee initialization failed: {e}") from e

    async def stop(self) -> None:
        """
        Stop the digital employee.

        Gracefully shuts down the loop and all components.

        Raises:
            EmployeeShutdownError: If shutdown encounters errors (non-fatal, logged)
        """
        if not self._is_running:
            logger.warning(f"Employee {self.name} is not running")
            return

        logger.info(f"Stopping employee: {self.name}")
        shutdown_errors: list[tuple[str, Exception]] = []

        # Stop the loop
        if self._loop:
            try:
                await self._loop.stop()
            except Exception as e:
                logger.error(f"Error stopping loop: {e}", exc_info=True)
                shutdown_errors.append(("loop", e))

        # Cancel loop task if running
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await asyncio.wait_for(self._loop_task, timeout=10.0)
            except asyncio.CancelledError:
                logger.debug(f"Loop task cancelled for {self.name}")
            except TimeoutError:
                logger.warning(f"Loop task cancellation timed out for {self.name}")
                shutdown_errors.append(("loop_task", TimeoutError("Cancellation timed out")))

        # Shutdown capabilities (continue even if some fail)
        if self._capabilities:
            for cap_type in list(self._capabilities._instances.keys()):
                for emp_id in list(self._capabilities._instances[cap_type].keys()):
                    cap = self._capabilities._instances[cap_type].get(emp_id)
                    if cap:
                        try:
                            await cap.shutdown()
                        except Exception as e:
                            logger.error(
                                f"Failed to shutdown capability {cap_type}: {e}", exc_info=True
                            )
                            shutdown_errors.append((f"capability:{cap_type}", e))

        # Custom stop logic
        try:
            await self.on_stop()
        except Exception as e:
            logger.error(f"on_stop() hook failed for {self.name}: {e}", exc_info=True)
            shutdown_errors.append(("on_stop", e))

        # Close database session and dispose engine
        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                logger.error(f"Error closing session: {e}", exc_info=True)
                shutdown_errors.append(("session", e))
            self._session = None

        if self._engine:
            try:
                await self._engine.dispose()
            except Exception as e:
                logger.error(f"Error disposing engine: {e}", exc_info=True)
                shutdown_errors.append(("engine", e))
            self._engine = None
            self._sessionmaker = None

        # Mark as stopped
        self._is_running = False

        if shutdown_errors:
            logger.warning(
                f"Employee {self.name} stopped with {len(shutdown_errors)} error(s): "
                f"{[e[0] for e in shutdown_errors]}"
            )
        else:
            logger.info(f"Employee {self.name} stopped cleanly")

    async def on_start(self) -> None:
        """
        Called after employee is initialized but before loop starts.

        Override this to add custom initialization logic.
        Errors raised here will cause startup to fail.
        """

    async def on_stop(self) -> None:
        """
        Called during shutdown after loop stops.

        Override this to add custom cleanup logic.
        Errors raised here are logged but don't prevent shutdown.
        """

    # =========================================================================
    # Initialization Helpers
    # =========================================================================

    async def _validate_config(self) -> None:
        """
        Validate configuration before starting.

        Raises:
            EmployeeConfigError: If configuration is invalid
        """
        errors: list[str] = []

        # Check LLM API keys - at least one provider must be configured
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        vertex_project = os.getenv("VERTEX_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        azure_key = os.getenv("AZURE_OPENAI_API_KEY")

        if not any([anthropic_key, openai_key, vertex_project, azure_key]):
            errors.append(
                "No LLM credentials found. Set one of: ANTHROPIC_API_KEY, OPENAI_API_KEY, "
                "VERTEX_PROJECT_ID (or GOOGLE_CLOUD_PROJECT), or AZURE_OPENAI_API_KEY"
            )

        if errors:
            error_msg = "; ".join(errors)
            logger.error(f"Configuration validation failed: {error_msg}")
            raise EmployeeConfigError(f"Invalid configuration: {error_msg}")

        logger.debug("Configuration validation passed")

    async def _cleanup_on_error(self) -> None:
        """Clean up partially initialized components after error."""
        logger.info(f"Cleaning up after initialization error for {self.name}")

        # Stop loop if started
        if self._loop:
            try:
                await self._loop.stop()
            except Exception as e:
                logger.warning(f"Error stopping loop during cleanup: {e}")

        # Close database session and dispose engine
        if self._session:
            try:
                await self._session.close()
            except Exception as e:
                logger.warning(f"Error closing session during cleanup: {e}")
            self._session = None

        if self._engine:
            try:
                await self._engine.dispose()
            except Exception as e:
                logger.warning(f"Error disposing engine during cleanup: {e}")
            self._engine = None
            self._sessionmaker = None

        # Mark as not running
        self._is_running = False

        logger.debug(f"Cleanup complete for {self.name}")

    async def _init_employee_record(self, session: AsyncSession) -> None:
        """
        Create or load employee database record.

        Reuses existing employee if one exists with the same tenant_id and email.
        This ensures employee state persists across restarts.
        """
        # Try to find existing employee by tenant and email
        result = await session.execute(
            select(EmployeeModel).where(
                EmployeeModel.tenant_id == self.tenant_id,
                EmployeeModel.email == self.config.email,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Reuse existing employee
            self._db_employee = existing
            self._employee_id = existing.id

            # Update fields that may have changed
            existing.name = self.config.name
            existing.role = self.role
            existing.personality = self.personality.to_dict()
            existing.config = self.config.to_db_config()
            existing.capabilities = self.config.capabilities or self.default_capabilities
            existing.status = "active"

            logger.info(f"Loaded existing employee record: {self._employee_id}")
        else:
            # Create new employee
            self._db_employee = EmployeeModel(
                tenant_id=self.tenant_id,
                name=self.config.name,
                role=self.role,
                email=self.config.email,
                personality=self.personality.to_dict(),
                config=self.config.to_db_config(),
                capabilities=self.config.capabilities or self.default_capabilities,
                status="active",
                lifecycle_stage="autonomous",
            )
            session.add(self._db_employee)
            await session.flush()
            self._employee_id = self._db_employee.id

            logger.info(f"Created new employee record: {self._employee_id}")

    async def _init_llm(self) -> None:
        """
        Initialize LLM service.

        Raises:
            EmployeeConfigError: If required API keys are missing
        """
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        vertex_project = os.getenv("VERTEX_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        azure_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")

        # This should have been caught in _validate_config, but double-check
        if not any([anthropic_key, openai_key, vertex_project, azure_key]):
            raise EmployeeConfigError(
                "No LLM credentials found. Set one of: ANTHROPIC_API_KEY, OPENAI_API_KEY, "
                "VERTEX_PROJECT_ID, or AZURE_OPENAI_API_KEY"
            )

        llm_config = LLMConfig(
            primary_model=self.config.llm.primary_model,
            fallback_model=self.config.llm.fallback_model,
            anthropic_api_key=anthropic_key or "",
            openai_api_key=openai_key or "",
            vertex_project_id=vertex_project,
            azure_openai_api_key=azure_key,
            azure_openai_endpoint=azure_endpoint,
            azure_openai_deployment=azure_deployment,
        )
        self._llm = LLMService(llm_config)

        logger.debug(f"Initialized LLM service with primary model: {self.config.llm.primary_model}")

    async def _init_bdi(self, session: AsyncSession) -> None:
        """Initialize BDI components."""
        # LLM should be initialized before BDI
        assert self._llm is not None, "_init_llm() must be called before _init_bdi()"

        self._beliefs = BeliefSystem(
            session=session,
            employee_id=self.employee_id,
            tenant_id=self.tenant_id,
            llm_service=self._llm,
        )
        self._goals = GoalSystem(
            session=session,
            employee_id=self.employee_id,
            tenant_id=self.tenant_id,
        )
        self._intentions = IntentionStack(
            session=session,
            employee_id=self.employee_id,
            tenant_id=self.tenant_id,
        )

        logger.debug("Initialized BDI components")

    async def _init_memory(self, session: AsyncSession) -> None:
        """Initialize memory systems."""
        self._memory = MemorySystem(
            session=session,
            employee_id=self.employee_id,
            tenant_id=self.tenant_id,
        )

        logger.debug("Initialized memory systems")

    async def _init_capabilities(self) -> None:
        """
        Initialize and register capabilities.

        If a capability registry was injected in __init__, use it directly.
        Otherwise, create a new registry and validate capabilities.

        Raises:
            EmployeeConfigError: If unknown capabilities are specified
        """
        # Use injected registry if provided (for testing with simulated capabilities)
        if self._injected_capabilities is not None:
            self._capabilities = self._injected_capabilities
            logger.debug("Using injected capability registry")
            return

        # Create new registry for production use
        self._capabilities = CapabilityRegistry()

        # Get effective capabilities
        cap_list = self.config.capabilities or self.default_capabilities
        valid_capabilities = [ct.value.lower() for ct in CapabilityType]

        for cap_name in cap_list:
            try:
                # CapabilityType values are lowercase (e.g., "email", "calendar")
                cap_type = CapabilityType(cap_name.lower())
                # Capabilities are enabled when needed via the registry
                logger.debug(f"Capability available: {cap_type.value}")
            except ValueError as e:
                # Unknown capability - raise error instead of just warning
                raise EmployeeConfigError(
                    f"Unknown capability '{cap_name}'. Valid capabilities: {valid_capabilities}"
                ) from e

        logger.debug(f"Initialized capabilities: {cap_list}")

    async def _create_default_goals(self) -> None:
        """Create default goals for the role."""
        assert self._goals is not None, "_init_bdi() must be called before _create_default_goals()"

        goals = self.config.goals or self.default_goals

        for goal_config in goals:
            await self._goals.add_goal(
                goal_type=goal_config.goal_type,
                description=goal_config.description,
                priority=goal_config.priority,
                target=goal_config.target,
            )

        logger.debug(f"Created {len(goals)} default goals")

    async def _init_loop(self) -> None:
        """Initialize proactive execution loop."""
        # All components must be initialized before loop
        assert self._db_employee is not None, "Employee record not initialized"
        assert self._beliefs is not None, "BeliefSystem not initialized"
        assert self._goals is not None, "GoalSystem not initialized"
        assert self._intentions is not None, "IntentionStack not initialized"
        assert self._memory is not None, "MemorySystem not initialized"
        assert self._capabilities is not None, "CapabilityRegistry not initialized"

        loop_config = LoopConfig(
            cycle_interval_seconds=self.config.loop.cycle_interval_seconds,
            strategic_planning_interval_hours=self.config.loop.strategic_planning_interval_hours,
            deep_reflection_interval_hours=self.config.loop.reflection_interval_hours,
        )

        self._loop = ProactiveExecutionLoop(
            employee=self._db_employee,
            beliefs=self._beliefs,  # type: ignore[arg-type]
            goals=self._goals,
            intentions=self._intentions,  # type: ignore[arg-type]
            memory=self._memory,
            capability_registry=self._capabilities,
            config=loop_config,
        )

        logger.debug("Initialized proactive loop")

    async def _run_loop(self) -> None:
        """Run the proactive loop."""
        if self._loop:
            self._loop_task = asyncio.create_task(self._loop.start())
            # Wait for the loop to complete (it runs indefinitely)
            try:
                await self._loop_task
            except asyncio.CancelledError:
                logger.info(f"Loop cancelled for {self.name}")

    # =========================================================================
    # Public API
    # =========================================================================

    async def run_once(self) -> None:
        """
        Run a single cycle of the proactive loop.

        Useful for testing or manual control.

        Raises:
            EmployeeNotStartedError: If employee not started
        """
        if not self._is_running:
            raise EmployeeNotStartedError(f"Cannot run cycle on {self.name}: call start() first")

        if self._loop:
            await self._loop._run_cycle()

    def get_status(self) -> dict[str, Any]:
        """
        Get current employee status.

        Returns:
            Dictionary with status information including:
            - employee_id: UUID of the employee (None if not started)
            - name: Display name
            - role: Employee role
            - email: Email address
            - is_running: Whether currently running
            - started_at: ISO timestamp of start time
            - capabilities: List of enabled capabilities
        """
        return {
            "employee_id": str(self._employee_id) if self._employee_id else None,
            "name": self.name,
            "role": self.role,
            "email": self.email,
            "is_running": self._is_running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "capabilities": self.config.capabilities or self.default_capabilities,
        }

    def __repr__(self) -> str:
        status = "running" if self._is_running else "stopped"
        return f"<{self.__class__.__name__}(name={self.name}, role={self.role}, status={status})>"


__all__ = [
    "DigitalEmployee",
    "MemorySystem",
]
