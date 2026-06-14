"""Async world-bible ingest pipeline (Phase 1b).

Drives a source through the status machine
``uploaded -> parsing -> chunking -> embedding -> indexed`` (or ``failed`` with
``last_error``). Reuses the SRD indexing path (Chroma + SQLite double write).
Re-ingesting the same ``source_id`` deletes its old chunks first (idempotent
overwrite), so there are no orphans.

Runs under its own DB session because FastAPI BackgroundTasks execute outside
the request/response session scope.
"""

from __future__ import annotations

import logging
from pathlib import Path

from services.db.repositories import SourceRepository
from services.db.session import session_scope

logger = logging.getLogger(__name__)


def _find_raw_path(upload_dir: str, project_id: str, source_id: str) -> Path:
    project_dir = Path(upload_dir) / project_id
    matches = sorted(project_dir.glob(f"{source_id}__*"))
    if not matches:
        raise FileNotFoundError(
            f"no uploaded file found for source {source_id} under {project_dir}"
        )
    return matches[0]


async def ingest_source(source_id: str) -> None:
    """Parse -> chunk -> embed -> index a single uploaded source.

    Status transitions are persisted as we go so the client can poll
    ``GET /projects/{id}/sources/{source_id}``. Any failure records
    ``status="failed"`` + ``last_error`` and leaves Chroma untouched for the
    affected source (best-effort).
    """
    from app.config import get_settings

    from services.rag.chunkers.lore_chunker import chunk_lore
    from services.rag.embed import embed_texts
    from services.rag.index import (
        ChromaIndex,
        delete_chunks_by_source_id,
        upsert_chunks_sqlite,
    )
    from services.rag.parsers import Parser

    settings = get_settings()

    try:
        async with session_scope() as session:
            repo = SourceRepository(session)
            source = await repo.get(source_id)
            project_id = source.project_id
            source_title = source.original_filename
            kind = source.kind

        # --- parsing ---
        async with session_scope() as session:
            await SourceRepository(session).update_status(source_id, "parsing")

        raw_path = _find_raw_path(settings.UPLOAD_DIR, project_id, source_id)
        parser = Parser()
        parse_result = parser.parse(
            kind=kind,
            raw_path=raw_path,
            project_id=project_id,
            source_id=source_id,
            parsed_dir=settings.PARSED_DIR,
        )

        # --- chunking ---
        async with session_scope() as session:
            await SourceRepository(session).update_status(source_id, "chunking")

        chunks = chunk_lore(
            parse_result.markdown,
            source_id=source_id,
            project_id=project_id,
            source_title=source_title,
        )
        if not chunks:
            raise ValueError("no chunks produced from parsed markdown")

        # --- embedding ---
        async with session_scope() as session:
            await SourceRepository(session).update_status(source_id, "embedding")

        embeddings = await embed_texts(
            [c.text for c in chunks], batch_size=settings.EMBEDDING_BATCH_SIZE
        )

        # --- index (idempotent overwrite by source_id) ---
        index = ChromaIndex(
            persist_path=settings.CHROMA_PATH,
            collection_name=settings.CHROMA_COLLECTION,
        )
        index.delete_by_source_id(source_id)
        index.upsert_chunks(chunks, embeddings)

        async with session_scope() as session:
            await delete_chunks_by_source_id(session, source_id)
            await upsert_chunks_sqlite(session, chunks)
            await SourceRepository(session).update_status(source_id, "indexed")

        # --- keep BM25 in-memory index fresh (if running) ---
        try:
            from services.rag.retriever import get_bm25_retriever

            retriever = get_bm25_retriever()
            if retriever is not None:
                retriever.remove_chunks([c.id for c in chunks])
                retriever.add_chunks([(c.id, c.text, _bm25_meta(c)) for c in chunks])
        except Exception:  # pragma: no cover - BM25 freshness is best-effort
            logger.warning("Failed to update BM25 index after ingest", exc_info=True)

        logger.info("Ingest complete for source %s (%d chunks)", source_id, len(chunks))

    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingest failed for source %s", source_id)
        try:
            async with session_scope() as session:
                await SourceRepository(session).set_error(source_id, str(exc))
        except Exception:  # pragma: no cover
            logger.exception("Failed to record ingest error for source %s", source_id)


def _bm25_meta(chunk) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "source": chunk.source,
        "chunk_type": chunk.chunk_type,
        "project_id": chunk.metadata.get("project_id"),
        "tags": chunk.tags,
        **{k: v for k, v in chunk.metadata.items() if k in ("cr", "spell_level")},
    }
