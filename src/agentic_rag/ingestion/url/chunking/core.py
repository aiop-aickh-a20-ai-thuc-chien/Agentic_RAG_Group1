"""URL-specific Chunk mapping with shared ingestion chunking helpers."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.chunking import (
    DEFAULT_PARAGRAPH_MAX_TOKENS as SHARED_PARAGRAPH_MAX_TOKENS,
)
from agentic_rag.ingestion.chunking import (
    DEFAULT_PARAGRAPH_OVERLAP as SHARED_PARAGRAPH_OVERLAP,
)
from agentic_rag.ingestion.chunking import (
    build_chunk_id,
    chunk_structural_clarity,
    chunk_text_quality,
    detect_lang,
    is_usable_chunk_text,
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
    "chunk_evidence_diagnostics",
    "chunk_structural_clarity",
    "chunk_text_quality",
    "detect_lang",
    "is_usable_chunk_text",
    "normalize_space",
    "paragraph_chunk",
    "short_hash",
    "slugify",
    "split_markdown",
    "split_markdown_paragraphs",
    "split_sentences",
]

_NUMBER_WITH_OPTIONAL_UNIT_RE = re.compile(
    r"(?<![\w])"
    r"(?:\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)"
    r"(?:\s*(?:%|km|kwh|kw|vnd|vnđ|ty|tỷ|trieu|triệu|m2|m²|nam|năm))?"
    r"(?![\w])",
    re.IGNORECASE,
)
_MARKDOWN_PREFIX_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|#{1,6}\s*)")


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
    text_chunks = split_markdown_paragraphs(
        text,
        max_tokens=chunk_size,
        overlap_paragraphs=chunk_overlap,
    )
    chunk_part_total = len(text_chunks)
    for index, chunk_text in enumerate(text_chunks, start=1):
        chunk_id = build_chunk_id(source_type, source, section, index)
        chunk_quality = chunk_text_quality(chunk_text)
        structural_clarity = chunk_quality["structural_clarity"]
        evidence_diagnostics = chunk_evidence_diagnostics(chunk_text)
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
                    "content_hash": content_hash,
                    "chunk_index": index,
                    "chunk_part_index": index,
                    "chunk_part_total": chunk_part_total,
                    "chunk_quality": chunk_quality,
                    "is_usable_for_retrieval": chunk_quality["is_usable"],
                    "structural_clarity": structural_clarity,
                    "has_structural_confusion": not structural_clarity["is_clear"],
                    "needs_table_reconstruction": structural_clarity["needs_table_reconstruction"],
                    "evidence_diagnostics": evidence_diagnostics,
                    "has_duplicate_evidence": evidence_diagnostics["has_duplicate_evidence"],
                    "has_possible_conflict": evidence_diagnostics["has_possible_conflict"],
                },
            )
        )
    return chunks


def chunk_evidence_diagnostics(text: str) -> dict[str, Any]:
    """Detect repeated or potentially conflicting evidence inside one chunk."""

    lines = [_normalize_evidence_line(line) for line in text.splitlines()]
    lines = [line for line in lines if len(line) >= 24]
    duplicate_groups: list[dict[str, Any]] = [
        {"text": line, "count": count} for line, count in Counter(lines).most_common() if count > 1
    ][:3]

    numeric_values = [
        _normalize_numeric_value(match.group(0))
        for match in _NUMBER_WITH_OPTIONAL_UNIT_RE.finditer(text)
    ]
    repeated_numeric_values: list[dict[str, Any]] = [
        {"value": value, "count": count}
        for value, count in Counter(numeric_values).most_common()
        if count > 1
    ][:5]

    values_by_label: dict[str, set[str]] = defaultdict(set)
    for raw_line in text.splitlines():
        label = _evidence_label(raw_line)
        if not label:
            continue
        values = {
            _normalize_numeric_value(match.group(0))
            for match in _NUMBER_WITH_OPTIONAL_UNIT_RE.finditer(raw_line)
        }
        if values:
            values_by_label[label].update(values)

    conflict_groups: list[dict[str, Any]] = [
        {"label": label, "values": sorted(values)}
        for label, values in values_by_label.items()
        if len(values) > 1
    ][:3]

    return {
        "duplicate_evidence_count": sum(group["count"] - 1 for group in duplicate_groups),
        "duplicate_evidence_examples": duplicate_groups,
        "numeric_value_count": len(numeric_values),
        "unique_numeric_value_count": len(set(numeric_values)),
        "repeated_numeric_values": repeated_numeric_values,
        "possible_conflict_count": len(conflict_groups),
        "possible_conflict_examples": conflict_groups,
        "has_duplicate_evidence": bool(duplicate_groups),
        "has_possible_conflict": bool(conflict_groups),
    }


def _normalize_evidence_line(line: str) -> str:
    cleaned = _MARKDOWN_PREFIX_RE.sub("", line)
    return normalize_space(cleaned).casefold()


def _normalize_numeric_value(value: str) -> str:
    return normalize_space(value).casefold().replace(",", ".")


def _evidence_label(line: str) -> str | None:
    cleaned = _MARKDOWN_PREFIX_RE.sub("", line)
    if ":" in cleaned:
        label = cleaned.split(":", 1)[0]
    elif " - " in cleaned:
        label = cleaned.split(" - ", 1)[0]
    else:
        return None
    label = normalize_space(label).casefold()
    return label if 3 <= len(label) <= 80 else None
