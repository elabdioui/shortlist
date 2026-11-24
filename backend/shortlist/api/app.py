# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastAPI application factory and router registration."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker

from shortlist.api.rate_limit import LoginRateLimiter
from shortlist.api.routes import auth, candidates, jobs, privacy, providers, runs
from shortlist.api.startup import validate_startup_requirements
from shortlist.config import Settings, get_settings
from shortlist.schemas.common import HealthResponse


def create_app(
    *,
    settings_override: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    """Create and configure the Shortlist FastAPI application."""
    settings = settings_override or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        validate_startup_requirements(settings)
        yield

    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Open-source, self-hosted AI CV screening API.",
        license_info={"name": "AGPL-3.0-or-later"},
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )

    application.state.settings = settings
    application.state.login_limiter = LoginRateLimiter(max_attempts=5, window_seconds=60)
    if session_factory is not None:
        application.state.session_factory = session_factory

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/api/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        """Return service health status and version."""
        return HealthResponse(status="ok", version=settings.version)

    application.include_router(auth.router)
    application.include_router(providers.router)
    application.include_router(jobs.router)
    application.include_router(candidates.router)
    application.include_router(runs.router)
    application.include_router(privacy.router)

    return application


app = create_app()
