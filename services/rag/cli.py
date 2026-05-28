"""CLI utilities for RAG ingestion workflows."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[2]
APPS_API_PATH = REPO_ROOT / "apps" / "api"


def _bootstrap_import_paths() -> None:
    """Allow direct `python3 -m services.rag.cli ...` without manual PYTHONPATH."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(APPS_API_PATH) not in sys.path:
        sys.path.insert(0, str(APPS_API_PATH))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m services.rag.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    load_srd = subparsers.add_parser("load-srd", help="Load SRD records from local JSON files")
    load_srd.add_argument("--dry-run", action="store_true", help="Print per-file record counts")
    load_srd.add_argument("--srd-path", help="Override SRD path (defaults to SRD_DATA_PATH)")

    reindex_srd = subparsers.add_parser("reindex-srd", help="Chunk/embed/index all SRD records")
    reindex_srd.add_argument("--srd-path", help="Override SRD path (defaults to SRD_DATA_PATH)")
    reindex_srd.add_argument(
        "--batch-size", type=int, help="Embedding batch size (defaults to EMBEDDING_BATCH_SIZE)"
    )

    search = subparsers.add_parser("search", help="Run vector search against indexed SRD data")
    search.add_argument("query", help="Search query")
    search.add_argument("--top-k", type=int, default=5, help="Result count")

    return parser


def _run_load_srd(args: argparse.Namespace) -> int:
    from services.rag.srd_loader import iter_records

    records = list(iter_records(args.srd_path))
    if args.dry_run:
        per_file = Counter(record.file_name for record in records)
        for file_name in sorted(per_file):
            print(f"{file_name}\t{per_file[file_name]}")
    else:
        print(f"Loaded {len(records)} SRD records.")
    return 0


async def _run_reindex_srd(args: argparse.Namespace) -> int:
    from app.config import get_settings

    from services.db.session import session_scope
    from services.rag.chunkers import chunk_record
    from services.rag.embed import embed_texts
    from services.rag.index import ChromaIndex, existing_chunk_ids, upsert_chunks_sqlite
    from services.rag.srd_loader import iter_records

    settings = get_settings()
    batch_size = args.batch_size or settings.EMBEDDING_BATCH_SIZE

    records = list(iter_records(args.srd_path))
    chunks = [chunk_record(record) for record in records]
    print(f"Loaded {len(records)} records, produced {len(chunks)} chunks.")

    async with session_scope() as session:
        done_ids = await existing_chunk_ids(session, [chunk.id for chunk in chunks])
        pending_chunks = [chunk for chunk in chunks if chunk.id not in done_ids]
        print(f"Already indexed: {len(done_ids)}; pending: {len(pending_chunks)}")

        if not pending_chunks:
            print("No pending chunks. Reindex complete.")
            return 0

        texts = [chunk.text for chunk in pending_chunks]
        embeddings = await embed_texts(texts, batch_size=batch_size)
        index = ChromaIndex(
            persist_path=settings.CHROMA_PATH,
            collection_name=settings.CHROMA_COLLECTION,
        )
        index.upsert_chunks(pending_chunks, embeddings)
        await upsert_chunks_sqlite(session, pending_chunks)
        print(f"Indexed {len(pending_chunks)} chunks.")
    return 0


async def _run_search(args: argparse.Namespace) -> int:
    from app.config import get_settings

    from services.db.models import RagChunk as RagChunkModel
    from services.db.session import session_scope
    from services.rag.embed import embed_texts
    from services.rag.index import ChromaIndex

    settings = get_settings()
    query_embedding = (await embed_texts([args.query], batch_size=1))[0]
    index = ChromaIndex(
        persist_path=settings.CHROMA_PATH,
        collection_name=settings.CHROMA_COLLECTION,
    )
    rows = index.query(query_embedding, top_k=args.top_k)
    async with session_scope() as session:
        chunk_ids = [str(item["chunk_id"]) for item in rows]
        result = await session.execute(select(RagChunkModel).where(RagChunkModel.id.in_(chunk_ids)))
        db_chunks = {row.id: row for row in result.scalars().all()}

    for item in rows:
        metadata = item["metadata"] if isinstance(item["metadata"], dict) else {}
        db_row = db_chunks.get(str(item["chunk_id"]))
        title = db_row.title if db_row and db_row.title else item["chunk_id"]
        source = metadata.get("source", "unknown")
        text = str(item.get("text", "")).replace("\n", " ")[:180]
        print(
            f"- title={title} source={source} score={item['score']}\n"
            f"  chunk_id={item['chunk_id']}\n"
            f"  text={text}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    _bootstrap_import_paths()
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "load-srd":
            return _run_load_srd(args)
        if args.command == "reindex-srd":
            return asyncio.run(_run_reindex_srd(args))
        if args.command == "search":
            return asyncio.run(_run_search(args))
        parser.error(f"Unsupported command: {args.command}")
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
