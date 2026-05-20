"""LLM provider abstraction.

Business code should depend on `LLMProvider` and never import openai / deepseek
SDKs directly. Concrete providers live in this package and are picked by name
via the registry in `__init__.py`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class LLMResponse(BaseModel):
    """Normalized LLM response.

    `content` is provider-agnostic: when `response_schema` was passed to
    `generate()`, providers MUST return a parsed dict; otherwise a string.
    """

    content: Any
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    raw: dict[str, Any] | None = None


class LLMProvider(ABC):
    """Provider interface.

    Implementations are responsible for:
    - Calling the underlying API
    - Parsing JSON output when `response_schema` is supplied
    - Reporting token usage and rough cost
    """

    name: str  # subclass sets a stable identifier ("openai", "deepseek", ...)

    @abstractmethod
    async def generate(
        self,
        model: str,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...
