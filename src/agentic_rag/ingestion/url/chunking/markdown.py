"""Section-aware Markdown chunking for URL ingestion."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agentic_rag.ingestion.url.chunking.core import (
    DEFAULT_PARAGRAPH_MAX_TOKENS,
    DEFAULT_PARAGRAPH_OVERLAP,
    paragraph_chunk,
)

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
    chunk_token_count: int
    semantic_unit: str = field(default="markdown_section_paragraph_sentence", kw_only=True)


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
    max_tokens: int = DEFAULT_PARAGRAPH_MAX_TOKENS,
    overlap_paragraphs: int = DEFAULT_PARAGRAPH_OVERLAP,
    max_chars: int | None = None,
    overlap_chars: int | None = None,
) -> list[MarkdownChunk]:
    """Split URL Markdown into deterministic, section-aware token chunks.

    ``max_chars`` and ``overlap_chars`` are accepted for compatibility with the
    previous char-window API. When provided, ``max_chars`` is converted to a
    conservative token budget.
    """

    if max_chars is not None:
        if max_chars <= 0:
            raise ValueError("max_chars must be greater than zero.")
        max_tokens = max(1, max_chars // 4)
    if overlap_chars is not None:
        if overlap_chars < 0:
            raise ValueError("overlap_chars must be greater than or equal to zero.")
        if max_chars is not None and overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars.")
    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than zero.")
    if overlap_paragraphs < 0:
        raise ValueError("overlap_paragraphs must be greater than or equal to zero.")

    chunks: list[MarkdownChunk] = []
    for section in split_markdown_into_sections(markdown):
        for paragraph_result in paragraph_chunk(
            section.text,
            max_tokens=max_tokens,
            overlap_paragraphs=overlap_paragraphs,
        ):
            text = str(paragraph_result["text"]).strip()
            if not text:
                continue
            chunks.append(
                MarkdownChunk(
                    section=section.title,
                    section_level=section.level,
                    section_path=section.path,
                    text=_with_section_heading(section=section, text=text),
                    chunk_token_count=int(paragraph_result["token_count"]),
                )
            )
    return chunks


def _with_section_heading(*, section: MarkdownSection, text: str) -> str:
    if section.title is None:
        return text
    heading_level = min(max(section.level, 1), 6)
    return f"{'#' * heading_level} {section.title}\n\n{text}"
