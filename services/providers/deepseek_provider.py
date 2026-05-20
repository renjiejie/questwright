"""DeepSeek implementation of LLMProvider.

DeepSeek exposes an OpenAI-compatible HTTP API, so we reuse the AsyncOpenAI
client and only swap base_url + key. This keeps the surface tiny and means we
get streaming / retries / etc. for free in future phases.
"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import AsyncOpenAI

from .base import LLMProvider, LLMResponse


_DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# DeepSeek pricing (USD per 1K tokens). Update as needed.
_COSTS = {
    "deepseek-chat": (0.00027, 0.0011),
    "deepseek-reasoner": (0.00055, 0.00219),
}


def _estimate_cost(model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    pricing = _COSTS.get(model)
    if pricing is None:
        return None
    in_rate, out_rate = pricing
    return (input_tokens / 1000) * in_rate + (output_tokens / 1000) * out_rate


class DeepSeekProvider(LLMProvider):
    name = "deepseek"

    def __init__(self, client: AsyncOpenAI | None = None, api_key: str | None = None) -> None:
        if client is None:
            key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
            if not key:
                raise RuntimeError(
                    "DEEPSEEK_API_KEY not set; pass api_key= or inject a mocked client"
                )
            client = AsyncOpenAI(api_key=key, base_url=_DEEPSEEK_BASE_URL)
        self._client = client

    async def generate(
        self,
        model: str,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if response_schema is not None:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0].message.content or ""

        if response_schema is not None:
            try:
                content: Any = json.loads(choice)
            except json.JSONDecodeError as exc:
                raise ValueError(f"DeepSeek returned non-JSON content: {choice[:200]}") from exc
        else:
            content = choice

        usage = response.usage
        in_tok = getattr(usage, "prompt_tokens", None) if usage else None
        out_tok = getattr(usage, "completion_tokens", None) if usage else None

        return LLMResponse(
            content=content,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=_estimate_cost(model, in_tok, out_tok),
            raw=response.model_dump() if hasattr(response, "model_dump") else None,
        )
