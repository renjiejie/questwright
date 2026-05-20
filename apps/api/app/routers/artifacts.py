"""Artifact CRUD router.

Endpoints (Phase 0):
- POST   /artifacts             — create v1
- GET    /artifacts/{id}        — read one
- POST   /artifacts/{id}/revise — fork a new version (parent_id wired)
- GET    /artifacts             — list by run_id

Enforces the never-modify invariant by exposing only create + revise; no PATCH.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from services.db.models import Artifact
from services.db.repositories import ArtifactNotFound, ArtifactRepository


router = APIRouter(prefix="/artifacts", tags=["artifacts"])


class ArtifactCreate(BaseModel):
    project_id: str
    run_id: str
    stage: str
    content_json: dict[str, Any]
    title: str | None = None
    model: str | None = None
    prompt_hash: str | None = None
    input_context_ids: list[str] | None = None
    status: str = Field(default="pending_human_review")


class ArtifactRevise(BaseModel):
    content_json: dict[str, Any]
    title: str | None = None
    model: str | None = None
    prompt_hash: str | None = None
    input_context_ids: list[str] | None = None
    status: str = Field(default="pending_human_review")


class ArtifactRead(BaseModel):
    id: str
    project_id: str
    run_id: str
    stage: str
    version: int
    parent_artifact_id: str | None
    status: str
    title: str | None
    content_json: dict[str, Any]
    model: str | None
    prompt_hash: str | None
    input_context_ids: list[str] | None
    created_at: datetime

    @classmethod
    def from_orm_obj(cls, obj: Artifact) -> "ArtifactRead":
        return cls(
            id=obj.id,
            project_id=obj.project_id,
            run_id=obj.run_id,
            stage=obj.stage,
            version=obj.version,
            parent_artifact_id=obj.parent_artifact_id,
            status=obj.status,
            title=obj.title,
            content_json=obj.content_json,
            model=obj.model,
            prompt_hash=obj.prompt_hash,
            input_context_ids=obj.input_context_ids,
            created_at=obj.created_at,
        )


@router.post("", response_model=ArtifactRead, status_code=201)
async def create_artifact(
    body: ArtifactCreate,
    session: AsyncSession = Depends(get_session),
) -> ArtifactRead:
    repo = ArtifactRepository(session)
    obj = await repo.create(**body.model_dump())
    return ArtifactRead.from_orm_obj(obj)


@router.get("/{artifact_id}", response_model=ArtifactRead)
async def get_artifact(
    artifact_id: str,
    session: AsyncSession = Depends(get_session),
) -> ArtifactRead:
    repo = ArtifactRepository(session)
    try:
        obj = await repo.get(artifact_id)
    except ArtifactNotFound:
        raise HTTPException(status_code=404, detail=f"artifact {artifact_id} not found") from None
    return ArtifactRead.from_orm_obj(obj)


@router.post("/{artifact_id}/revise", response_model=ArtifactRead, status_code=201)
async def revise_artifact(
    artifact_id: str,
    body: ArtifactRevise,
    session: AsyncSession = Depends(get_session),
) -> ArtifactRead:
    repo = ArtifactRepository(session)
    try:
        obj = await repo.revise(artifact_id, **body.model_dump())
    except ArtifactNotFound:
        raise HTTPException(status_code=404, detail=f"artifact {artifact_id} not found") from None
    return ArtifactRead.from_orm_obj(obj)


@router.get("", response_model=list[ArtifactRead])
async def list_artifacts(
    run_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[ArtifactRead]:
    repo = ArtifactRepository(session)
    items = await repo.list_for_run(run_id)
    return [ArtifactRead.from_orm_obj(o) for o in items]
