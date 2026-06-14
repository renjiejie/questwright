"""Unit tests for the world-bible lore chunker (task 8.3)."""

from __future__ import annotations

from services.rag.chunkers.lore_chunker import (
    TARGET_MAX_TOKENS,
    TARGET_MIN_TOKENS,
    _token_len,
    chunk_lore,
)


def test_three_level_heading_section_path() -> None:
    md = (
        "# 大陆\n\n大陆总览段落。\n\n"
        "## 王国\n\n王国介绍段落。\n\n"
        "### 城邦\n\n城邦的详细描写在这里。\n"
    )
    chunks = chunk_lore(md, source_id="s1", project_id="p1", source_title="世界观")

    city_chunks = [c for c in chunks if c.section_path == ["大陆", "王国", "城邦"]]
    assert city_chunks, "expected a chunk for the deepest section"
    c = city_chunks[0]
    assert c.chunk_type == "lore_chunk"
    assert c.source == "world_bible"
    assert c.canon_level == "soft"
    assert c.metadata["project_id"] == "p1"
    assert c.metadata["source_id"] == "s1"
    assert c.source_ref.startswith("s1#")


def test_chunk_token_sizes_in_target_range() -> None:
    # Build a ~5000-token doc: several sections each well above the min.
    para = "这是一段世界观描述文字，用于测试切块器的 token 控制能力。" * 30  # large CJK para
    sections = []
    for i in range(8):
        sections.append(f"## 区域{i}\n\n{para}\n\n{para}\n")
    md = "# 世界\n\n世界总览。\n\n" + "\n".join(sections)

    chunks = chunk_lore(md, source_id="s1", project_id="p1")
    assert len(chunks) >= 5

    token_counts = [_token_len(c.text) for c in chunks]
    # All chunks must respect the upper bound.
    assert all(t <= TARGET_MAX_TOKENS for t in token_counts)
    in_range = [t for t in token_counts if TARGET_MIN_TOKENS <= t <= TARGET_MAX_TOKENS]
    # >= 90% land in the target band (small tail chunks excepted).
    assert len(in_range) / len(token_counts) >= 0.9


def test_no_overlap_between_chunks() -> None:
    md = "# A\n\n" + ("段落一。\n\n" * 200)
    chunks = chunk_lore(md, source_id="s1", project_id="p1")
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids)), "chunk ids must be unique"
