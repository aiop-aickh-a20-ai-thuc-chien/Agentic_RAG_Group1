"""URL-aware wrappers for shared section-aware Markdown chunking."""

import re

from agentic_rag.ingestion.chunking import (
    MarkdownChunk,
    MarkdownSection,
    split_markdown_into_sections,
)
from agentic_rag.ingestion.chunking import (
    chunk_markdown_by_sections as _shared_chunk_markdown_by_sections,
)

_VALUE_UNIT_RE = re.compile(
    r"\b(?:vnd|vn\u0111|km|kwh|kw|hp|nm|w|n\u0103m|nam|th\u00e1ng|thang)\b|%",
    flags=re.IGNORECASE,
)


def chunk_markdown_by_sections(
    markdown: str,
    *,
    max_tokens: int = 512,
    overlap_paragraphs: int = 1,
    max_chars: int | None = None,
    overlap_chars: int | None = None,
    root_title: str | None = None,
) -> list[MarkdownChunk]:
    """Split URL Markdown while demoting value-only pseudo headings.

    The shared chunker treats all-uppercase short lines as subsection titles.
    That is useful for many PDFs, but product pages often contain standalone
    price/spec values such as ``1.699.000.000 VND``. For URL ingestion, those
    values should stay under the parent product section instead of becoming
    section names.
    """

    chunks = _shared_chunk_markdown_by_sections(
        markdown,
        max_tokens=max_tokens,
        overlap_paragraphs=overlap_paragraphs,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
        root_title=root_title,
    )
    return [_demote_value_heading_chunk(chunk) for chunk in chunks]


def _demote_value_heading_chunk(chunk: MarkdownChunk) -> MarkdownChunk:
    section = chunk.section
    section_path = tuple(chunk.section_path)
    if section is None or len(section_path) < 2:
        return chunk
    if not _is_value_only_heading(section):
        return chunk

    parent_path = section_path[:-1]
    parent_section = parent_path[-1] if parent_path else None
    metadata = {
        **chunk.metadata,
        "demoted_value_heading": section,
        "demoted_value_heading_reason": "url_value_only_heading",
    }
    return chunk.model_copy(
        update={
            "section": parent_section,
            "section_path": parent_path,
            "text": _replace_leading_heading(
                chunk.text,
                old_heading=section,
                new_heading=parent_section,
            ),
            "metadata": metadata,
        }
    )


def _replace_leading_heading(
    text: str,
    *,
    old_heading: str,
    new_heading: str | None,
) -> str:
    pattern = re.compile(rf"^(?P<marker>#{{1,6}})\s+{re.escape(old_heading)}\s*\n+")
    match = pattern.match(text)
    if match is None:
        return text.strip()
    body = text[match.end() :].lstrip()
    if not new_heading:
        return body.strip()
    return f"{match.group('marker')} {new_heading}\n\n{body}".strip()


def _is_value_only_heading(value: str) -> bool:
    stripped = value.strip().strip("*_`")
    if not stripped or not any(char.isdigit() for char in stripped):
        return False
    if _VALUE_UNIT_RE.search(stripped):
        return True
    digit_count = sum(1 for char in stripped if char.isdigit())
    letter_count = sum(1 for char in stripped if char.isalpha())
    return digit_count >= 3 and digit_count >= max(1, letter_count * 2)


__all__ = [
    "MarkdownChunk",
    "MarkdownSection",
    "chunk_markdown_by_sections",
    "split_markdown_into_sections",
]
