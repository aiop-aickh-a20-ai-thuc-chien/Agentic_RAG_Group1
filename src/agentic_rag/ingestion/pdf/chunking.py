"""Deterministic Markdown chunking for PDF ingestion."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

_HEADING_RE = re.compile(r"^#{1,6}(?!#)\s*(?P<title>.+?)\s*$")


class _PdfChunkingModel(BaseModel):
    """Base config for PDF-local chunking models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class MarkdownSection(_PdfChunkingModel):
    """A Markdown section associated with the nearest heading."""

    title: str | None
    text: str


class MarkdownChunk(_PdfChunkingModel):
    """A chunk of Markdown text ready to map into the shared Chunk contract."""

    section: str | None
    text: str


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
    max_chars: int = 1200,
    overlap_chars: int = 150,
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
