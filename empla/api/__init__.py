"""
empla.api - FastAPI REST API

Provides REST API for managing digital employees.

Usage:
    uvicorn empla.api.main:app --reload
"""

from empla.api.main import app, create_app

__all__ = ["app", "create_app"]
