"""Document parsers for the world-bible ingest pipeline.

Parsers normalize an uploaded source file into clean, heading-preserving
Markdown. The `Parser` facade dispatches by `kind`; MVP ships Markdown only
(via Docling) and reserves PDF for a later patch.
"""

from __future__ import annotations

from .markdown_parser import MarkdownParser, Parser, ParseResult

__all__ = ["MarkdownParser", "Parser", "ParseResult"]
