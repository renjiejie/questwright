"""Hybrid retrieval package.

Exposes the retriever building blocks and a process-wide BM25 singleton that
is initialized in the FastAPI lifespan and refreshed incrementally on ingest.
"""

from __future__ import annotations

from .bm25 import BM25Retriever
from .filters import RetrievalFilters, build_chroma_where, passes_post_filter
from .hybrid import Candidate, HybridRetriever
from .reranker import NoOpReranker, Reranker
from .vector import VectorRetriever

__all__ = [
    "BM25Retriever",
    "Candidate",
    "HybridRetriever",
    "NoOpReranker",
    "Reranker",
    "RetrievalFilters",
    "VectorRetriever",
    "build_chroma_where",
    "passes_post_filter",
    "get_bm25_retriever",
    "set_bm25_retriever",
]

_bm25_retriever: BM25Retriever | None = None


def get_bm25_retriever() -> BM25Retriever | None:
    return _bm25_retriever


def set_bm25_retriever(retriever: BM25Retriever | None) -> None:
    global _bm25_retriever
    _bm25_retriever = retriever
