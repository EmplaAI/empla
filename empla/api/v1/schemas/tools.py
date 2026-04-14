"""
empla.api.v1.schemas.tools - Tool catalog response schemas.

Read-only schemas for the per-employee tool catalog, integration health,
and trust-boundary blocks. The runner exposes these via its HealthServer
(empla.runner.health) and the API proxies through ``EmployeeManager``.
"""

from pydantic import BaseModel


class ToolCatalogItem(BaseModel):
    """A single tool the employee can call."""

    name: str
    description: str | None = None
    integration: str | None = None


class ToolCatalogResponse(BaseModel):
    items: list[ToolCatalogItem]
    total: int
    integrations: list[str]


class IntegrationHealthResponse(BaseModel):
    name: str
    status: str
    success_count: int = 0
    failure_count: int = 0
    timeout_count: int = 0
    total_calls: int = 0
    avg_latency_ms: float = 0.0
    error_rate: float = 0.0
    last_error: str | None = None


class BlockedToolEntry(BaseModel):
    tool_name: str
    reason: str
    employee_role: str | None = None
    timestamp: float


class TrustCycleStats(BaseModel):
    total_decisions: int = 0
    allowed: int = 0
    denied: int = 0
    tainted: bool = False
    cycle_calls: int = 0
    max_calls_per_cycle: int = 0


class BlockedToolsResponse(BaseModel):
    items: list[BlockedToolEntry]
    total: int
    stats: TrustCycleStats
