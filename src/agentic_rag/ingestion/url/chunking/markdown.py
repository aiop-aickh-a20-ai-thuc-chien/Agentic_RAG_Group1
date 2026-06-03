"""Compatibility exports for shared section-aware Markdown chunking."""

from agentic_rag.ingestion.chunking import (
    MarkdownChunk,
    MarkdownSection,
    chunk_markdown_by_sections,
    split_markdown_into_sections,
)

__all__ = [
    "MarkdownChunk",
    "MarkdownSection",
    "chunk_markdown_by_sections",
    "split_markdown_into_sections",
]
