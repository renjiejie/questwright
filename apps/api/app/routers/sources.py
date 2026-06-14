"""World-bible source upload + ingest status router.

Endpoints (Phase 1b):
- POST /projects/{project_id}/sources            — upload a Markdown source
- GET  /projects/{project_id}/sources/{id}       — poll ingest status
- POST /projects/{project_id}/sources/{id}/ingest — trigger async ingest

MVP accepts Markdown only (`.md` / `text/markdown`); other types -> 415.
Uploads above MAX_UPLOAD_BYTES -> 413. `project_id` is only format-checked
(soft-isolation key), never existence-checked.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.validation import is_valid_project_id
from services.db.models import Source
from services.db.repositories import SourceNotFound, SourceRepository

router = APIRouter(prefix="/projects/{project_id}/sources", tags=["sources"])

_MARKDOWN_MIME = {"text/markdown", "text/x-markdown"}


class SourceRead(BaseModel):
    source_id: str
    project_id: str
    kind: str
    original_filename: str
    mime_type: str | None
    byte_size: int
    status: str
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_obj(cls, obj: Source) -> SourceRead:
        return cls(
            source_id=obj.id,
            project_id=obj.project_id,
            kind=obj.kind,
            original_filename=obj.original_filename,
            mime_type=obj.mime_type,
            byte_size=obj.byte_size,
            status=obj.status,
            last_error=obj.last_error,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class IngestAccepted(BaseModel):
    task_id: str
    source_id: str
    status: str


def _validate_project_id(project_id: str) -> None:
    if not is_valid_project_id(project_id):
        raise HTTPException(
            status_code=422,
            detail="project_id must be 1-64 chars of [A-Za-z0-9_-]",
        )


def _is_markdown(file: UploadFile) -> bool:
    name = (file.filename or "").lower()
    if name.endswith(".md") or name.endswith(".markdown"):
        return True
    return (file.content_type or "") in _MARKDOWN_MIME


@router.post("", response_model=SourceRead, status_code=201)
async def upload_source(
    project_id: str,
    file: UploadFile = File(...),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> SourceRead:
    _validate_project_id(project_id)
    settings = get_settings()

    if not _is_markdown(file):
        raise HTTPException(
            status_code=415,
            detail="MVP only supports Markdown uploads (.md / text/markdown).",
        )

    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds MAX_UPLOAD_BYTES ({settings.MAX_UPLOAD_BYTES} bytes).",
        )

    repo = SourceRepository(session)
    source = await repo.create(
        project_id=project_id,
        kind="world_bible",
        original_filename=file.filename or "upload.md",
        mime_type=file.content_type,
        byte_size=len(data),
    )

    dest_dir = Path(settings.UPLOAD_DIR) / project_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{source.id}__{source.original_filename}"
    dest.write_bytes(data)

    return SourceRead.from_orm_obj(source)


@router.get("/{source_id}", response_model=SourceRead)
async def get_source(
    project_id: str,
    source_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> SourceRead:
    _validate_project_id(project_id)
    repo = SourceRepository(session)
    try:
        source = await repo.get(source_id)
    except SourceNotFound:
        raise HTTPException(status_code=404, detail=f"source {source_id} not found") from None
    if source.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"source {source_id} not found")
    return SourceRead.from_orm_obj(source)


@router.post("/{source_id}/ingest", response_model=IngestAccepted, status_code=202)
async def ingest_source_endpoint(
    project_id: str,
    source_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> IngestAccepted:
    _validate_project_id(project_id)
    repo = SourceRepository(session)
    try:
        source = await repo.get(source_id)
    except SourceNotFound:
        raise HTTPException(status_code=404, detail=f"source {source_id} not found") from None
    if source.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"source {source_id} not found")

    from services.rag.ingest import ingest_source

    task_id = f"ingest_{uuid.uuid4().hex[:16]}"
    background_tasks.add_task(ingest_source, source_id)
    return IngestAccepted(task_id=task_id, source_id=source_id, status="pending")
