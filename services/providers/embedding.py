"""Embedding provider abstraction.

Kept separate from LLMProvider because embedding APIs use a different surface
(batch input, single-purpose output) and different pricing tiers. Business
code depends on `EmbeddingProvider`; concrete providers live alongside.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

from openai import AsyncOpenAI


class EmbeddingProvider(ABC):
    name: str
    dim: int  # output vector dimensionality (caller relies on this for Chroma init)

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedding(EmbeddingProvider):
    """OpenAI-compatible embedding adapter.

    Defaults target OpenAI's `text-embedding-3-small` (dim=1536). The same class
    works against any OpenAI-compatible gateway (Aliyun DashScope, Voyage's
    OpenAI-compat endpoint, etc.) by passing `base_url` and a model that
    accepts the `dimensions` parameter to project to a fixed output size.
    """

    name = "openai"

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "text-embedding-3-small",
        dim: int = 1536,
        send_dimensions: bool = False,
    ) -> None:
        if client is None:
            key = api_key or os.getenv("OPENAI_API_KEY", "")
            if not key:
                raise RuntimeError(
                    "Embedding API key not set; pass api_key= or inject a mocked client"
                )
            client_kwargs: dict[str, Any] = {"api_key": key}
            if base_url:
                client_kwargs["base_url"] = base_url
            client = AsyncOpenAI(**client_kwargs)
        self._client = client
        self._model = model
        self.dim = dim
        self._send_dimensions = send_dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        kwargs: dict[str, Any] = {"model": self._model, "input": texts}
        if self._send_dimensions:
            kwargs["dimensions"] = self.dim
        response = await self._client.embeddings.create(**kwargs)
        data = _extract_embedding_rows(response)
        return [_extract_embedding_vector(item) for item in data]


def _extract_embedding_rows(response: Any) -> list[Any]:
    if hasattr(response, "data"):
        data = response.data
    elif isinstance(response, dict):
        data = response.get("data")
    elif isinstance(response, str):
        try:
            decoded = json.loads(response)
        except json.JSONDecodeError as exc:
            raise TypeError(
                "Embedding response is a string but not valid JSON; "
                "check your OPENAI_BASE_URL gateway compatibility."
            ) from exc
        data = decoded.get("data") if isinstance(decoded, dict) else None
    else:
        data = None

    if not isinstance(data, list):
        raise TypeError(
            f"Embedding response has unexpected shape: {type(response).__name__}. "
            "Expected an object with `.data` or OpenAI-compatible JSON with `data` list."
        )
    return data


def _extract_embedding_vector(item: Any) -> list[float]:
    if hasattr(item, "embedding"):
        embedding = item.embedding
    elif isinstance(item, dict):
        embedding = item.get("embedding")
    else:
        embedding = None

    if not isinstance(embedding, list):
        raise TypeError("Embedding item missing `embedding` list.")
    return [float(v) for v in embedding]
