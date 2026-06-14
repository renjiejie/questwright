"""Hybrid retriever: merge vector + BM25 candidates with stage weighting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.rag.config import StageConfig
from services.rag.retriever.bm25 import BM25Retriever
from services.rag.retriever.filters import RetrievalFilters
from services.rag.retriever.reranker import NoOpReranker, Reranker
from services.rag.retriever.vector import VectorRetriever


@dataclass
class Candidate:
    chunk_id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    vector_score: float = 0.0
    bm25_score: float = 0.0


def _normalize(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Min-max normalize scores to [0, 1] keyed by chunk_id."""
    if not rows:
        return {}
    scores = [float(r["score"]) for r in rows]
    lo, hi = min(scores), max(scores)
    span = hi - lo
    out: dict[str, float] = {}
    for r in rows:
        s = float(r["score"])
        out[str(r["chunk_id"])] = (s - lo) / span if span > 0 else 1.0
    return out


class HybridRetriever:
    def __init__(
        self,
        vector: VectorRetriever,
        bm25: BM25Retriever | None,
        reranker: Reranker | None = None,
    ) -> None:
        self._vector = vector
        self._bm25 = bm25
        self._reranker = reranker or NoOpReranker()

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 8,
        filters: RetrievalFilters | None = None,
        stage_config: StageConfig,
        candidate_k: int = 20,
    ) -> list[Candidate]:
        filters = filters or RetrievalFilters()

        vector_rows = await self._vector.retrieve(query, top_k=candidate_k, filters=filters)
        bm25_rows = (
            self._bm25.retrieve(query, top_k=candidate_k, filters=filters)
            if self._bm25 is not None
            else []
        )

        vec_norm = _normalize(vector_rows)
        bm25_norm = _normalize(bm25_rows)

        merged: dict[str, Candidate] = {}
        for row in vector_rows:
            cid = str(row["chunk_id"])
            merged[cid] = Candidate(
                chunk_id=cid,
                score=0.0,
                metadata=row.get("metadata") or {},
                text=str(row.get("text", "")),
                vector_score=vec_norm.get(cid, 0.0),
            )
        for row in bm25_rows:
            cid = str(row["chunk_id"])
            if cid in merged:
                merged[cid].bm25_score = bm25_norm.get(cid, 0.0)
            else:
                merged[cid] = Candidate(
                    chunk_id=cid,
                    score=0.0,
                    metadata=row.get("metadata") or {},
                    text=str(row.get("text", "")),
                    bm25_score=bm25_norm.get(cid, 0.0),
                )

        for cand in merged.values():
            source = str(cand.metadata.get("source", ""))
            source_weight = stage_config.source_weights.get(source, 1.0)
            base = (
                stage_config.vector_weight * cand.vector_score
                + stage_config.bm25_weight * cand.bm25_score
            )
            cand.score = base * source_weight

        ordered = sorted(merged.values(), key=lambda c: c.score, reverse=True)

        reranked = await self._reranker.rerank(
            query,
            [
                {
                    "chunk_id": c.chunk_id,
                    "score": c.score,
                    "metadata": c.metadata,
                    "text": c.text,
                    "vector_score": c.vector_score,
                    "bm25_score": c.bm25_score,
                }
                for c in ordered
            ],
        )
        out = [
            Candidate(
                chunk_id=str(r["chunk_id"]),
                score=float(r["score"]),
                metadata=r.get("metadata") or {},
                text=str(r.get("text", "")),
                vector_score=float(r.get("vector_score", 0.0)),
                bm25_score=float(r.get("bm25_score", 0.0)),
            )
            for r in reranked
        ]
        return out[:top_k]
