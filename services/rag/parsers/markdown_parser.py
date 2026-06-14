"""Markdown parsing via Docling.

Converts an uploaded Markdown file into normalized, heading-preserving
Markdown and writes the result to ``PARSED_DIR/{project_id}/{source_id}.md``.
The `Parser` facade dispatches by ``kind`` so PDF support can be added later
without touching callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParseResult:
    """Outcome of parsing one source file."""

    markdown: str
    parsed_path: Path


class MarkdownParser:
    """Parse Markdown into normalized Markdown using Docling."""

    def parse(self, raw_path: str | Path) -> str:
        from docling.document_converter import DocumentConverter

        raw_path = Path(raw_path)
        if not raw_path.exists():
            raise FileNotFoundError(f"source file not found: {raw_path}")

        converter = DocumentConverter()
        result = converter.convert(str(raw_path))
        markdown = result.document.export_to_markdown()
        if not markdown.strip():
            raise ValueError(f"parsed markdown is empty for {raw_path}")
        return markdown


class Parser:
    """Facade dispatching to a concrete parser by source ``kind``."""

    def __init__(self) -> None:
        self._markdown = MarkdownParser()

    def parse(
        self,
        *,
        kind: str,
        raw_path: str | Path,
        project_id: str,
        source_id: str,
        parsed_dir: str | Path,
    ) -> ParseResult:
        if kind == "world_bible":
            markdown = self._markdown.parse(raw_path)
        elif kind == "pdf":
            raise NotImplementedError("PDF parsing is not supported in MVP")
        else:
            raise ValueError(f"unsupported source kind: {kind}")

        dest_dir = Path(parsed_dir) / project_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        parsed_path = dest_dir / f"{source_id}.md"
        parsed_path.write_text(markdown, encoding="utf-8")
        return ParseResult(markdown=markdown, parsed_path=parsed_path)
