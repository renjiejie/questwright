"""Tests for EmbeddingProvider adapters."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
    provider = OpenAIEmbedding(client=MagicMock(), dim=1536)
    assert provider.dim == 1536


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
    assert "dimensions" not in kwargs


async def test_embed_sends_dimensions_when_enabled() -> None:
    client = _mock_client([[0.1] * 1024])
    provider = OpenAIEmbedding(
        client=client,
        model="text-embedding-v4",
        dim=1024,
        send_dimensions=True,
    )
    await provider.embed(["text"])
    kwargs = client.embeddings.create.await_args.kwargs
    assert kwargs["model"] == "text-embedding-v4"
    assert kwargs["dimensions"] == 1024


async def test_embed_empty_short_circuits() -> None:
    client = _mock_client([])
    provider = OpenAIEmbedding(client=client)
    out = await provider.embed([])
    assert out == []
    client.embeddings.create.assert_not_awaited()


async def test_embed_accepts_dict_response_shape() -> None:
    client = MagicMock()
    client.embeddings = MagicMock()
    client.embeddings.create = AsyncMock(
        return_value={"data": [{"embedding": [0.3, 0.4]}]}
    )
    provider = OpenAIEmbedding(client=client)
    out = await provider.embed(["text"])
    assert out == [[0.3, 0.4]]


async def test_embed_accepts_json_string_response_shape() -> None:
    client = MagicMock()
    client.embeddings = MagicMock()
    client.embeddings.create = AsyncMock(
        return_value='{"data":[{"embedding":[0.5,0.6]}]}'
    )
    provider = OpenAIEmbedding(client=client)
    out = await provider.embed(["text"])
    assert out == [[0.5, 0.6]]


def test_embed_passes_base_url_to_client() -> None:
    with patch("services.providers.embedding.AsyncOpenAI") as mock_cls:
        OpenAIEmbedding(
            api_key="sk-test",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    mock_cls.assert_called_once_with(
        api_key="sk-test",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def test_embed_omits_base_url_when_unset() -> None:
    with patch("services.providers.embedding.AsyncOpenAI") as mock_cls:
        OpenAIEmbedding(api_key="sk-test")
    mock_cls.assert_called_once_with(api_key="sk-test")
