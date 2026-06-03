"""Deterministic Markdown/text chunking for URL ingestion."""

from __future__ import annotations

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    TextChunkingStrategy,
    build_chunk_id,
    normalize_space,
    short_hash,
    slugify,
    split_markdown,
    split_text_with_strategy,
)

__all__ = [
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_SIZE",
    "TextChunkingStrategy",
    "build_chunk_id",
    "build_chunks",
    "normalize_space",
    "short_hash",
    "slugify",
    "split_markdown",
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
    chunking_strategy: TextChunkingStrategy | None = None,
) -> list[Chunk]:
    """Build shared Chunk objects from normalized Markdown/text."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size.")

    chunks: list[Chunk] = []
    content_hash = short_hash(text)
    text_chunks = split_text_with_strategy(
        text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        chunking_strategy=chunking_strategy,
    )
    for index, chunk_text in enumerate(text_chunks, start=1):
        chunks.append(
            Chunk(
                chunk_id=build_chunk_id(source_type, source, section, index),
                text=chunk_text,
                metadata={
                    "source": source,
                    "source_type": source_type,
                    "file_name": None,
                    "url": url,
                    "page": None,
                    "section": section,
                    "title": title,
                    "fetched_at": fetched_at,
                    "content_hash": content_hash,
                    "chunk_index": index,
                    "chunking_method": _chunking_method(chunking_strategy),
                    "chunking_provider": _chunking_provider(chunking_strategy),
                    "chunking_model": _chunking_model(chunking_strategy),
                },
            )
        )
    return chunks


def _chunking_method(chunking_strategy: TextChunkingStrategy | None) -> str:
    if chunking_strategy is None:
        return "deterministic-character-overlap"
    if chunking_strategy.provider == "tiktoken":
        return "deterministic-token-overlap"
    return "llm-assisted"


def _chunking_provider(chunking_strategy: TextChunkingStrategy | None) -> str | None:
    return None if chunking_strategy is None else chunking_strategy.provider


def _chunking_model(chunking_strategy: TextChunkingStrategy | None) -> str | None:
    return None if chunking_strategy is None else chunking_strategy.model
