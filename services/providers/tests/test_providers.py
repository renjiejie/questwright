"""Tests for LLMProvider adapters.

We mock the AsyncOpenAI client at the SDK boundary so tests don't need a real
API key and don't hit the network.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.providers import DeepSeekProvider, LLMProvider, LLMResponse, OpenAIProvider


def _mock_client(content: str, prompt_tokens: int = 100, completion_tokens: int = 50) -> MagicMock:
    """Build an AsyncOpenAI-shaped mock returning `content`."""
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        model_dump=lambda: {"mocked": True},
    )
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


def test_inheritance() -> None:
    assert issubclass(OpenAIProvider, LLMProvider)
    assert issubclass(DeepSeekProvider, LLMProvider)
    assert OpenAIProvider.name == "openai"
    assert DeepSeekProvider.name == "deepseek"


async def test_openai_plain_text_call() -> None:
    client = _mock_client("hello world")
    provider = OpenAIProvider(client=client)
    resp = await provider.generate(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert isinstance(resp, LLMResponse)
    assert resp.content == "hello world"
    assert resp.input_tokens == 100
    assert resp.output_tokens == 50
    # gpt-4o-mini in price table → cost computed
    assert resp.cost_usd is not None and resp.cost_usd > 0
    client.chat.completions.create.assert_awaited_once()
    call_kwargs = client.chat.completions.create.await_args.kwargs
    assert "response_format" not in call_kwargs


async def test_openai_json_schema_call_parses_dict() -> None:
    client = _mock_client('{"title":"x","ok":true}')
    provider = OpenAIProvider(client=client)
    resp = await provider.generate(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "give json"}],
        response_schema={"type": "object"},
    )
    assert resp.content == {"title": "x", "ok": True}
    call_kwargs = client.chat.completions.create.await_args.kwargs
    assert call_kwargs["response_format"] == {"type": "json_object"}


async def test_openai_invalid_json_raises() -> None:
    client = _mock_client("not json")
    provider = OpenAIProvider(client=client)
    with pytest.raises(ValueError, match="non-JSON"):
        await provider.generate(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "x"}],
            response_schema={"type": "object"},
        )


async def test_openai_unknown_model_no_cost() -> None:
    client = _mock_client("hi")
    provider = OpenAIProvider(client=client)
    resp = await provider.generate(
        model="gpt-unknown",
        messages=[{"role": "user", "content": "x"}],
    )
    assert resp.cost_usd is None


async def test_deepseek_plain_text_call() -> None:
    client = _mock_client("audit report")
    provider = DeepSeekProvider(client=client)
    resp = await provider.generate(
        model="deepseek-chat",
        messages=[{"role": "system", "content": "audit"}, {"role": "user", "content": "x"}],
        temperature=0.1,
    )
    assert resp.content == "audit report"
    assert resp.input_tokens == 100
    call_kwargs = client.chat.completions.create.await_args.kwargs
    assert call_kwargs["temperature"] == 0.1


async def test_deepseek_json_schema_call() -> None:
    client = _mock_client('{"approved":true,"issues":[]}')
    provider = DeepSeekProvider(client=client)
    resp = await provider.generate(
        model="deepseek-reasoner",
        messages=[{"role": "user", "content": "audit this"}],
        response_schema={"type": "object"},
    )
    assert resp.content == {"approved": True, "issues": []}
    assert resp.cost_usd is not None and resp.cost_usd > 0
