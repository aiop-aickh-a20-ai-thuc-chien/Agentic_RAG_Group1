"""URL-local ingestion quality diagnostics."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.core.contracts import Chunk

QualityVerdict = Literal["useful", "low_signal", "empty"]

_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)
_BOILERPLATE_RE = re.compile(
    r"\b(cookie|copyright|privacy|login|hotline|support|home|all rights reserved)\b",
    re.I,
)
_HEADING_RE = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)


class UrlQualityReport(BaseModel):
    """Compact diagnostics for URL parse/chunk quality."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: QualityVerdict
    markdown_word_count: int
    heading_count: int
    chunk_count: int
    boilerplate_hit_count: int
    useful_chunk_count: int
    issues: list[str] = Field(default_factory=list)


def analyze_url_quality(markdown: str, chunks: list[Chunk]) -> UrlQualityReport:
    """Return URL-local quality diagnostics for parsed Markdown and chunks."""

    word_count = len(_WORD_RE.findall(markdown))
    heading_count = len(_HEADING_RE.findall(markdown))
    boilerplate_hit_count = len(_BOILERPLATE_RE.findall(markdown))
    useful_chunk_count = sum(1 for chunk in chunks if len(_WORD_RE.findall(chunk.text)) >= 8)
    issues: list[str] = []
    if word_count == 0 or not chunks:
        issues.append("empty_markdown_or_chunks")
        verdict: QualityVerdict = "empty"
    else:
        if word_count < 20:
            issues.append("low_word_count")
        if heading_count == 0:
            issues.append("missing_headings")
        if useful_chunk_count == 0:
            issues.append("no_useful_chunks")
        if boilerplate_hit_count >= 3:
            issues.append("boilerplate_heavy")
        verdict = "low_signal" if issues else "useful"
    return UrlQualityReport(
        verdict=verdict,
        markdown_word_count=word_count,
        heading_count=heading_count,
        chunk_count=len(chunks),
        boilerplate_hit_count=boilerplate_hit_count,
        useful_chunk_count=useful_chunk_count,
        issues=issues,
    )


def attach_quality_metadata(chunks: list[Chunk], report: UrlQualityReport) -> list[Chunk]:
    """Attach URL-local quality diagnostics to chunk metadata."""

    payload = report.model_dump()
    return [
        chunk.model_copy(update={"metadata": {**chunk.metadata, "url_quality": payload}})
        for chunk in chunks
    ]


__all__ = [
    "QualityVerdict",
    "UrlQualityReport",
    "analyze_url_quality",
    "attach_quality_metadata",
]
