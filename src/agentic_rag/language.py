"""Shared language detection for the VinFast RAG agent.

Detection priority:
  1. Explicit instruction in the text ("answer in vietnamese")
  2. lingua statistical detection (English vs Vietnamese only)
  3. Domain keyword detection (handles short queries like "vf3 price")
  4. History language (carry forward from previous turns)
  5. Default: "vi"
"""

from __future__ import annotations

import re

from lingua import Language, LanguageDetectorBuilder

# ---------------------------------------------------------------------------
# Lingua detector — built once at module load, restricted to en/vi only
# ---------------------------------------------------------------------------

_DETECTOR = (
    LanguageDetectorBuilder.from_languages(Language.ENGLISH, Language.VIETNAMESE)
    .with_minimum_relative_distance(0.9)
    .build()
)

# ---------------------------------------------------------------------------
# Explicit instruction patterns — these win over statistical detection
# ---------------------------------------------------------------------------

_EXPLICIT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(answer|respond|reply|write)\s+(in\s+)?vietnamese\b", re.IGNORECASE), "vi"),
    (re.compile(r"\b(answer|respond|reply|write)\s+(in\s+)?english\b", re.IGNORECASE), "en"),
    (re.compile(r"\btrả\s*lời\s+bằng\s+tiếng\s+anh\b", re.IGNORECASE), "en"),
    (re.compile(r"\bviết\s+bằng\s+tiếng\s+anh\b", re.IGNORECASE), "en"),
    (re.compile(r"\btrả\s*lời\s+bằng\s+tiếng\s+việt\b", re.IGNORECASE), "vi"),
]

# ---------------------------------------------------------------------------
# English domain keywords — used when lingua is not confident enough
# (excludes shared words like "km", "vnd", "service", "motor")
# ---------------------------------------------------------------------------

_ENGLISH_KEYWORDS: frozenset[str] = frozenset(
    {
        # Price
        "price",
        "cost",
        "expensive",
        "cheap",
        # Battery / range
        "battery",
        "range",
        "mileage",
        "distance",
        # Charging
        "charge",
        "charging",
        "charger",
        # Specs
        "spec",
        "specs",
        "specification",
        "specifications",
        "horsepower",
        "torque",
        "acceleration",
        "dimension",
        "weight",
        # Warranty
        "warranty",
        "guarantee",
        # Comparison
        "compare",
        "comparison",
        "difference",
        "versus",
        "better",
        "worse",
        "between",
        # Safety
        "safety",
        "airbag",
        "autonomous",
        "brake",
        "crash",
        # Common English question words
        "what",
        "how",
        "which",
        "does",
        "the",
        "is",
        "are",
    }
)


def _has_english_keywords(text: str) -> bool:
    """Return True if text contains English domain keywords.

    Handles short queries like 'vf3 price' or 'vf8 battery range'
    where lingua lacks enough text to be confident.
    """
    words = set(re.findall(r"\b[a-z]+\b", text.lower()))
    return bool(words & _ENGLISH_KEYWORDS)


def detect_language(text: str, history: list[dict[str, str]] | None = None) -> str:
    """Return 'vi' or 'en' for the given text.

    Args:
        text: The user's current message.
        history: Conversation history, used as fallback when text is ambiguous.
    """
    # 1. Explicit instruction wins
    for pattern, lang in _EXPLICIT_PATTERNS:
        if pattern.search(text):
            return lang

    # 2. Statistical detection (returns None if confidence < 0.9)
    result = _DETECTOR.detect_language_of(text)
    if result is Language.ENGLISH:
        return "en"
    if result is Language.VIETNAMESE:
        return "vi"

    # 3. Keyword-based detection for short/ambiguous queries (e.g. "vf3 price")
    if _has_english_keywords(text):
        return "en"

    # 4. Fall back to history language
    if history:
        for lang in _extract_history_languages(history):
            return lang

    # 5. Default
    return "vi"


def _extract_history_languages(history: list[dict[str, str]]) -> list[str]:
    """Walk recent user turns and return the first confident lingua detection."""
    for msg in reversed(history):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "").strip()
        if not content:
            continue
        result = _DETECTOR.detect_language_of(content)
        if result is Language.ENGLISH:
            return ["en"]
        if result is Language.VIETNAMESE:
            return ["vi"]
    return []
