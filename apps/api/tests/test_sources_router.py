"""Integration tests for the sources upload router (tasks 7.5)."""

from __future__ import annotations

from pathlib import Path


def test_upload_markdown_succeeds(client, test_settings) -> None:
    resp = client.post(
        "/projects/p1/sources",
        files={"file": ("world.md", b"# Hello\n\nworld bible content", "text/markdown")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "uploaded"
    assert body["source_id"].startswith("source_")
    assert body["kind"] == "world_bible"

    # File landed on disk under the project dir.
    upload_dir = Path(test_settings.UPLOAD_DIR) / "p1"
    files = list(upload_dir.glob(f"{body['source_id']}__*"))
    assert len(files) == 1

    # Status is pollable.
    get_resp = client.get(f"/projects/p1/sources/{body['source_id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "uploaded"


def test_upload_non_markdown_rejected_415(client, test_settings) -> None:
    resp = client.post(
        "/projects/p1/sources",
        files={
            "file": (
                "doc.docx",
                b"PK\x03\x04binary",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert resp.status_code == 415
    assert "Markdown" in resp.json()["detail"]
    # Nothing written to disk.
    upload_dir = Path(test_settings.UPLOAD_DIR) / "p1"
    assert not upload_dir.exists() or not list(upload_dir.iterdir())


def test_upload_too_large_rejected_413(client, test_settings, monkeypatch) -> None:
    # Shrink the limit so we don't have to send 21MB.
    monkeypatch.setattr(test_settings, "MAX_UPLOAD_BYTES", 16)
    resp = client.post(
        "/projects/p1/sources",
        files={"file": ("big.md", b"x" * 64, "text/markdown")},
    )
    assert resp.status_code == 413


def test_invalid_project_id_rejected_422(client) -> None:
    resp = client.post(
        "/projects/bad id with spaces/sources",
        files={"file": ("world.md", b"# Hi", "text/markdown")},
    )
    assert resp.status_code == 422
