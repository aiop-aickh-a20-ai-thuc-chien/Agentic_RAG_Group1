"""Shared deterministic chunking primitives for ingestion modules."""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict

DEFAULT_CHUNK_SIZE = 1_200
DEFAULT_CHUNK_OVERLAP = 150

_HEADING_RE = re.compile(r"^#{1,6}(?!#)\s*(?P<title>.+?)\s*$")


class _IngestionChunkingModel(BaseModel):
    """Base configuration for shared ingestion chunking models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class MarkdownSection(_IngestionChunkingModel):
    """A Markdown section associated with the nearest heading."""

    title: str | None
    text: str


class MarkdownChunk(_IngestionChunkingModel):
    """A chunk of Markdown/text ready to map into a shared Chunk contract."""

    section: str | None
    text: str


class TextChunkingStrategy(Protocol):
    """Strategy that splits normalized Markdown/text into chunk strings."""

    @property
    def provider(self) -> str:
        """Provider name used by the strategy."""

    @property
    def model(self) -> str:
        """Model name used by the strategy."""

    def split(self, text: str) -> list[str]:
        """Return chunk strings for the provided text."""


def split_markdown_into_sections(markdown: str) -> list[MarkdownSection]:
    """Split Markdown into heading-scoped text sections."""

    sections: list[MarkdownSection] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush_current() -> None:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append(MarkdownSection(title=current_title, text=text))

    for line in markdown.splitlines():
        heading_match = _HEADING_RE.match(line.strip())
        if heading_match is not None:
            flush_current()
            current_title = heading_match.group("title").strip()
            current_lines = []
            continue
        current_lines.append(line)

    flush_current()
    return sections


def chunk_markdown(
    markdown: str,
    *,
    max_chars: int = DEFAULT_CHUNK_SIZE,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP,
) -> list[MarkdownChunk]:
    """Split Markdown into deterministic section-aware chunks."""

    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero.")
    if overlap_chars < 0:
        raise ValueError("overlap_chars must be greater than or equal to zero.")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars.")

    chunks: list[MarkdownChunk] = []
    for section in split_markdown_into_sections(markdown):
        for text in _split_section_text(
            section.text,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        ):
            chunks.append(MarkdownChunk(section=section.title, text=text))
    return chunks


def split_markdown(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split Markdown/text deterministically with word-boundary preference."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size.")

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
        next_start = max(end - chunk_overlap, 0)
        start = end if next_start <= start else next_start
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


def split_text_with_strategy(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    chunking_strategy: TextChunkingStrategy | None = None,
) -> list[str]:
    """Split text with either deterministic or injected model-assisted chunking."""

    if chunking_strategy is None:
        return split_markdown(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return [
        normalize_space(chunk) for chunk in chunking_strategy.split(text) if normalize_space(chunk)
    ]


def _split_section_text(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    normalized_text = text.strip()
    if not normalized_text:
        return []
    if len(normalized_text) <= max_chars:
        return [normalized_text]

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", normalized_text)]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.extend(
                _split_windowed(current, max_chars=max_chars, overlap_chars=overlap_chars)
            )
        current = ""
        chunks.extend(_split_windowed(paragraph, max_chars=max_chars, overlap_chars=overlap_chars))

    if current:
        chunks.extend(_split_windowed(current, max_chars=max_chars, overlap_chars=overlap_chars))

    return chunks


def _split_windowed(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = end - overlap_chars
    return chunks
