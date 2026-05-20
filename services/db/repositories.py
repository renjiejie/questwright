"""Repository for Artifact aggregate.

Encodes the **never modify, always fork** invariant from 实施方案 §9 / 设计草案 §9:

- `create()` makes a v1 with no parent.
- `revise()` reads an existing artifact, marks it `superseded`, then creates a
  new artifact whose `parent_artifact_id` points at the previous one and whose
  `version = previous + 1`.
- We never UPDATE an artifact's content_json after creation.

Only fields the caller controls are accepted; created_at, version, status are
managed here.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Artifact


def _new_id() -> str:
    return f"artifact_{uuid.uuid4().hex[:16]}"


class ArtifactNotFound(LookupError):
    pass


class ArtifactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, artifact_id: str) -> Artifact:
        obj = await self._session.get(Artifact, artifact_id)
        if obj is None:
            raise ArtifactNotFound(artifact_id)
        return obj

    async def list_for_run(self, run_id: str) -> list[Artifact]:
        stmt = select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        *,
        project_id: str,
        run_id: str,
        stage: str,
        content_json: dict[str, Any],
        title: str | None = None,
        model: str | None = None,
        prompt_hash: str | None = None,
        input_context_ids: list[str] | None = None,
        status: str = "pending_human_review",
    ) -> Artifact:
        artifact = Artifact(
            id=_new_id(),
            project_id=project_id,
            run_id=run_id,
            stage=stage,
            version=1,
            parent_artifact_id=None,
            status=status,
            title=title,
            content_json=content_json,
            model=model,
            prompt_hash=prompt_hash,
            input_context_ids=input_context_ids,
        )
        self._session.add(artifact)
        await self._session.flush()
        return artifact

    async def revise(
        self,
        previous_id: str,
        *,
        content_json: dict[str, Any],
        title: str | None = None,
        model: str | None = None,
        prompt_hash: str | None = None,
        input_context_ids: list[str] | None = None,
        status: str = "pending_human_review",
    ) -> Artifact:
        previous = await self.get(previous_id)
        previous.status = "superseded"

        new = Artifact(
            id=_new_id(),
            project_id=previous.project_id,
            run_id=previous.run_id,
            stage=previous.stage,
            version=previous.version + 1,
            parent_artifact_id=previous.id,
            status=status,
            title=title if title is not None else previous.title,
            content_json=content_json,
            model=model,
            prompt_hash=prompt_hash,
            input_context_ids=input_context_ids,
        )
        self._session.add(new)
        await self._session.flush()
        return new
