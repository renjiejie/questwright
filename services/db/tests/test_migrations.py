from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[3]
INITIAL_REVISION = "97ba4eed80a8"


def _make_alembic_config(database_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("+aiosqlite", ""))
    return config


def test_upgrade_head_keeps_existing_rag_chunks(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "phase0.db"
    database_url = f"sqlite+aiosqlite:///{db_path}"

    monkeypatch.setenv("DATABASE_URL", database_url)
    alembic_cfg = _make_alembic_config(database_url)

    command.upgrade(alembic_cfg, INITIAL_REVISION)

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO rag_chunks (
            id, source, source_title, chunk_type, title, section_path, page_start,
            page_end, tags, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            "legacy_chunk_1",
            "srd_misc",
            "Legacy",
            "rule_chunk",
            "Legacy Title",
            "[]",
            None,
            None,
            "[]",
        ),
    )
    conn.commit()
    conn.close()

    command.upgrade(alembic_cfg, "head")

    conn = sqlite3.connect(db_path)
    row_count = conn.execute(
        "SELECT COUNT(*) FROM rag_chunks WHERE id = 'legacy_chunk_1'"
    ).fetchone()[0]
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info('rag_chunks')").fetchall()
    }
    conn.close()

    assert row_count == 1
    assert {
        "project_id",
        "source_id",
        "source_ref",
        "canon_level",
        "metadata",
        "chunk_text",
    }.issubset(columns)
