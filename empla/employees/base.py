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
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

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
from empla.employees.personality import Personality
from empla.llm import LLMConfig, LLMService
from empla.models.database import get_db
from empla.models.employee import Employee as EmployeeModel

logger = logging.getLogger(__name__)


class MemorySystem:
    """Container for all memory subsystems."""

    def __init__(
        self,
        session: AsyncSession,
        employee_id: UUID,
        tenant_id: UUID,
    ):
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

    def __init__(self, config: EmployeeConfig):
        """
        Initialize digital employee.

        Args:
            config: Employee configuration
        """
        self.config = config
        self._employee_id: UUID | None = None
        self._tenant_id: UUID | None = config.tenant_id or uuid4()
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
        self._loop_task: asyncio.Task | None = None

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
            raise RuntimeError("Employee not started. Call start() first.")
        return self._employee_id

    @property
    def tenant_id(self) -> UUID:
        """Tenant ID."""
        if self._tenant_id is None:
            raise RuntimeError("Tenant ID not set.")
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
            raise RuntimeError("Employee not started. Call start() first.")
        return self._llm

    @property
    def beliefs(self) -> BeliefSystem:
        """Belief system."""
        if self._beliefs is None:
            raise RuntimeError("Employee not started. Call start() first.")
        return self._beliefs

    @property
    def goals(self) -> GoalSystem:
        """Goal system."""
        if self._goals is None:
            raise RuntimeError("Employee not started. Call start() first.")
        return self._goals

    @property
    def intentions(self) -> IntentionStack:
        """Intention stack."""
        if self._intentions is None:
            raise RuntimeError("Employee not started. Call start() first.")
        return self._intentions

    @property
    def memory(self) -> MemorySystem:
        """Memory systems."""
        if self._memory is None:
            raise RuntimeError("Employee not started. Call start() first.")
        return self._memory

    @property
    def capabilities(self) -> CapabilityRegistry:
        """Capability registry."""
        if self._capabilities is None:
            raise RuntimeError("Employee not started. Call start() first.")
        return self._capabilities

    # =========================================================================
    # Lifecycle Methods
    # =========================================================================

    async def start(self, run_loop: bool = True) -> None:
        """
        Start the digital employee.

        This initializes all components and starts the proactive loop.

        Args:
            run_loop: Whether to start the proactive loop (default True)

        Example:
            >>> employee = SalesAE(config)
            >>> await employee.start()
            >>> # Employee is now running autonomously
        """
        if self._is_running:
            logger.warning(f"Employee {self.name} is already running")
            return

        logger.info(f"Starting employee: {self.name} ({self.role})")

        # Initialize database session
        # Note: In production, session should be managed externally
        async with get_db() as session:
            self._session = session

            # Create or load employee record
            await self._init_employee_record(session)

            # Initialize LLM service
            await self._init_llm()

            # Initialize BDI components
            await self._init_bdi(session)

            # Initialize memory systems
            await self._init_memory(session)

            # Initialize capabilities
            await self._init_capabilities()

            # Create default goals
            await self._create_default_goals()

            # Create proactive loop
            await self._init_loop()

            # Mark as running
            self._is_running = True
            self._started_at = datetime.now(UTC)

            # Custom start logic
            await self.on_start()

            logger.info(f"Employee {self.name} started successfully")

            # Start the loop
            if run_loop:
                await self._run_loop()

    async def stop(self) -> None:
        """
        Stop the digital employee.

        Gracefully shuts down the loop and all components.
        """
        if not self._is_running:
            logger.warning(f"Employee {self.name} is not running")
            return

        logger.info(f"Stopping employee: {self.name}")

        # Stop the loop
        if self._loop:
            await self._loop.stop()

        # Cancel loop task if running
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass

        # Shutdown capabilities
        if self._capabilities:
            for cap_type in list(self._capabilities._instances.keys()):
                for emp_id in list(self._capabilities._instances[cap_type].keys()):
                    cap = self._capabilities._instances[cap_type].get(emp_id)
                    if cap:
                        await cap.shutdown()

        # Custom stop logic
        await self.on_stop()

        # Mark as stopped
        self._is_running = False

        logger.info(f"Employee {self.name} stopped")

    async def on_start(self) -> None:
        """
        Called after employee is initialized but before loop starts.

        Override this to add custom initialization logic.
        """
        pass

    async def on_stop(self) -> None:
        """
        Called during shutdown after loop stops.

        Override this to add custom cleanup logic.
        """
        pass

    # =========================================================================
    # Initialization Helpers
    # =========================================================================

    async def _init_employee_record(self, session: AsyncSession) -> None:
        """Create or load employee database record."""
        # For now, create a new employee
        # In production, would check if exists first
        self._db_employee = EmployeeModel(
            tenant_id=self.tenant_id,
            name=self.config.name,
            role=self.config.role,
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

        logger.debug(f"Created employee record: {self._employee_id}")

    async def _init_llm(self) -> None:
        """Initialize LLM service."""
        import os

        llm_config = LLMConfig(
            primary_model=self.config.llm.primary_model,
            fallback_model=self.config.llm.fallback_model,
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        )
        self._llm = LLMService(llm_config)

        logger.debug("Initialized LLM service")

    async def _init_bdi(self, session: AsyncSession) -> None:
        """Initialize BDI components."""
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
            llm_service=self._llm,
        )
        self._intentions = IntentionStack(
            session=session,
            employee_id=self.employee_id,
            tenant_id=self.tenant_id,
            llm_service=self._llm,
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
        """Initialize and register capabilities."""
        self._capabilities = CapabilityRegistry()

        # Get effective capabilities
        cap_list = self.config.capabilities or self.default_capabilities

        for cap_name in cap_list:
            try:
                cap_type = CapabilityType(cap_name.upper())
                # Capabilities are enabled when needed
                # For now, just log what would be enabled
                logger.debug(f"Capability available: {cap_type.value}")
            except ValueError:
                logger.warning(f"Unknown capability: {cap_name}")

        logger.debug(f"Initialized capabilities: {cap_list}")

    async def _create_default_goals(self) -> None:
        """Create default goals for the role."""
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
        loop_config = LoopConfig(
            cycle_interval=self.config.loop.cycle_interval_seconds,
            strategic_planning_interval=self.config.loop.strategic_planning_interval_hours * 3600,
            reflection_interval=self.config.loop.reflection_interval_hours * 3600,
        )

        self._loop = ProactiveExecutionLoop(
            employee=self._db_employee,
            beliefs=self._beliefs,
            goals=self._goals,
            intentions=self._intentions,
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
        """
        if not self._is_running:
            raise RuntimeError("Employee not started. Call start() first.")

        if self._loop:
            await self._loop._run_cycle()

    def get_status(self) -> dict[str, Any]:
        """
        Get current employee status.

        Returns:
            Dictionary with status information
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
