"""Reranker interface (default no-op).

Reserved so a cross-encoder reranker (Cohere, bge-reranker, ...) can be slotted
in later without changing the hybrid retriever's call site.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Reranker(ABC):
    @abstractmethod
    async def rerank(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]: ...


class NoOpReranker(Reranker):
    async def rerank(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return candidates
