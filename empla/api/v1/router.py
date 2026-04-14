"""
empla.api.v1.router - API v1 Router

Aggregates all v1 API endpoints.
"""

from fastapi import APIRouter

from empla.api.v1.endpoints import (
    activity,
    auth,
    bdi,
    employee_control,
    employees,
    integrations,
    mcp_servers,
    memory,
    metrics,
    playbooks,
    roles,
    webhooks,
)

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(employees.router, prefix="/employees", tags=["employees"])
api_router.include_router(employee_control.router, prefix="/employees", tags=["employee-control"])
api_router.include_router(activity.router, prefix="/activity", tags=["activity"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
api_router.include_router(mcp_servers.router, prefix="/mcp-servers", tags=["mcp-servers"])
api_router.include_router(roles.router, prefix="/roles", tags=["roles"])
api_router.include_router(bdi.router, prefix="/employees", tags=["bdi"])
api_router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(playbooks.router, prefix="/employees", tags=["playbooks"])
api_router.include_router(memory.router, prefix="/employees", tags=["memory"])
