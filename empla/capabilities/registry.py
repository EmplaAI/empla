"""
Capability Registry

Central registry for managing capability lifecycle and routing.
"""

import logging
from uuid import UUID

from empla.capabilities.base import (
    Action,
    ActionResult,
    BaseCapability,
    CapabilityConfig,
    CapabilityType,
    Observation,
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

    def __init__(self) -> None:
        """Initialize empty registry"""
        # Map of capability type -> implementation class
        self._capabilities: dict[CapabilityType, type[BaseCapability]] = {}

        # Map of employee_id -> capability_type -> instance
        self._instances: dict[UUID, dict[CapabilityType, BaseCapability]] = {}

    def register(
        self, capability_type: CapabilityType, capability_class: type[BaseCapability]
    ) -> None:
        """
        Register a capability implementation for a capability type.

        Parameters:
            capability_type (CapabilityType): Identifier of the capability being registered.
            capability_class (Type[BaseCapability]): Implementation class to associate with the capability; must be a subclass of `BaseCapability`.

        Raises:
            ValueError: If `capability_class` does not subclass `BaseCapability`.
        """
        if not issubclass(capability_class, BaseCapability):
            raise ValueError(f"{capability_class.__name__} must extend BaseCapability")

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
        Enable the given capability for an employee by instantiating, initializing, and registering it.

        Parameters:
            employee_id (UUID): Employee identifier for whom the capability is enabled.
            tenant_id (UUID): Tenant identifier the employee belongs to.
            capability_type (CapabilityType): Capability type to enable.
            config (CapabilityConfig): Configuration passed to the capability on creation.

        Returns:
            BaseCapability: The initialized capability instance.

        Raises:
            ValueError: If the capability type is not registered.
            Exception: If the capability instance fails to initialize.
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
        instance = capability_class(tenant_id=tenant_id, employee_id=employee_id, config=config)

        # Initialize
        try:
            await instance.initialize()
        except Exception:
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
        Disable and remove a specific capability for an employee.

        If the capability is not enabled for the given employee, the call is a no-op. If enabled, the method attempts to call the capability's shutdown routine; any exception raised during shutdown is logged and suppressed, and the capability is removed from the registry.

        Parameters:
            employee_id (UUID): Identifier of the employee whose capability should be disabled.
            capability_type (CapabilityType): The type of capability to disable.
        """
        if employee_id not in self._instances:
            logger.warning(f"No capabilities enabled for employee {employee_id}")
            return

        if capability_type not in self._instances[employee_id]:
            logger.warning(f"Capability {capability_type} not enabled for employee {employee_id}")
            return

        # Shutdown capability
        capability = self._instances[employee_id][capability_type]
        try:
            await capability.shutdown()
        except Exception:
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
        Disable all capabilities currently enabled for the given employee and remove the employee entry from the registry.

        If the employee has no enabled capabilities this function returns without error. Each enabled capability is shut down via disable_for_employee; errors during individual shutdowns are handled by that method and do not prevent other capabilities from being disabled.

        Parameters:
            employee_id (UUID): Identifier of the employee whose capabilities should be disabled.
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
    ) -> BaseCapability | None:
        """
        Retrieve the enabled capability instance for an employee.

        @returns: `BaseCapability` instance for the given capability type if enabled for the employee, `None` otherwise.
        """
        if employee_id not in self._instances:
            return None

        return self._instances[employee_id].get(capability_type)

    def get_enabled_capabilities(self, employee_id: UUID) -> list[CapabilityType]:
        """
        List the capability types currently enabled for the given employee.

        Parameters:
            employee_id (UUID): Employee identifier to query.

        Returns:
            enabled_capabilities (List[CapabilityType]): Enabled capability types for the employee; empty list if none are enabled.
        """
        if employee_id not in self._instances:
            return []

        return list(self._instances[employee_id].keys())

    async def perceive_all(self, employee_id: UUID) -> list[Observation]:
        """
        Aggregate observations from all capabilities enabled for the given employee.

        If the employee has no enabled capabilities this returns an empty list. Exceptions raised by individual capabilities are logged and skipped so that perception continues for remaining capabilities.

        Returns:
            List[Observation]: Observations collected from enabled capabilities; empty list if none.
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

            except Exception:
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

    async def execute_action(self, employee_id: UUID, action: Action) -> ActionResult:
        """
        Route and execute an Action using the employee's enabled capability.

        If the employee does not have the required capability enabled, returns a failure ActionResult with an explanatory error. If executing the capability raises an exception, returns a failure ActionResult containing the exception message; otherwise returns the capability's ActionResult.

        Returns:
            ActionResult: `success` is `True` when the action completed successfully; `False` otherwise, with `error` populated on failure.
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
            return ActionResult(success=False, error=f"Capability {capability_type} not enabled")

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

    def health_check(self, employee_id: UUID) -> dict[CapabilityType, bool]:
        """
        Run a health check for every capability enabled for the given employee.

        Parameters:
            employee_id (UUID): Identifier of the employee whose enabled capabilities will be checked.

        Returns:
            health_status (Dict[CapabilityType, bool]): Mapping from capability type to `true` if that capability reports healthy, `false` otherwise. If the employee has no enabled capabilities, returns an empty dict.
        """
        if employee_id not in self._instances:
            return {}

        health_status = {}
        for capability_type, capability in self._instances[employee_id].items():
            health_status[capability_type] = capability.is_healthy()

        return health_status

    def __repr__(self) -> str:
        """
        Return a concise string representation of the registry showing counts of registered capability types and employees with enabled capabilities.

        Returns:
            str: A string in the form "CapabilityRegistry(registered={registered}, employees_with_capabilities={employees})".
        """
        registered = len(self._capabilities)
        employees = len(self._instances)
        return (
            f"CapabilityRegistry(registered={registered}, employees_with_capabilities={employees})"
        )
