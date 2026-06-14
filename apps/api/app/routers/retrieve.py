"""Retrieve API router (Phase 1c).

POST /projects/{project_id}/retrieve
  body: {query, top_k?, stage?, filters?}

Runs hybrid retrieval (vector + BM25 + metadata filters, stage-weighted) with
mandatory project isolation, then hydrates full chunk fields from SQLite.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.validation import is_valid_project_id
from services.db.models import RagChunk as RagChunkModel
from services.rag.config import get_retrieval_config
from services.rag.index import ChromaIndex
from services.rag.retriever import (
    HybridRetriever,
    RetrievalFilters,
    VectorRetriever,
    get_bm25_retriever,
)

router = APIRouter(prefix="/projects/{project_id}/retrieve", tags=["retrieve"])


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=100)
    stage: str | None = None
    filters: dict[str, Any] | None = None

    @field_validator("query")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must be a non-empty string")
        return v


class RetrievedChunk(BaseModel):
    chunk_id: str
    score: float
    source: str | None
    source_title: str | None
    chunk_type: str | None
    title: str | None
    section_path: list[str] | None
    tags: list[str] | None
    text: str
    metadata: dict[str, Any] | None
    canon_level: str | None
    source_ref: str | None


@router.post("", response_model=list[RetrievedChunk])
async def retrieve_chunks(
    project_id: str,
    body: RetrieveRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[RetrievedChunk]:
    if not is_valid_project_id(project_id):
        raise HTTPException(
            status_code=422,
            detail="project_id must be 1-64 chars of [A-Za-z0-9_-]",
        )

    settings = get_settings()
    top_k = body.top_k or settings.RETRIEVAL_TOP_K

    try:
        filters = RetrievalFilters.from_request(body.filters, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    stage_config = get_retrieval_config().get_stage(body.stage)

    index = ChromaIndex(
        persist_path=settings.CHROMA_PATH,
        collection_name=settings.CHROMA_COLLECTION,
    )
    hybrid = HybridRetriever(VectorRetriever(index), get_bm25_retriever())
    candidates = await hybrid.retrieve(
        body.query, top_k=top_k, filters=filters, stage_config=stage_config
    )
    if not candidates:
        return []

    chunk_ids = [c.chunk_id for c in candidates]
    result = await session.execute(
        select(RagChunkModel).where(RagChunkModel.id.in_(chunk_ids))
    )
    db_rows = {row.id: row for row in result.scalars().all()}

    out: list[RetrievedChunk] = []
    for cand in candidates:
        row = db_rows.get(cand.chunk_id)
        meta = cand.metadata if isinstance(cand.metadata, dict) else {}
        out.append(
            RetrievedChunk(
                chunk_id=cand.chunk_id,
                score=cand.score,
                source=(row.source if row else meta.get("source")),
                source_title=(row.source_title if row else None),
                chunk_type=(row.chunk_type if row else meta.get("chunk_type")),
                title=(row.title if row else None),
                section_path=(row.section_path if row else None),
                tags=(row.tags if row else None),
                text=(row.chunk_text if row and row.chunk_text else cand.text),
                metadata=(row.metadata_json if row else meta),
                canon_level=(row.canon_level if row else None),
                source_ref=(row.source_ref if row else None),
            )
        )
    return out
