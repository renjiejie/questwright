"""Integration tests: upload -> ingest -> retrieve (tasks 9.4, 11.4)."""

from __future__ import annotations

import hashlib

import pytest


def _fake_vector(text: str, dim: int = 8) -> list[float]:
    h = hashlib.sha256(text.encode("utf-8")).digest()
    return [b / 255.0 for b in h[:dim]]


@pytest.fixture
def patch_embedding(monkeypatch):
    async def fake_embed_texts(texts, batch_size, provider=None):
        return [_fake_vector(t) for t in texts]

    # ingest imports embed_texts lazily; vector retriever binds it at import time.
    monkeypatch.setattr("services.rag.embed.embed_texts", fake_embed_texts)
    monkeypatch.setattr("services.rag.retriever.vector.embed_texts", fake_embed_texts)
    return fake_embed_texts


SAMPLE_MD = """# 北境大陆

广袤的北境大陆被冰雪覆盖。

## 龙巢王国

龙巢王国由古龙守护。

### 火龙城

火龙城是龙巢王国的首都，红龙盘踞于此。red dragon lairs here.
"""


def _upload(client, project_id: str, content: bytes, name: str = "world.md"):
    return client.post(
        f"/projects/{project_id}/sources",
        files={"file": (name, content, "text/markdown")},
    )


def test_upload_ingest_retrieve_roundtrip(client, patch_embedding) -> None:
    up = _upload(client, "p1", SAMPLE_MD.encode("utf-8"))
    assert up.status_code == 201, up.text
    source_id = up.json()["source_id"]

    ingest = client.post(f"/projects/p1/sources/{source_id}/ingest")
    assert ingest.status_code == 202, ingest.text
    assert ingest.json()["status"] == "pending"

    # TestClient runs BackgroundTasks synchronously, so status is terminal now.
    status = client.get(f"/projects/p1/sources/{source_id}").json()
    assert status["status"] == "indexed", status

    # Retrieve recalls the lore.
    resp = client.post("/projects/p1/retrieve", json={"query": "red dragon", "top_k": 5})
    assert resp.status_code == 200, resp.text
    results = resp.json()
    assert results, "expected at least one hit"
    assert any(r["source"] == "world_bible" for r in results)
    # Scores monotonic non-increasing.
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_ingest_corrupt_content_marks_failed(client, patch_embedding) -> None:
    # Empty file -> parser yields empty markdown -> failure path.
    up = _upload(client, "p1", b"", name="empty.md")
    assert up.status_code == 201
    source_id = up.json()["source_id"]

    client.post(f"/projects/p1/sources/{source_id}/ingest")
    status = client.get(f"/projects/p1/sources/{source_id}").json()
    assert status["status"] == "failed"
    assert status["last_error"]


def test_retrieve_empty_query_422(client) -> None:
    resp = client.post("/projects/p1/retrieve", json={"query": "   "})
    assert resp.status_code == 422


def test_retrieve_missing_query_422(client) -> None:
    resp = client.post("/projects/p1/retrieve", json={"top_k": 5})
    assert resp.status_code == 422


def test_retrieve_invalid_project_id_422(client) -> None:
    resp = client.post("/projects/bad id/retrieve", json={"query": "dragon"})
    assert resp.status_code == 422


def test_retrieve_top_k_truncates(client, patch_embedding) -> None:
    up = _upload(client, "p1", SAMPLE_MD.encode("utf-8"))
    source_id = up.json()["source_id"]
    client.post(f"/projects/p1/sources/{source_id}/ingest")

    resp = client.post("/projects/p1/retrieve", json={"query": "龙", "top_k": 1})
    assert resp.status_code == 200
    assert len(resp.json()) <= 1


def test_cross_project_isolation(client, patch_embedding) -> None:
    a = _upload(client, "pA", b"# Alpha\n\nalpha lore secret AAA\n", "a.md")
    b = _upload(client, "pB", b"# Beta\n\nbeta lore secret BBB\n", "b.md")
    sa, sb = a.json()["source_id"], b.json()["source_id"]
    client.post(f"/projects/pA/sources/{sa}/ingest")
    client.post(f"/projects/pB/sources/{sb}/ingest")

    res_a = client.post("/projects/pA/retrieve", json={"query": "lore secret", "top_k": 20}).json()
    ids_a = {r["chunk_id"] for r in res_a}
    assert any(cid.startswith(sa) for cid in ids_a)
    assert not any(cid.startswith(sb) for cid in ids_a), "pA must not see pB's lore"
