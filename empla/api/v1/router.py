"""
empla.api.v1.router - API v1 Router

Aggregates all v1 API endpoints.
"""

from fastapi import APIRouter

from empla.api.v1.endpoints import activity, auth, employee_control, employees, integrations

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(employees.router, prefix="/employees", tags=["employees"])
api_router.include_router(employee_control.router, prefix="/employees", tags=["employee-control"])
api_router.include_router(activity.router, prefix="/activity", tags=["activity"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
