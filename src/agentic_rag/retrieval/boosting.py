"""Metadata-aware score boosting for retrieved chunks."""

from __future__ import annotations

import math
import os
from datetime import UTC, datetime
from typing import Any

from agentic_rag.core.contracts import SearchResult


def _noop_traceable(*, name: str = "", run_type: str = "chain", **_: object) -> Any:
    def _decorator(func: Any) -> Any:
        return func

    return _decorator


try:
    from langsmith import traceable as _ls_traceable
except Exception:  # pragma: no cover - langsmith optional
    _ls_traceable = _noop_traceable  # type: ignore[assignment]


@_ls_traceable(name="metadata-boosting", run_type="tool")
def _trace_boosting(summary: dict[str, Any]) -> dict[str, Any]:
    """Emit the soft-boosting decision to LangSmith (factors, reordering).

    A span only appears when ``METADATA_BOOSTING_ENABLED`` is on, so an absent
    span = boosting off. Shows the multiplicative factor range applied and whether
    the top result changed, so an A/B run can tell if boosting actually reordered.
    """
    return summary


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


def _quality_boost_enabled() -> bool:
    return os.getenv("METADATA_QUALITY_BOOST_ENABLED", "false").lower() == "true"


def _retrieval_weight_boost_enabled() -> bool:
    return os.getenv("METADATA_RETRIEVAL_WEIGHT_BOOST_ENABLED", "false").lower() == "true"


def _trust_boost_enabled() -> bool:
    return os.getenv("METADATA_TRUST_BOOST_ENABLED", "false").lower() == "true"


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

    top_before = results[0].chunk.chunk_id
    factors: list[float] = []
    boosted: list[SearchResult] = []
    for result in results:
        normalized_score = (result.score - min_score) / score_range
        metadata = result.chunk.metadata
        document_type_factor = _document_type_factor(
            doc_type=str(metadata.get("document_type") or "unknown"),
            query_type=query_type,
        )
        recency_factor = _recency_factor(metadata.get("fetched_at"))
        dedup_factor = _dedup_factor(metadata.get("deduplication"))
        quality_factor = (
            _quality_factor(metadata.get("quality_score")) if _quality_boost_enabled() else 1.0
        )
        retrieval_weight_factor = (
            _retrieval_weight_factor(metadata.get("retrieval_weight"))
            if _retrieval_weight_boost_enabled()
            else 1.0
        )
        trust_factor = _trust_factor(metadata) if _trust_boost_enabled() else 1.0
        raw_factor = (
            document_type_factor
            * recency_factor
            * dedup_factor
            * quality_factor
            * retrieval_weight_factor
            * trust_factor
        )
        factor = max(0.7, min(1.4, raw_factor))
        factors.append(factor)
        boosted.append(result.model_copy(update={"score": normalized_score * factor}))

    boosted.sort(key=lambda r: r.score, reverse=True)
    reranked = [r.model_copy(update={"rank": rank}) for rank, r in enumerate(boosted, start=1)]
    _trace_boosting(
        {
            "enabled": True,
            "query_type": query_type,
            "count": len(results),
            "min_factor": min(factors),
            "max_factor": max(factors),
            "mean_factor": sum(factors) / len(factors),
            "boosted_count": sum(1 for f in factors if abs(f - 1.0) > 1e-9),
            "top_changed": top_before != reranked[0].chunk.chunk_id,
        }
    )
    return reranked


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


def _quality_factor(quality_score: Any) -> float:
    if isinstance(quality_score, bool) or not isinstance(quality_score, (int, float)):
        return 1.0
    score = max(0.0, min(1.0, float(quality_score)))
    # Map 0..1 to a small 0.9..1.1 multiplier.
    return 0.9 + (score * 0.2)


def _retrieval_weight_factor(retrieval_weight: Any) -> float:
    if isinstance(retrieval_weight, bool) or not isinstance(retrieval_weight, (int, float)):
        return 1.0
    return max(0.8, min(1.2, float(retrieval_weight)))


def _trust_factor(metadata: Any) -> float:
    if not isinstance(metadata, dict):
        return 1.0
    if metadata.get("metadata_prefilter_exclude") is True:
        return 0.7
    if metadata.get("trusted_for_retrieval") is False:
        return 0.85
    return 1.0
