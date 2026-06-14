"""FastAPI application entrypoint.

Phase 0: `/healthz` + `/artifacts` CRUD.
Phase 1b/1c: `/projects/{id}/sources` ingest + `/projects/{id}/retrieve`.
The BM25 in-memory index is built once in the lifespan startup from SQLite.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import get_settings
from app.routers import artifacts, retrieve, sources

logger = logging.getLogger(__name__)

BM25_BUILD_WARN_SECONDS = 5.0


class HealthResponse(BaseModel):
    status: str
    env: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the BM25 in-memory index from SQLite once at startup.
    try:
        from services.db.session import session_scope
        from services.rag.retriever import BM25Retriever, set_bm25_retriever

        async with session_scope() as session:
            retriever = await BM25Retriever.from_sqlite(session)
        elapsed = getattr(retriever, "_build_elapsed", 0.0)
        if elapsed > BM25_BUILD_WARN_SECONDS:
            logger.warning(
                "BM25 index build took %.2fs (> %ss); consider an external index.",
                elapsed,
                BM25_BUILD_WARN_SECONDS,
            )
        logger.info("BM25 index ready: %d chunks in %.2fs", len(retriever), elapsed)
        set_bm25_retriever(retriever)
    except Exception:  # pragma: no cover - startup must not crash on empty/missing DB
        logger.warning("BM25 index initialization failed; continuing without it.", exc_info=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Questwright API",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["meta"])
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok", env=settings.APP_ENV)

    # The Knowledge debug UI runs on a different port (3765) than the API, so
    # browser fetches are cross-origin. Enable CORS outside prod for local dev.
    if settings.APP_ENV != "prod":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins(),
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(artifacts.router)
    app.include_router(sources.router)
    app.include_router(retrieve.router)

    return app


app = create_app()
