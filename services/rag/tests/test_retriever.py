"""Unit tests for hybrid retrieval building blocks (task 10.7)."""

from __future__ import annotations

import pytest

from services.rag.config import StageConfig
from services.rag.retriever.bm25 import BM25Retriever
from services.rag.retriever.filters import (
    RetrievalFilters,
    build_chroma_where,
    passes_post_filter,
)
from services.rag.retriever.hybrid import HybridRetriever
from services.rag.retriever.reranker import NoOpReranker, Reranker

# --- filters ---


def test_composite_filter_chroma_where() -> None:
    f = RetrievalFilters(source=["monster_manual"], cr_range=(5.0, 10.0))
    where = build_chroma_where(f)
    assert where == {
        "$and": [
            {"source": {"$in": ["monster_manual"]}},
            {"cr": {"$gte": 5.0}},
            {"cr": {"$lte": 10.0}},
        ]
    }


def test_post_filter_cr_range_and_source() -> None:
    f = RetrievalFilters(source=["monster_manual"], cr_range=(5.0, 10.0))
    assert passes_post_filter({"source": "monster_manual", "cr": 7}, f)
    assert not passes_post_filter({"source": "monster_manual", "cr": 2}, f)
    assert not passes_post_filter({"source": "phb", "cr": 7}, f)


def test_project_isolation_post_filter() -> None:
    f = RetrievalFilters(project_id="p1")
    # SRD chunk (no project) visible everywhere.
    assert passes_post_filter({"source": "phb"}, f)
    assert passes_post_filter({"project_id": None}, f)
    # Own project visible.
    assert passes_post_filter({"project_id": "p1"}, f)
    # Other project's lore hidden.
    assert not passes_post_filter({"project_id": "p2"}, f)


def test_tags_any_match() -> None:
    f = RetrievalFilters(tags=["fire"])
    assert passes_post_filter({"tags": ["fire", "dragon"]}, f)
    assert passes_post_filter({"tags": "fire;dragon"}, f)
    assert not passes_post_filter({"tags": ["ice"]}, f)


# --- BM25 ---


def test_bm25_add_remove_and_isolation() -> None:
    r = BM25Retriever()
    r.add_chunks(
        [
            ("srd-1", "grappled condition restrained", {"source": "phb", "project_id": None}),
            ("lore-a", "dragon lair in the north", {"source": "world_bible", "project_id": "p1"}),
            ("lore-b", "dragon hoard secret", {"source": "world_bible", "project_id": "p2"}),
        ]
    )
    # p1 sees SRD + its own lore, never p2's lore.
    hits = r.retrieve("dragon", top_k=10, filters=RetrievalFilters(project_id="p1"))
    ids = {h["chunk_id"] for h in hits}
    assert "lore-a" in ids
    assert "lore-b" not in ids

    # keyword recall for SRD.
    hits2 = r.retrieve("grappled", top_k=5, filters=RetrievalFilters(project_id="p1"))
    assert any(h["chunk_id"] == "srd-1" for h in hits2)

    # removal works without rebuild from scratch.
    r.remove_chunks(["lore-a"])
    hits3 = r.retrieve("dragon", top_k=10, filters=RetrievalFilters(project_id="p1"))
    assert "lore-a" not in {h["chunk_id"] for h in hits3}


# --- hybrid + stage weights + reranker ---


class _FakeVector:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def retrieve(self, query, *, top_k=20, filters=None):
        return self._rows


@pytest.mark.asyncio
async def test_stage_weights_change_ranking() -> None:
    vector_rows = [
        {"chunk_id": "lore", "score": 0.9, "metadata": {"source": "world_bible"}, "text": "lore"},
        {"chunk_id": "mm", "score": 0.85, "metadata": {"source": "monster_manual"}, "text": "mm"},
    ]
    bm25 = BM25Retriever()
    bm25.add_chunks(
        [
            ("lore", "lore text", {"source": "world_bible", "project_id": "p1"}),
            ("mm", "monster text", {"source": "monster_manual", "project_id": None}),
        ]
    )
    hybrid = HybridRetriever(_FakeVector(vector_rows), bm25)

    default_stage = StageConfig(
        vector_weight=0.6,
        bm25_weight=0.4,
        source_weights={"world_bible": 1.0, "monster_manual": 1.0},
    )
    audit_stage = StageConfig(
        vector_weight=0.5,
        bm25_weight=0.5,
        source_weights={"world_bible": 5.0, "monster_manual": 0.5},
    )

    out_default = await hybrid.retrieve(
        "x", top_k=2, filters=RetrievalFilters(project_id="p1"), stage_config=default_stage
    )
    out_audit = await hybrid.retrieve(
        "x", top_k=2, filters=RetrievalFilters(project_id="p1"), stage_config=audit_stage
    )
    # Under the audit stage, world_bible is boosted to the top.
    assert out_audit[0].chunk_id == "lore"
    # Scores are monotonic non-increasing.
    assert out_default[0].score >= out_default[-1].score


class _ReverseReranker(Reranker):
    async def rerank(self, query, candidates):
        return list(reversed(candidates))


@pytest.mark.asyncio
async def test_reranker_injection_effective() -> None:
    vector_rows = [
        {"chunk_id": "a", "score": 0.9, "metadata": {"source": "phb"}, "text": "a"},
        {"chunk_id": "b", "score": 0.1, "metadata": {"source": "phb"}, "text": "b"},
    ]
    stage = StageConfig(vector_weight=1.0, bm25_weight=0.0, source_weights={})

    noop = HybridRetriever(_FakeVector(vector_rows), None, NoOpReranker())
    out_noop = await noop.retrieve("x", top_k=2, stage_config=stage)
    assert out_noop[0].chunk_id == "a"

    rev = HybridRetriever(_FakeVector(vector_rows), None, _ReverseReranker())
    out_rev = await rev.retrieve("x", top_k=2, stage_config=stage)
    assert out_rev[0].chunk_id == "b"
