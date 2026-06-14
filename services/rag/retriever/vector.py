"""Vector retriever over the Chroma ``dnd_rag`` collection."""

from __future__ import annotations

from services.rag.embed import embed_texts
from services.rag.index import ChromaIndex
from services.rag.retriever.filters import (
    RetrievalFilters,
    build_chroma_where,
    passes_post_filter,
)


class VectorRetriever:
    def __init__(self, index: ChromaIndex) -> None:
        self._index = index

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 20,
        filters: RetrievalFilters | None = None,
    ) -> list[dict[str, object]]:
        filters = filters or RetrievalFilters()
        query_embedding = (await embed_texts([query], batch_size=1))[0]
        where = build_chroma_where(filters)
        # Over-fetch so post-filtering (project isolation, tags) still yields top_k.
        rows = self._index.query_where(query_embedding, top_k=top_k * 3, where=where)

        results: list[dict[str, object]] = []
        for row in rows:
            metadata = row.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}
            if not passes_post_filter(metadata, filters):
                continue
            distance = row.get("score")
            # Chroma returns L2/cosine *distance*; convert to a similarity score.
            score = 1.0 / (1.0 + float(distance)) if distance is not None else 0.0
            results.append(
                {
                    "chunk_id": row["chunk_id"],
                    "score": score,
                    "metadata": metadata,
                    "text": row.get("text", ""),
                }
            )
            if len(results) >= top_k:
                break
        return results
