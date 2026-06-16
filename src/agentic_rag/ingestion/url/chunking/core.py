"""URL-specific Chunk mapping with shared ingestion chunking helpers."""

from __future__ import annotations

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.chunking import (
    DEFAULT_PARAGRAPH_MAX_TOKENS as SHARED_PARAGRAPH_MAX_TOKENS,
)
from agentic_rag.ingestion.chunking import (
    DEFAULT_PARAGRAPH_OVERLAP as SHARED_PARAGRAPH_OVERLAP,
)
from agentic_rag.ingestion.chunking import (
    build_chunk_id,
    detect_lang,
    normalize_space,
    paragraph_chunk,
    short_hash,
    slugify,
    split_markdown,
    split_markdown_paragraphs,
    split_sentences,
)

DEFAULT_CHUNK_SIZE = SHARED_PARAGRAPH_MAX_TOKENS
DEFAULT_CHUNK_OVERLAP = SHARED_PARAGRAPH_OVERLAP
DEFAULT_PARAGRAPH_MAX_TOKENS = SHARED_PARAGRAPH_MAX_TOKENS
DEFAULT_PARAGRAPH_OVERLAP = SHARED_PARAGRAPH_OVERLAP

__all__ = [
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_PARAGRAPH_MAX_TOKENS",
    "DEFAULT_PARAGRAPH_OVERLAP",
    "build_chunk_id",
    "build_chunks",
    "detect_lang",
    "normalize_space",
    "paragraph_chunk",
    "short_hash",
    "slugify",
    "split_markdown",
    "split_markdown_paragraphs",
    "split_sentences",
]


def build_chunks(
    *,
    text: str,
    source: str,
    source_type: str,
    section: str,
    url: str | None,
    title: str | None,
    ingestion_at: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Build shared Chunk objects from normalized Markdown/text."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size.")

    chunks: list[Chunk] = []
    content_hash = short_hash(text)
    text_chunks = split_markdown_paragraphs(
        text,
        max_tokens=chunk_size,
        overlap_paragraphs=chunk_overlap,
    )
    chunk_part_total = len(text_chunks)
    for index, chunk_text in enumerate(text_chunks, start=1):
        chunk_id = build_chunk_id(source_type, source, section, index)
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                text=chunk_text,
                metadata={
                    "chunk_id": chunk_id,
                    "source": source,
                    "source_type": source_type,
                    "url": url,
                    "section": section,
                    "title": title,
                    "ingestion_at": ingestion_at,
                    "chunk_index": index,
                    "content_hash": content_hash,
                    "chunk_part_index": index,
                    "chunk_part_total": chunk_part_total,
                },
            )
        )
    return chunks
