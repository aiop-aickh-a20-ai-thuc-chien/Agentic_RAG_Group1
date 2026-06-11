"""Text normalization used before duplicate detection."""

from __future__ import annotations

import re
import unicodedata

_ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\ufeff]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Normalize text for stable duplicate fingerprints."""

    normalized = unicodedata.normalize("NFKC", text)
    normalized = _ZERO_WIDTH_RE.sub("", normalized)
    normalized = normalized.casefold()
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()
