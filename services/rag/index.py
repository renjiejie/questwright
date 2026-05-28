"""Chroma + SQLite indexing utilities for RAG chunks."""

from __future__ import annotations

from pathlib import Path

import chromadb
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from services.db.models import RagChunk as RagChunkModel
from services.rag.schemas import RagChunk


class ChromaIndex:
    def __init__(self, *, persist_path: str | Path, collection_name: str) -> None:
        self._client = chromadb.PersistentClient(path=str(persist_path))
        self._collection = self._client.get_or_create_collection(collection_name)

    def count(self) -> int:
        return self._collection.count()

    def upsert_chunks(self, chunks: list[RagChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings length mismatch")
        if not chunks:
            return
        self._collection.upsert(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            embeddings=embeddings,
            metadatas=[_filterable_metadata(chunk) for chunk in chunks],
        )

    def query(self, embedding: list[float], top_k: int) -> list[dict[str, object]]:
        result = self._collection.query(query_embeddings=[embedding], n_results=top_k)
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        rows: list[dict[str, object]] = []
        for idx, chunk_id in enumerate(ids):
            rows.append(
                {
                    "chunk_id": chunk_id,
                    "score": distances[idx] if idx < len(distances) else None,
                    "metadata": metadatas[idx] if idx < len(metadatas) else {},
                    "text": documents[idx] if idx < len(documents) else "",
                }
            )
        return rows

    def get_embeddings(self, ids: list[str]) -> dict[str, list[float]]:
        result = self._collection.get(ids=ids, include=["embeddings"])
        result_ids = result.get("ids", [])
        embeddings = result.get("embeddings", [])
        return {str(result_ids[i]): list(embeddings[i]) for i in range(len(result_ids))}


def _filterable_metadata(chunk: RagChunk) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source": chunk.source,
        "chunk_type": chunk.chunk_type,
        "tags": ";".join(chunk.tags),
    }
    for field in ("cr", "spell_level", "project_id"):
        if field in chunk.metadata and chunk.metadata[field] is not None:
            metadata[field] = chunk.metadata[field]
    return metadata


async def upsert_chunks_sqlite(session: AsyncSession, chunks: list[RagChunk]) -> None:
    table = RagChunkModel.__table__
    for chunk in chunks:
        stmt = sqlite_insert(table).values(
            id=chunk.id,
            project_id=chunk.metadata.get("project_id"),
            source_id=chunk.metadata.get("source_id"),
            source=chunk.source,
            source_ref=chunk.source_ref,
            canon_level=chunk.canon_level,
            source_title=chunk.source_title,
            chunk_type=chunk.chunk_type,
            title=chunk.title,
            section_path=chunk.section_path,
            tags=chunk.tags,
            metadata=chunk.metadata,
            chunk_text=chunk.text,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "project_id": chunk.metadata.get("project_id"),
                "source_id": chunk.metadata.get("source_id"),
                "source": chunk.source,
                "source_ref": chunk.source_ref,
                "canon_level": chunk.canon_level,
                "source_title": chunk.source_title,
                "chunk_type": chunk.chunk_type,
                "title": chunk.title,
                "section_path": chunk.section_path,
                "tags": chunk.tags,
                "metadata": chunk.metadata,
                "chunk_text": chunk.text,
            },
        )
        await session.execute(stmt)


async def existing_chunk_ids(session: AsyncSession, chunk_ids: list[str]) -> set[str]:
    if not chunk_ids:
        return set()
    result = await session.execute(select(RagChunkModel.id).where(RagChunkModel.id.in_(chunk_ids)))
    return {row[0] for row in result.all()}
