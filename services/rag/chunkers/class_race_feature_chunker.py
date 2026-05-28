from __future__ import annotations

from services.rag.chunkers import BaseChunker, register
from services.rag.schemas import RagChunk, RawSrdRecord


def _flatten_desc(raw: dict) -> str:
    desc = raw.get("desc", [])
    if isinstance(desc, list):
        return "\n".join(str(item) for item in desc if item)
    return str(desc or "")


@register(
    "classes",
    "subclasses",
    "races",
    "subraces",
    "features",
    "traits",
    "feats",
    "backgrounds",
    "levels",
    "ability-scores",
    "skills",
    "proficiencies",
    "languages",
)
class ClassRaceFeatureChunker(BaseChunker):
    def chunk(self, record: RawSrdRecord) -> RagChunk:
        raw = record.raw_json
        desc_text = _flatten_desc(raw)
        text = f"{record.name}. Category {record.category}. {desc_text}".strip()
        return RagChunk(
            id=f"{record.file_name}#{record.index}",
            source=record.source,
            source_title=record.file_name,
            chunk_type=f"{record.category}_chunk",
            title=record.name,
            tags=[],
            text=text,
            metadata={"category": record.category},
            canon_level="hard",
            source_ref=f"{record.file_name}#{record.index}",
        )
