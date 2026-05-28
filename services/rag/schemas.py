"""Pydantic schemas shared by RAG ingestion/retrieval modules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RawSrdRecord(BaseModel):
    source: Literal["monster_manual", "phb", "dmg", "srd_misc"]
    file_name: str
    category: str
    index: str
    name: str
    raw_json: dict[str, Any] = Field(default_factory=dict)
    loaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RagChunk(BaseModel):
    id: str
    source: str
    source_title: str | None = None
    edition: str = "5e"
    chunk_type: str
    title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    canon_level: str = "hard"
    source_ref: str
