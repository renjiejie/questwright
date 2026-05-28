from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from services.db.models import Base
from services.rag.embed import embed_texts
from services.rag.index import ChromaIndex, upsert_chunks_sqlite
from services.rag.schemas import RagChunk


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary failure")
        return [[float(i + 1), 0.0] for i in range(len(texts))]


@pytest.mark.asyncio
async def test_embed_texts_retries_and_succeeds() -> None:
    provider = FakeEmbeddingProvider()
    vectors = await embed_texts(["a", "b"], batch_size=2, provider=provider)
    assert provider.calls == 2
    assert vectors == [[1.0, 0.0], [2.0, 0.0]]


@pytest.mark.asyncio
async def test_reindex_twice_keeps_counts_and_overwrites_embedding(tmp_path: Path) -> None:
    db_path = tmp_path / "rag.db"
    sync_engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    async_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    chunks = [
        RagChunk(
            id="chunk-1",
            source="monster_manual",
            source_title="5e-SRD-Monsters.json",
            chunk_type="monster_statblock",
            title="Young Red Dragon",
            text="Young Red Dragon text",
            metadata={"cr": "10"},
            source_ref="5e-SRD-Monsters.json#young-red-dragon",
        ),
        RagChunk(
            id="chunk-2",
            source="phb",
            source_title="5e-SRD-Spells.json",
            chunk_type="spell_chunk",
            title="Fireball",
            text="Fireball text",
            metadata={"spell_level": 3},
            source_ref="5e-SRD-Spells.json#fireball",
        ),
    ]

    index = ChromaIndex(persist_path=tmp_path / "chroma", collection_name="test_rag")

    async with session_maker() as session:
        index.upsert_chunks(chunks, [[0.1, 0.1], [0.2, 0.2]])
        await upsert_chunks_sqlite(session, chunks)
        await session.commit()

    async with session_maker() as session:
        index.upsert_chunks(chunks, [[0.9, 0.9], [0.8, 0.8]])
        await upsert_chunks_sqlite(session, chunks)
        await session.commit()

    assert index.count() == 2
    embeddings = index.get_embeddings(["chunk-1", "chunk-2"])
    assert embeddings["chunk-1"][0] == pytest.approx(0.9)
    assert embeddings["chunk-2"][0] == pytest.approx(0.8)

    async with session_maker() as session:
        row_count = (await session.execute(text("SELECT COUNT(*) FROM rag_chunks"))).scalar_one()
    assert row_count == 2

    await async_engine.dispose()
