from __future__ import annotations

from services.rag.chunkers import BaseChunker, register
from services.rag.schemas import RagChunk, RawSrdRecord


def _as_text(value: object) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item)
    return str(value or "")


@register(
    "conditions",
    "damage-types",
    "magic-items",
    "magic-schools",
    "equipment",
    "equipment-categories",
    "alignments",
    "weapon-properties",
)
class MiscChunker(BaseChunker):
    def chunk(self, record: RawSrdRecord) -> RagChunk:
        raw = record.raw_json
        desc = _as_text(raw.get("desc"))
        text = f"{record.name}. {desc}".strip()
        return RagChunk(
            id=f"{record.file_name}#{record.index}",
            source=record.source,
            source_title=record.file_name,
            chunk_type="misc_chunk",
            title=record.name,
            tags=[],
            text=text,
            metadata={"category": record.category},
            canon_level="hard",
            source_ref=f"{record.file_name}#{record.index}",
        )
