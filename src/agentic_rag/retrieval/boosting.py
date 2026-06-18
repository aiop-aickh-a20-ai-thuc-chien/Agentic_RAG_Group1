"""Metadata-aware score boosting for retrieved chunks."""

from __future__ import annotations

import math
import os
from datetime import UTC, datetime
from typing import Any

from agentic_rag.core.contracts import SearchResult

_DOCUMENT_TYPE_BOOST_MATRIX: dict[str, dict[str, float]] = {
    "faq": {
        "faq": 1.3,
        "manual": 1.1,
        "article": 1.0,
        "spec_sheet": 0.95,
        "policy": 0.9,
        "unknown": 0.85,
    },
    "spec_sheet": {
        "spec_sheet": 1.3,
        "manual": 1.1,
        "article": 1.0,
        "faq": 0.95,
        "policy": 0.9,
        "unknown": 0.85,
    },
    "manual": {
        "manual": 1.3,
        "faq": 1.1,
        "article": 1.0,
        "spec_sheet": 1.0,
        "policy": 0.9,
        "unknown": 0.85,
    },
    "policy": {
        "policy": 1.3,
        "article": 1.0,
        "faq": 1.0,
        "manual": 0.95,
        "spec_sheet": 0.9,
        "unknown": 0.85,
    },
    "article": {
        "article": 1.1,
        "faq": 1.0,
        "manual": 1.0,
        "spec_sheet": 1.0,
        "policy": 1.0,
        "unknown": 0.9,
    },
}

_DEFAULT_DOC_TYPE_BOOST: dict[str, float] = {
    "faq": 1.0,
    "policy": 1.0,
    "manual": 1.0,
    "spec_sheet": 1.1,
    "article": 1.0,
    "unknown": 0.9,
}

_DEDUP_CANDIDATE_FACTOR = 0.8
_RECENCY_MAX_BOOST = 1.0
_RECENCY_MIN_SCORE = 1.0  # change to 0.9 if you want to penalize old content
_RECENCY_HALF_LIFE_DAYS = 90


def _boosting_enabled() -> bool:
    return os.getenv("METADATA_BOOSTING_ENABLED", "true").lower() == "true"


def apply_metadata_boost(
    results: list[SearchResult],
    *,
    query_type: str | None = None,
) -> list[SearchResult]:
    """Apply metadata score multipliers after fusion.

    Three signals applied multiplicatively:
    1. document_type — query-aware weights
    2. fetched_at    — recency decay
    3. deduplication — penalty for duplicate_candidate chunks
    """
    if not _boosting_enabled():
        return results
    if not results:
        return results
    if len(results) == 1:
        return [results[0].model_copy(update={"rank": 1})]

    min_score = min(r.score for r in results)
    max_score = max(r.score for r in results)
    score_range = max_score - min_score or 1.0

    boosted: list[SearchResult] = []
    for result in results:
        normalized_score = (result.score - min_score) / score_range
        metadata = result.chunk.metadata
        factor = 1.0
        factor *= _document_type_factor(
            doc_type=str(metadata.get("document_type") or "unknown"),
            query_type=query_type,
        )
        factor *= _recency_factor(metadata.get("fetched_at"))
        factor *= _dedup_factor(metadata.get("deduplication"))
        factor = max(0.7, min(1.4, factor))

        boosted.append(result.model_copy(update={"score": normalized_score * factor}))

    boosted.sort(key=lambda r: r.score, reverse=True)
    return [r.model_copy(update={"rank": rank}) for rank, r in enumerate(boosted, start=1)]


def _document_type_factor(doc_type: str, query_type: str | None) -> float:
    # "unknown" query_type (and None) intentionally fall through to _DEFAULT_DOC_TYPE_BOOST
    matrix = _DOCUMENT_TYPE_BOOST_MATRIX.get(query_type or "")
    if matrix:
        return matrix.get(doc_type, 1.0)
    return _DEFAULT_DOC_TYPE_BOOST.get(doc_type, 1.0)


def _recency_factor(fetched_at: Any) -> float:
    if not isinstance(fetched_at, str) or not fetched_at:
        return 1.0
    try:
        dt = datetime.fromisoformat(fetched_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        age_days = (datetime.now(UTC) - dt).days
        decay = math.exp(-age_days * math.log(2) / _RECENCY_HALF_LIFE_DAYS)
        return _RECENCY_MIN_SCORE + (_RECENCY_MAX_BOOST - _RECENCY_MIN_SCORE) * decay
    except (ValueError, TypeError):
        return 1.0


def _dedup_factor(deduplication: Any) -> float:
    if not isinstance(deduplication, dict):
        return 1.0
    if deduplication.get("status") == "duplicate_candidate":
        return _DEDUP_CANDIDATE_FACTOR
    return 1.0
