"""
empla.api.main - FastAPI Application Factory

Creates and configures the FastAPI application for the empla dashboard API.

Usage:
    # Development
    uvicorn empla.api.main:app --reload

    # Production
    uvicorn empla.api.main:app --host 0.0.0.0 --port 8000

Environment Variables:
    CORS_ORIGINS: Comma-separated list of allowed CORS origins
                  Default: http://localhost:3000,http://localhost:5173
"""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from empla.api.v1.router import api_router
from empla.models.database import get_engine, get_sessionmaker

logger = logging.getLogger(__name__)

# Default CORS origins for development
DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",  # React dev server
    "http://localhost:5173",  # Vite dev server
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]


def get_cors_origins() -> list[str]:
    """
    Get CORS origins from environment or use defaults.

    Set CORS_ORIGINS env var as comma-separated list for production.
    """
    env_origins = os.environ.get("CORS_ORIGINS", "")
    if env_origins:
        origins = [origin.strip() for origin in env_origins.split(",") if origin.strip()]
        if origins:
            return origins
    return DEFAULT_CORS_ORIGINS


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.

    Sets up database connection pool on startup,
    cleans up on shutdown.
    """
    # Startup
    logger.info("Starting empla API server...")

    # Create database engine and session factory
    engine = get_engine()
    app.state.engine = engine
    app.state.sessionmaker = get_sessionmaker(engine)

    logger.info("Database connection pool initialized")

    yield

    # Shutdown
    logger.info("Shutting down empla API server...")
    await engine.dispose()
    logger.info("Database connections closed")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="empla API",
        description="API for managing digital employees",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Configure CORS - use env var CORS_ORIGINS for production
    cors_origins = get_cors_origins()
    logger.info(f"Configuring CORS for origins: {cors_origins}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routes
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


# Create the application instance
app = create_app()
