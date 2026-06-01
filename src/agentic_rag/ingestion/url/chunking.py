"""Deterministic Markdown/text chunking for URL ingestion."""

from __future__ import annotations

import hashlib
import re

from agentic_rag.core.contracts import Chunk

DEFAULT_CHUNK_SIZE = 1_200
DEFAULT_CHUNK_OVERLAP = 150


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
) -> list[Chunk]:
    """Build shared Chunk objects from normalized Markdown/text."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size.")

    chunks: list[Chunk] = []
    content_hash = short_hash(text)
    text_chunks = split_markdown(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
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
                },
            )
        )
    return chunks


def split_markdown(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split Markdown/text deterministically with word-boundary preference."""

    cleaned_text = normalize_space(text)
    if not cleaned_text:
        return []
    if len(cleaned_text) <= chunk_size:
        return [cleaned_text]

    chunks: list[str] = []
    start = 0
    while start < len(cleaned_text):
        end = min(start + chunk_size, len(cleaned_text))
        if end < len(cleaned_text):
            split_at = cleaned_text.rfind(" ", start, end)
            if split_at > start:
                end = split_at
        chunk = cleaned_text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned_text):
            break
        start = max(end - chunk_overlap, 0)
    return chunks


def build_chunk_id(source_type: str, source: str, section: str, index: int) -> str:
    """Build a deterministic chunk ID from source and section metadata."""

    return f"{source_type}_{short_hash(source)}_{slugify(section)}_c{index:03d}"


def short_hash(value: str) -> str:
    """Return a stable short SHA-256 digest."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def slugify(value: str) -> str:
    """Normalize a section name for use inside a chunk ID."""

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "main"


def normalize_space(value: str) -> str:
    """Collapse repeated whitespace into single spaces."""

    return " ".join(value.split())
