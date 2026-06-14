"""Metadata filter translation for hybrid retrieval.

A request's filter dict is translated into:
- a Chroma ``where`` clause for the fields Chroma can match natively
  (``source`` / ``chunk_type`` / ``cr_range``), and
- a post-filter applied to candidates from both paths for ``project_id`` and
  ``tags``.

``project_id`` isolation is enforced as a post-filter because Chroma cannot
express "key missing OR equals" in a single clause, and SRD chunks are indexed
without a ``project_id`` key. The rule: a candidate is visible when its
``project_id`` is empty (global SRD) OR equals the requested project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievalFilters:
    source: list[str] = field(default_factory=list)
    chunk_type: list[str] = field(default_factory=list)
    cr_range: tuple[float, float] | None = None
    tags: list[str] = field(default_factory=list)
    project_id: str | None = None

    @classmethod
    def from_request(
        cls, filters: dict[str, Any] | None, project_id: str | None
    ) -> RetrievalFilters:
        filters = filters or {}
        cr_range = filters.get("cr_range")
        parsed_cr: tuple[float, float] | None = None
        if cr_range is not None:
            if not (isinstance(cr_range, (list, tuple)) and len(cr_range) == 2):
                raise ValueError("cr_range must be [min, max]")
            parsed_cr = (float(cr_range[0]), float(cr_range[1]))
        return cls(
            source=list(filters.get("source") or []),
            chunk_type=list(filters.get("chunk_type") or []),
            cr_range=parsed_cr,
            tags=list(filters.get("tags") or []),
            project_id=project_id,
        )


def _cr_to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_chroma_where(filters: RetrievalFilters) -> dict[str, Any] | None:
    """Translate filters into a Chroma ``where`` clause (project_id/tags excluded)."""
    clauses: list[dict[str, Any]] = []
    if filters.source:
        clauses.append({"source": {"$in": filters.source}})
    if filters.chunk_type:
        clauses.append({"chunk_type": {"$in": filters.chunk_type}})
    if filters.cr_range is not None:
        lo, hi = filters.cr_range
        clauses.append({"cr": {"$gte": lo}})
        clauses.append({"cr": {"$lte": hi}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def passes_post_filter(metadata: dict[str, Any], filters: RetrievalFilters) -> bool:
    """Apply project isolation + tags + (for BM25) the full filter set."""
    # Project isolation: empty/missing project_id = global SRD, visible to all.
    meta_project = metadata.get("project_id")
    if filters.project_id is not None:
        if meta_project not in (None, "", filters.project_id):
            return False

    if filters.source and metadata.get("source") not in filters.source:
        return False
    if filters.chunk_type and metadata.get("chunk_type") not in filters.chunk_type:
        return False
    if filters.cr_range is not None:
        cr = _cr_to_float(metadata.get("cr"))
        lo, hi = filters.cr_range
        if cr is None or not (lo <= cr <= hi):
            return False
    if filters.tags:
        raw_tags = metadata.get("tags")
        if isinstance(raw_tags, str):
            chunk_tags = [t for t in raw_tags.split(";") if t]
        elif isinstance(raw_tags, list):
            chunk_tags = raw_tags
        else:
            chunk_tags = []
        if not set(filters.tags) & set(chunk_tags):
            return False
    return True
