from __future__ import annotations

from services.rag.chunkers import BaseChunker, register
from services.rag.schemas import RagChunk, RawSrdRecord


def _expand_entry(item: object) -> str:
    if isinstance(item, dict):
        name = item.get("name", "")
        desc = item.get("desc", "")
        if isinstance(desc, list):
            desc = " ".join(str(d) for d in desc)
        return f"{name}: {desc}" if desc else str(name)
    return str(item or "")


def _as_text(value: object) -> str:
    if isinstance(value, list):
        return "; ".join(_expand_entry(item) for item in value if item)
    return str(value or "")


@register("monsters")
class MonsterChunker(BaseChunker):
    def chunk(self, record: RawSrdRecord) -> RagChunk:
        raw = record.raw_json
        actions = _as_text(raw.get("actions"))
        specials = _as_text(raw.get("special_abilities"))
        cr = str(raw.get("challenge_rating") or raw.get("cr") or "")
        ac = raw.get("armor_class")
        hp = raw.get("hit_points")
        text = (
            f"{record.name}. CR {cr}. Size {raw.get('size', '')}. Type {raw.get('type', '')}. "
            f"AC {ac}. HP {hp}. Actions: {actions}. Special abilities: {specials}."
        ).strip()
        return RagChunk(
            id=f"{record.file_name}#{record.index}",
            source=record.source,
            source_title=record.file_name,
            chunk_type="monster_statblock",
            title=record.name,
            tags=[],
            text=text,
            metadata={"cr": cr, "ac": ac, "hp": hp},
            canon_level="hard",
            source_ref=f"{record.file_name}#{record.index}",
        )
