"""End-to-end acceptance test using the real sample world bible (tasks 13.1-13.3).

Uses a deterministic fake embedding so it runs without API keys, but exercises
the full upload -> ingest -> indexed -> retrieve path against the committed
sample markdown, plus stage switching.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

SAMPLE = (
    Path(__file__).resolve().parents[3]
    / "openspec"
    / "changes"
    / "add-rag-world-bible-and-retrieval"
    / "examples"
    / "world_bible_sample.md"
)


def _fake_vector(text: str, dim: int = 8) -> list[float]:
    h = hashlib.sha256(text.encode("utf-8")).digest()
    return [b / 255.0 for b in h[:dim]]


@pytest.fixture
def patch_embedding(monkeypatch):
    async def fake_embed_texts(texts, batch_size, provider=None):
        return [_fake_vector(t) for t in texts]

    monkeypatch.setattr("services.rag.embed.embed_texts", fake_embed_texts)
    monkeypatch.setattr("services.rag.retriever.vector.embed_texts", fake_embed_texts)
    return fake_embed_texts


def test_sample_world_bible_e2e_and_stage_switch(client, patch_embedding) -> None:
    content = SAMPLE.read_bytes()
    up = client.post(
        "/projects/p1/sources",
        files={"file": ("world_bible_sample.md", content, "text/markdown")},
    )
    assert up.status_code == 201, up.text
    source_id = up.json()["source_id"]

    # 13.1: ingest reaches indexed.
    assert client.post(f"/projects/p1/sources/{source_id}/ingest").status_code == 202
    status = client.get(f"/projects/p1/sources/{source_id}").json()
    assert status["status"] == "indexed", status

    # 13.2: retrieve recalls lore; stage switch is accepted and returns results.
    default_hits = client.post(
        "/projects/p1/retrieve",
        json={"query": "燃焰议长 火山", "top_k": 8, "stage": "default"},
    )
    audit_hits = client.post(
        "/projects/p1/retrieve",
        json={"query": "燃焰议长 火山", "top_k": 8, "stage": "world_audit"},
    )
    assert default_hits.status_code == 200
    assert audit_hits.status_code == 200
    audit = audit_hits.json()
    assert audit, "expected lore hits"
    # world_audit boosts world_bible source weight -> top hit is world_bible.
    assert audit[0]["source"] == "world_bible"
    # section_path is preserved through ingest.
    assert any(r["section_path"] for r in audit)
