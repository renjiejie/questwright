from __future__ import annotations

from services.rag.chunkers import BaseChunker, register
from services.rag.schemas import RagChunk, RawSrdRecord


def _join_desc(value: object) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item)
    return str(value or "")


@register("spells")
class SpellChunker(BaseChunker):
    def chunk(self, record: RawSrdRecord) -> RagChunk:
        raw = record.raw_json
        level = raw.get("level")
        school = raw.get("school")
        text = (
            f"{record.name}. Level {level}. School {school}. Range {raw.get('range', '')}. "
            f"Components {raw.get('components', '')}. "
            f"Description: {_join_desc(raw.get('desc'))}. "
            f"Higher level: {_join_desc(raw.get('higher_level'))}."
        ).strip()
        return RagChunk(
            id=f"{record.file_name}#{record.index}",
            source=record.source,
            source_title=record.file_name,
            chunk_type="spell_chunk",
            title=record.name,
            tags=[],
            text=text,
            metadata={"spell_level": level, "school": school},
            canon_level="hard",
            source_ref=f"{record.file_name}#{record.index}",
        )
