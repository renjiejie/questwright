"""Shared fixtures for API integration tests.

Builds a FastAPI app wired to a fresh temp SQLite DB and isolated storage
dirs, so tests never touch the developer's real data/ directory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from services.db.models import Base


@pytest.fixture
def test_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Override Settings to point all storage at a temp dir."""
    import app.config as config_mod

    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PARSED_DIR", str(tmp_path / "parsed"))
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("CHROMA_COLLECTION", "test_rag")
    config_mod.get_settings.cache_clear()

    # Create schema synchronously up-front.
    sync_engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    settings = config_mod.get_settings()

    # services.db.session caches its engine/maker globally; reset so the
    # ingest BackgroundTask (which uses session_scope) targets this temp DB.
    import services.db.session as db_session

    db_session._engine = None
    db_session._session_maker = None

    yield settings

    db_session._engine = None
    db_session._session_maker = None
    config_mod.get_settings.cache_clear()


@pytest.fixture
def session_maker(test_settings) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(test_settings.DATABASE_URL, future=True)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def client(test_settings, session_maker) -> Iterator:
    from app.db import get_session
    from app.main import create_app
    from fastapi.testclient import TestClient

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_session] = _override_get_session
    with TestClient(app) as test_client:
        yield test_client
