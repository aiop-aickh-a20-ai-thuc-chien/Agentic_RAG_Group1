"""Text normalization used before duplicate detection."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from agentic_rag.ingestion.dedup_detect.models import DedupDocument

_ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\ufeff]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Normalize text for stable duplicate fingerprints."""

    normalized = unicodedata.normalize("NFKC", text)
    normalized = _ZERO_WIDTH_RE.sub("", normalized)
    normalized = normalized.casefold()
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()


def dedup_text(document: DedupDocument) -> str:
    """Return the canonical text used by duplicate-detection layers.

    URL ingestion precomputes ``dedupe_text`` after removing source-specific
    noise such as URLs and zero-width markers. Other ingestion sources can opt
    into the same behavior through metadata while older chunks still fall back
    to normalized raw text.
    """

    metadata_text = _metadata_text(document.metadata.get("dedupe_text"))
    if metadata_text:
        return metadata_text
    metadata_text = _metadata_text(document.metadata.get("normalized_text"))
    if metadata_text:
        return metadata_text
    return normalize_text(document.text)


def _metadata_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = normalize_text(value)
    return normalized or None
