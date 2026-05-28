"""Embedding helpers for RAG pipelines."""

from __future__ import annotations

import asyncio

from services.providers.embedding import EmbeddingProvider, OpenAIEmbedding


def _default_provider() -> EmbeddingProvider:
    """Build the default embedding provider from app settings.

    Decoupled from the chat LLM so embedding can target a different vendor
    (e.g. Aliyun DashScope) than chat completions.
    """
    from app.config import get_settings

    settings = get_settings()
    return OpenAIEmbedding(
        api_key=settings.EMBEDDING_API_KEY or settings.OPENAI_API_KEY,
        base_url=settings.EMBEDDING_BASE_URL or None,
        model=settings.EMBEDDING_MODEL,
        dim=settings.EMBEDDING_DIM,
        send_dimensions=True,
    )


async def embed_texts(
    texts: list[str],
    batch_size: int,
    provider: EmbeddingProvider | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")

    embedding_provider = provider or _default_provider()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start : start + batch_size]
        vectors.extend(await _embed_with_retry(embedding_provider, chunk))
    return vectors


async def _embed_with_retry(provider: EmbeddingProvider, texts: list[str]) -> list[list[float]]:
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            return await provider.embed(texts)
        except Exception:
            if attempt == max_attempts - 1:
                raise
            await asyncio.sleep(0.5 * (2**attempt))
    return []
