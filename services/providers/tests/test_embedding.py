"""Tests for EmbeddingProvider adapters."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from services.providers import EmbeddingProvider, OpenAIEmbedding


def _mock_client(vectors: list[list[float]]) -> MagicMock:
    response = SimpleNamespace(
        data=[SimpleNamespace(embedding=v) for v in vectors],
    )
    client = MagicMock()
    client.embeddings = MagicMock()
    client.embeddings.create = AsyncMock(return_value=response)
    return client


def test_openai_embedding_inheritance() -> None:
    assert issubclass(OpenAIEmbedding, EmbeddingProvider)
    assert OpenAIEmbedding.name == "openai"
    assert OpenAIEmbedding.dim == 1536


async def test_embed_batch() -> None:
    fake_vec1 = [0.1] * 1536
    fake_vec2 = [0.2] * 1536
    client = _mock_client([fake_vec1, fake_vec2])
    provider = OpenAIEmbedding(client=client)
    out = await provider.embed(["text a", "text b"])
    assert len(out) == 2
    assert len(out[0]) == 1536
    assert out[0][0] == 0.1
    assert out[1][0] == 0.2
    client.embeddings.create.assert_awaited_once()
    kwargs = client.embeddings.create.await_args.kwargs
    assert kwargs["model"] == "text-embedding-3-small"
    assert kwargs["input"] == ["text a", "text b"]


async def test_embed_empty_short_circuits() -> None:
    client = _mock_client([])
    provider = OpenAIEmbedding(client=client)
    out = await provider.embed([])
    assert out == []
    client.embeddings.create.assert_not_awaited()
