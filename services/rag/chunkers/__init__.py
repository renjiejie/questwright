"""SRD chunker registry and dispatch utilities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from services.rag.schemas import RagChunk, RawSrdRecord

_CATEGORY_CHUNKERS: dict[str, BaseChunker] = {}


class BaseChunker(ABC):
    @abstractmethod
    def chunk(self, record: RawSrdRecord) -> RagChunk: ...


def register(*categories: str) -> Callable[[type[BaseChunker]], type[BaseChunker]]:
    def _decorator(chunker_cls: type[BaseChunker]) -> type[BaseChunker]:
        chunker = chunker_cls()
        for category in categories:
            _CATEGORY_CHUNKERS[category] = chunker
        return chunker_cls

    return _decorator


def get_chunker(category: str) -> BaseChunker:
    if category not in _CATEGORY_CHUNKERS:
        raise ValueError(f"No chunker registered for category: {category}")
    return _CATEGORY_CHUNKERS[category]


def chunk_record(record: RawSrdRecord) -> RagChunk:
    return get_chunker(record.category).chunk(record)


from services.rag.chunkers import (  # noqa: E402,F401
    class_race_feature_chunker,
    misc_chunker,
    monster_chunker,
    rule_chunker,
    spell_chunker,
)
