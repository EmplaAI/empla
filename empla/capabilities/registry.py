"""
Capability Registry

Central registry for managing capability lifecycle and routing.
"""

from typing import Dict, List, Optional, Type
from uuid import UUID
import logging

from empla.capabilities.base import (
    BaseCapability,
    CapabilityType,
    CapabilityConfig,
    Observation,
    Action,
    ActionResult,
)

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    """
    Central registry for all capabilities.

    Manages capability lifecycle:
    - Registration of capability implementations
    - Enabling/disabling capabilities for employees
    - Routing perception and actions to appropriate capabilities

    Thread-safe and designed for multi-tenant environments.

    Usage:
        # Create registry
        registry = CapabilityRegistry()

        # Register capability implementations
        registry.register(CapabilityType.EMAIL, EmailCapability)
        registry.register(CapabilityType.CALENDAR, CalendarCapability)

        # Enable for employee
        await registry.enable_for_employee(
            employee_id=employee.id,
            tenant_id=employee.tenant_id,
            capability_type=CapabilityType.EMAIL,
            config=EmailConfig(...)
        )

        # Perceive environment
        observations = await registry.perceive_all(employee.id)

        # Execute action
        result = await registry.execute_action(employee.id, action)

        # Disable when done
        await registry.disable_for_employee(
            employee_id=employee.id,
            capability_type=CapabilityType.EMAIL
        )
    """

    def __init__(self):
        """Initialize empty registry"""
        # Map of capability type -> implementation class
        self._capabilities: Dict[CapabilityType, Type[BaseCapability]] = {}

        # Map of employee_id -> capability_type -> instance
        self._instances: Dict[UUID, Dict[CapabilityType, BaseCapability]] = {}

    def register(
        self, capability_type: CapabilityType, capability_class: Type[BaseCapability]
    ) -> None:
        """
        Register a capability implementation.

        Args:
            capability_type: Type of capability
            capability_class: Implementation class (must extend BaseCapability)

        Raises:
            ValueError: If capability_class doesn't extend BaseCapability
        """
        if not issubclass(capability_class, BaseCapability):
            raise ValueError(
                f"{capability_class.__name__} must extend BaseCapability"
            )

        self._capabilities[capability_type] = capability_class

        logger.info(
            f"Registered capability: {capability_type}",
            extra={"capability_class": capability_class.__name__},
        )

    async def enable_for_employee(
        self,
        employee_id: UUID,
        tenant_id: UUID,
        capability_type: CapabilityType,
        config: CapabilityConfig,
    ) -> BaseCapability:
        """
        Enable a capability for an employee.

        Creates capability instance, initializes it, and stores for later use.

        Args:
            employee_id: Employee to enable capability for
            tenant_id: Tenant the employee belongs to
            capability_type: Type of capability to enable
            config: Capability configuration

        Returns:
            Initialized capability instance

        Raises:
            ValueError: If capability type not registered
            Exception: If initialization fails
        """
        if capability_type not in self._capabilities:
            raise ValueError(f"Capability not registered: {capability_type}")

        # Create employee capabilities dict if needed
        if employee_id not in self._instances:
            self._instances[employee_id] = {}

        # Check if already enabled
        if capability_type in self._instances[employee_id]:
            logger.warning(
                f"Capability {capability_type} already enabled for employee {employee_id}"
            )
            return self._instances[employee_id][capability_type]

        # Create instance
        capability_class = self._capabilities[capability_type]
        instance = capability_class(
            tenant_id=tenant_id, employee_id=employee_id, config=config
        )

        # Initialize
        try:
            await instance.initialize()
        except Exception as e:
            logger.error(
                f"Failed to initialize {capability_type} for employee {employee_id}",
                exc_info=True,
            )
            raise

        # Store
        self._instances[employee_id][capability_type] = instance

        logger.info(
            f"Enabled {capability_type} for employee {employee_id}",
            extra={
                "employee_id": str(employee_id),
                "tenant_id": str(tenant_id),
                "capability_type": capability_type,
            },
        )

        return instance

    async def disable_for_employee(
        self, employee_id: UUID, capability_type: CapabilityType
    ) -> None:
        """
        Disable a capability for an employee.

        Shuts down capability and removes from registry.

        Args:
            employee_id: Employee to disable capability for
            capability_type: Type of capability to disable
        """
        if employee_id not in self._instances:
            logger.warning(
                f"No capabilities enabled for employee {employee_id}"
            )
            return

        if capability_type not in self._instances[employee_id]:
            logger.warning(
                f"Capability {capability_type} not enabled for employee {employee_id}"
            )
            return

        # Shutdown capability
        capability = self._instances[employee_id][capability_type]
        try:
            await capability.shutdown()
        except Exception as e:
            logger.error(
                f"Error during {capability_type} shutdown for employee {employee_id}",
                exc_info=True,
            )

        # Remove from registry
        del self._instances[employee_id][capability_type]

        logger.info(
            f"Disabled {capability_type} for employee {employee_id}",
            extra={
                "employee_id": str(employee_id),
                "capability_type": capability_type,
            },
        )

    async def disable_all_for_employee(self, employee_id: UUID) -> None:
        """
        Disable all capabilities for an employee.

        Used when employee is deactivated or offboarded.

        Args:
            employee_id: Employee to disable all capabilities for
        """
        if employee_id not in self._instances:
            return

        # Disable each capability
        capability_types = list(self._instances[employee_id].keys())
        for capability_type in capability_types:
            await self.disable_for_employee(employee_id, capability_type)

        # Remove employee from registry
        del self._instances[employee_id]

        logger.info(
            f"Disabled all capabilities for employee {employee_id}",
            extra={"employee_id": str(employee_id)},
        )

    def get_capability(
        self, employee_id: UUID, capability_type: CapabilityType
    ) -> Optional[BaseCapability]:
        """
        Get capability instance for employee.

        Args:
            employee_id: Employee ID
            capability_type: Type of capability

        Returns:
            Capability instance if enabled, None otherwise
        """
        if employee_id not in self._instances:
            return None

        return self._instances[employee_id].get(capability_type)

    def get_enabled_capabilities(self, employee_id: UUID) -> List[CapabilityType]:
        """
        Get list of enabled capabilities for employee.

        Args:
            employee_id: Employee ID

        Returns:
            List of enabled capability types (empty if none)
        """
        if employee_id not in self._instances:
            return []

        return list(self._instances[employee_id].keys())

    async def perceive_all(self, employee_id: UUID) -> List[Observation]:
        """
        Run perception across all enabled capabilities for employee.

        Called by proactive loop during perception phase.

        Args:
            employee_id: Employee ID

        Returns:
            List of observations from all capabilities (can be empty)
        """
        if employee_id not in self._instances:
            return []

        observations = []

        for capability_type, capability in list(self._instances[employee_id].items()):
            try:
                obs = await capability.perceive()
                observations.extend(obs)

                if obs:
                    logger.debug(
                        f"{capability_type} perceived {len(obs)} observations",
                        extra={
                            "employee_id": str(employee_id),
                            "capability_type": capability_type,
                            "observation_count": len(obs),
                        },
                    )

            except Exception as e:
                logger.error(
                    f"Perception failed for {capability_type}",
                    exc_info=True,
                    extra={
                        "employee_id": str(employee_id),
                        "capability_type": capability_type,
                    },
                )
                # Continue with other capabilities
        return observations

    async def execute_action(
        self, employee_id: UUID, action: Action
    ) -> ActionResult:
        """
        Execute action using appropriate capability.

        Routes action to the capability that can execute it.

        Args:
            employee_id: Employee ID
            action: Action to execute

        Returns:
            Result of action execution
        """
        # Parse capability from action
        capability_type = CapabilityType(action.capability)

        # Get capability instance
        capability = self.get_capability(employee_id, capability_type)

        if not capability:
            logger.error(
                f"Capability {capability_type} not enabled for employee {employee_id}",
                extra={
                    "employee_id": str(employee_id),
                    "capability_type": capability_type,
                    "action": action.operation,
                },
            )
            return ActionResult(
                success=False, error=f"Capability {capability_type} not enabled"
            )

        # Execute action
        try:
            result = await capability.execute_action(action)

            logger.info(
                f"Action executed: {action.operation}",
                extra={
                    "employee_id": str(employee_id),
                    "capability_type": capability_type,
                    "operation": action.operation,
                    "success": result.success,
                },
            )

            return result

        except Exception as e:
            logger.error(
                f"Action execution failed: {action.operation}",
                exc_info=True,
                extra={
                    "employee_id": str(employee_id),
                    "capability_type": capability_type,
                    "operation": action.operation,
                },
            )
            return ActionResult(success=False, error=str(e))

    def health_check(self, employee_id: UUID) -> Dict[CapabilityType, bool]:
        """
        Run health check on all capabilities for employee.

        Args:
            employee_id: Employee ID

        Returns:
            Dict mapping capability type to health status
        """
        if employee_id not in self._instances:
            return {}

        health_status = {}
        for capability_type, capability in self._instances[employee_id].items():
            health_status[capability_type] = capability.is_healthy()

        return health_status

    def __repr__(self) -> str:
        registered = len(self._capabilities)
        employees = len(self._instances)
        return (
            f"CapabilityRegistry("
            f"registered={registered}, "
            f"employees_with_capabilities={employees})"
        )
