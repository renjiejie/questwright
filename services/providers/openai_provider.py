"""OpenAI implementation of LLMProvider.

Uses the async OpenAI SDK and the Chat Completions API. When
`response_schema` is supplied, we use `response_format={"type":"json_object"}`
and parse the model's JSON. Schema validation is the caller's responsibility
(see services/agents for Pydantic validation in node code).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from openai import AsyncOpenAI

from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


# Rough USD cost per 1K tokens. Updated when needed; not authoritative.
_COSTS = {
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4.1": (0.002, 0.008),
    "gpt-4.1-mini": (0.0004, 0.0016),
}


def _estimate_cost(model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    pricing = _COSTS.get(model)
    if pricing is None:
        return None
    in_rate, out_rate = pricing
    return (input_tokens / 1000) * in_rate + (output_tokens / 1000) * out_rate


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, client: AsyncOpenAI | None = None, api_key: str | None = None) -> None:
        if client is None:
            key = api_key or os.getenv("OPENAI_API_KEY", "")
            if not key:
                raise RuntimeError(
                    "OPENAI_API_KEY not set; pass api_key= or inject a mocked client"
                )
            client = AsyncOpenAI(api_key=key)
        self._client = client

    async def generate(
        self,
        model: str,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any] | None = None,
        temperature: float = 0.7,
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
            # Force JSON output. Caller validates against the schema.
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0].message.content or ""

        if response_schema is not None:
            try:
                content: Any = json.loads(choice)
            except json.JSONDecodeError as exc:
                raise ValueError(f"OpenAI returned non-JSON content: {choice[:200]}") from exc
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
