"""Embedding provider abstraction.

Kept separate from LLMProvider because embedding APIs use a different surface
(batch input, single-purpose output) and different pricing tiers. Business
code depends on `EmbeddingProvider`; concrete providers live alongside.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

from openai import AsyncOpenAI


class EmbeddingProvider(ABC):
    name: str
    dim: int  # output vector dimensionality (caller relies on this for Chroma init)

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedding(EmbeddingProvider):
    """`text-embedding-3-small`: dim=1536, ~$0.02 / 1M tokens."""

    name = "openai"
    dim = 1536

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
    ) -> None:
        if client is None:
            key = api_key or os.getenv("OPENAI_API_KEY", "")
            if not key:
                raise RuntimeError(
                    "OPENAI_API_KEY not set; pass api_key= or inject a mocked client"
                )
            client = AsyncOpenAI(api_key=key)
        self._client = client
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]
