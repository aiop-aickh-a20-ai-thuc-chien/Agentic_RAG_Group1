"""URL-specific Chunk mapping with shared ingestion chunking helpers."""

from __future__ import annotations

import re
import unicodedata

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
    "is_usable_chunk_text",
    "normalize_for_content_hash",
    "normalize_for_dedupe_hash",
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
    fetched_at: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    chunk_id_prefix: str | None = None,
) -> list[Chunk]:
    """Build shared Chunk objects from normalized Markdown/text."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size.")

    chunks: list[Chunk] = []
    normalized_full_text = normalize_for_content_hash(text)
    page_hash = short_hash(normalized_full_text)
    text_chunks = split_markdown_paragraphs(
        text,
        max_tokens=chunk_size,
        overlap_paragraphs=chunk_overlap,
    )
    chunk_part_total = len(text_chunks)
    id_prefix = chunk_id_prefix or source_type
    for index, chunk_text in enumerate(text_chunks, start=1):
        chunk_id = build_chunk_id(id_prefix, source, section, index)
        normalized_chunk_text = normalize_for_content_hash(chunk_text)
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
                    "fetched_at": fetched_at,
                    "updated_date": fetched_at,
                    "updated_date_source": "ingestion_start",
                    "page_hash": page_hash,
                    "content_hash": short_hash(normalized_chunk_text),
                    "dedupe_hash": short_hash(normalize_for_dedupe_hash(chunk_text)),
                    "normalized_text": normalized_chunk_text,
                    "chunk_part_index": index,
                    "chunk_part_total": chunk_part_total,
                },
            )
        )
    return chunks


def normalize_for_content_hash(value: str) -> str:
    """Normalize text for stable per-chunk content hashing."""

    return normalize_space(unicodedata.normalize("NFKC", value)).casefold()


def normalize_for_dedupe_hash(value: str) -> str:
    """Normalize text more aggressively for duplicate-detection blocking."""

    text = normalize_for_content_hash(value)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[\u200b\u200c\u200d]", "", text)
    return normalize_space(text)


def is_usable_chunk_text(text: str) -> bool:
    """Return whether chunk text has enough signal for review/retrieval."""

    normalized = normalize_space(text)
    if not normalized:
        return False
    words = re.findall(r"\w+", normalized, flags=re.UNICODE)
    if len(words) < 8:
        return False
    alpha_chars = sum(1 for char in normalized if char.isalpha())
    return alpha_chars >= 20
