"""Section-aware Markdown chunking for URL ingestion."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(?P<marker>#{1,6})(?!#)\s*(?P<title>.+?)\s*$")


@dataclass(frozen=True)
class MarkdownSection:
    """A URL Markdown section with heading hierarchy metadata."""

    title: str | None
    level: int
    path: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class MarkdownChunk:
    """A chunk of URL Markdown associated with a heading path."""

    section: str | None
    section_level: int
    section_path: tuple[str, ...]
    text: str


def split_markdown_into_sections(markdown: str) -> list[MarkdownSection]:
    """Split Markdown into heading-scoped sections and preserve h1/h2 hierarchy."""

    sections: list[MarkdownSection] = []
    heading_stack: list[tuple[int, str]] = []
    current_title: str | None = None
    current_level = 0
    current_path: tuple[str, ...] = ()
    current_lines: list[str] = []

    def flush_current() -> None:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append(
                MarkdownSection(
                    title=current_title,
                    level=current_level,
                    path=current_path,
                    text=text,
                )
            )

    for line in markdown.splitlines():
        heading_match = _HEADING_RE.match(line.strip())
        if heading_match is None:
            current_lines.append(line)
            continue

        flush_current()
        heading_level = len(heading_match.group("marker"))
        heading_title = heading_match.group("title").strip()
        heading_stack = [heading for heading in heading_stack if heading[0] < heading_level]
        heading_stack.append((heading_level, heading_title))
        current_title = heading_title
        current_level = heading_level
        current_path = tuple(title for _, title in heading_stack)
        current_lines = []

    flush_current()
    return sections


def chunk_markdown_by_sections(
    markdown: str,
    *,
    max_chars: int = 1_200,
    overlap_chars: int = 150,
) -> list[MarkdownChunk]:
    """Split URL Markdown into deterministic, section-aware chunks."""

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
            chunks.append(
                MarkdownChunk(
                    section=section.title,
                    section_level=section.level,
                    section_path=section.path,
                    text=text,
                )
            )
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
        next_start = end - overlap_chars
        start = end if next_start <= start else next_start
    return chunks
