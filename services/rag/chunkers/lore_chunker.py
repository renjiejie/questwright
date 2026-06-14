"""Heading-aware chunker for world-bible Markdown.

Splits normalized Markdown into `RagChunk`s along heading boundaries. Each
chunk carries the full `section_path` (root heading -> current section),
`chunk_type="lore_chunk"`, `source="world_bible"`, `canon_level="soft"`.
Chunks target 500-1000 tokens; sections above the ceiling are recursively
split on paragraph boundaries. No overlap (MVP).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from services.rag.schemas import RagChunk

TARGET_MIN_TOKENS = 500
TARGET_MAX_TOKENS = 1000

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_SLUG_RE = re.compile(r"[^\w一-鿿]+")


@lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def _token_len(text: str) -> int:
    """Approximate token count. Uses tiktoken when available."""
    enc = _encoder()
    if enc is not None:
        return len(enc.encode(text))
    # Rough fallback: ~4 chars/token.
    return max(1, len(text) // 4)


def _slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.strip().lower()).strip("-")
    return slug or "section"


@dataclass
class _Section:
    """A heading and the body text directly under it (before any child heading)."""

    path: list[str]
    body: str = ""
    paragraphs: list[str] = field(default_factory=list)


def _parse_sections(markdown: str) -> list[_Section]:
    """Walk markdown lines, grouping body text under its heading path."""
    sections: list[_Section] = []
    heading_stack: list[tuple[int, str]] = []  # (level, title)
    current: _Section | None = None
    buffer: list[str] = []

    def _flush() -> None:
        nonlocal current, buffer
        if current is not None:
            current.body = "\n".join(buffer).strip()
            sections.append(current)
        buffer = []

    for line in markdown.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            _flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            current = _Section(path=[t for _, t in heading_stack])
        else:
            if current is None:
                # Preamble before the first heading.
                current = _Section(path=[])
            buffer.append(line)
    _flush()
    return [s for s in sections if s.body or s.path]


def _split_paragraphs(body: str) -> list[str]:
    parts = re.split(r"\n\s*\n", body)
    return [p.strip() for p in parts if p.strip()]


def _pack_paragraphs(paragraphs: list[str]) -> list[str]:
    """Greedily pack paragraphs into <= TARGET_MAX_TOKENS pieces.

    Oversized single paragraphs are recursively split on sentence/newline.
    """
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        ptoks = _token_len(para)
        if ptoks > TARGET_MAX_TOKENS:
            if current:
                pieces.append("\n\n".join(current))
                current, current_tokens = [], 0
            pieces.extend(_split_oversized(para))
            continue
        if current_tokens + ptoks > TARGET_MAX_TOKENS and current:
            pieces.append("\n\n".join(current))
            current, current_tokens = [], 0
        current.append(para)
        current_tokens += ptoks

    if current:
        pieces.append("\n\n".join(current))
    return pieces


def _split_oversized(text: str) -> list[str]:
    """Recursively split a single oversized block to respect the token ceiling."""
    if _token_len(text) <= TARGET_MAX_TOKENS:
        return [text]
    # Split on sentence enders (CJK + latin), fall back to a hard midpoint.
    units = re.split(r"(?<=[。！？.!?])\s*", text)
    units = [u for u in units if u.strip()]
    if len(units) <= 1:
        mid = len(text) // 2
        return _split_oversized(text[:mid]) + _split_oversized(text[mid:])

    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for unit in units:
        utoks = _token_len(unit)
        if current_tokens + utoks > TARGET_MAX_TOKENS and current:
            pieces.append(" ".join(current).strip())
            current, current_tokens = [], 0
        current.append(unit)
        current_tokens += utoks
    if current:
        pieces.append(" ".join(current).strip())
    return pieces


def chunk_lore(
    markdown: str,
    *,
    source_id: str,
    project_id: str,
    source_title: str | None = None,
) -> list[RagChunk]:
    """Chunk world-bible markdown into RagChunks with heading-aware section paths."""
    sections = _parse_sections(markdown)
    chunks: list[RagChunk] = []
    seq = 0

    for section in sections:
        if not section.body:
            continue
        paragraphs = _split_paragraphs(section.body)
        pieces = _pack_paragraphs(paragraphs)
        section_slug = _slugify(section.path[-1]) if section.path else "root"
        title = section.path[-1] if section.path else None

        for piece in pieces:
            if not piece.strip():
                continue
            chunk_id = f"{source_id}#{section_slug}-{seq}"
            chunks.append(
                RagChunk(
                    id=chunk_id,
                    source="world_bible",
                    source_title=source_title,
                    chunk_type="lore_chunk",
                    title=title,
                    section_path=list(section.path),
                    tags=[],
                    text=piece,
                    metadata={"project_id": project_id, "source_id": source_id},
                    canon_level="soft",
                    source_ref=f"{source_id}#{section_slug}",
                )
            )
            seq += 1

    return chunks
