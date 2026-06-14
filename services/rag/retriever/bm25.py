"""In-memory BM25 retriever backed by SQLite ``rag_chunks``.

The index is built once at process startup from ``rag_chunks.chunk_text`` and
kept fresh incrementally via ``add_chunks`` / ``remove_chunks`` (no process
restart needed). Tokenization is whitespace + CJK-char split, which is crude
but adequate for keyword recall at MVP scale.
"""

from __future__ import annotations

import re
import time
from typing import Any

from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.db.models import RagChunk as RagChunkModel
from services.rag.retriever.filters import RetrievalFilters, passes_post_filter

_TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


class BM25Retriever:
    def __init__(self) -> None:
        self._chunk_ids: list[str] = []
        self._texts: dict[str, str] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._tokens: dict[str, list[str]] = {}
        self._bm25: BM25Okapi | None = None

    @classmethod
    async def from_sqlite(cls, session: AsyncSession) -> BM25Retriever:
        retriever = cls()
        start = time.perf_counter()
        result = await session.execute(
            select(
                RagChunkModel.id,
                RagChunkModel.chunk_text,
                RagChunkModel.source,
                RagChunkModel.chunk_type,
                RagChunkModel.project_id,
                RagChunkModel.tags,
                RagChunkModel.metadata_json,
            )
        )
        triples: list[tuple[str, str, dict[str, Any]]] = []
        for row in result.all():
            chunk_id, text, source, chunk_type, project_id, tags, meta = row
            metadata: dict[str, Any] = dict(meta or {})
            metadata.setdefault("source", source)
            metadata.setdefault("chunk_type", chunk_type)
            metadata.setdefault("project_id", project_id)
            metadata.setdefault("tags", tags or [])
            triples.append((chunk_id, text or "", metadata))
        retriever.add_chunks(triples)
        elapsed = time.perf_counter() - start
        retriever._build_elapsed = elapsed  # type: ignore[attr-defined]
        return retriever

    def _rebuild(self) -> None:
        if self._chunk_ids:
            corpus = [self._tokens[cid] for cid in self._chunk_ids]
            self._bm25 = BM25Okapi(corpus)
        else:
            self._bm25 = None

    def add_chunks(self, chunks: list[tuple[str, str, dict[str, Any]]]) -> None:
        for chunk_id, text, metadata in chunks:
            if chunk_id not in self._texts:
                self._chunk_ids.append(chunk_id)
            self._texts[chunk_id] = text
            self._metadata[chunk_id] = metadata
            self._tokens[chunk_id] = _tokenize(text)
        self._rebuild()

    def remove_chunks(self, chunk_ids: list[str]) -> None:
        removed = False
        for chunk_id in chunk_ids:
            if chunk_id in self._texts:
                self._chunk_ids.remove(chunk_id)
                del self._texts[chunk_id]
                del self._metadata[chunk_id]
                del self._tokens[chunk_id]
                removed = True
        if removed:
            self._rebuild()

    def __len__(self) -> int:
        return len(self._chunk_ids)

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 20,
        filters: RetrievalFilters | None = None,
    ) -> list[dict[str, object]]:
        filters = filters or RetrievalFilters()
        if self._bm25 is None or not self._chunk_ids:
            return []
        query_tokens = _tokenize(query)
        scores = self._bm25.get_scores(query_tokens)
        order = sorted(range(len(self._chunk_ids)), key=lambda i: scores[i], reverse=True)

        results: list[dict[str, object]] = []
        for idx in order:
            chunk_id = self._chunk_ids[idx]
            metadata = self._metadata.get(chunk_id, {})
            if not passes_post_filter(metadata, filters):
                continue
            results.append(
                {
                    "chunk_id": chunk_id,
                    "score": float(scores[idx]),
                    "metadata": metadata,
                    "text": self._texts.get(chunk_id, ""),
                }
            )
            if len(results) >= top_k:
                break
        return results
