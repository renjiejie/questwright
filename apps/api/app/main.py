"""FastAPI application entrypoint.

Phase 0 scope: `/healthz` for liveness + `/artifacts` CRUD with fork-based
revise semantics. Routers for projects / sources / workflow / reviews are
added in later phases.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import get_settings
from app.routers import artifacts


class HealthResponse(BaseModel):
    status: str
    env: str


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Questwright API",
        version="0.1.0",
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["meta"])
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok", env=settings.APP_ENV)

    app.include_router(artifacts.router)

    return app


app = create_app()
