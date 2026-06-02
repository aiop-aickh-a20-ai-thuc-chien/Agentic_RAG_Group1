"""PDF compatibility exports for shared ingestion chunking."""

from agentic_rag.ingestion.chunking import (
    MarkdownChunk,
    MarkdownSection,
    chunk_markdown,
    split_markdown_into_sections,
)

__all__ = [
    "MarkdownChunk",
    "MarkdownSection",
    "chunk_markdown",
    "split_markdown_into_sections",
]
