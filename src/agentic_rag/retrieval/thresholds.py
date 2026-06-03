"""Threshold helpers for retrieval candidate filtering."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from agentic_rag.core.contracts import SearchResult


@dataclass(frozen=True)
class ThresholdConfig:
    """Optional retrieval thresholds; `None` keeps the stage backward-compatible."""

    bm25_min_score: float | None = None
    dense_min_score: float | None = None
    bm25_min_norm_score: float | None = None
    dense_min_norm_score: float | None = None
    fusion_min_score: float | None = None
    rerank_min_score: float | None = None
    min_evidence_count: int = 0


def apply_pre_fusion_thresholds(
    *,
    bm25_results: list[SearchResult],
    dense_results: list[SearchResult],
    config: ThresholdConfig,
) -> tuple[list[SearchResult], list[SearchResult], dict[str, object]]:
    """Filter weak retriever results before fusion and return trace metadata."""

    bm25_norm_scores = normalized_scores_by_chunk_id(bm25_results)
    dense_norm_scores = normalized_scores_by_chunk_id(dense_results)
    filtered_bm25, removed_bm25 = filter_by_thresholds(
        bm25_results,
        min_score=config.bm25_min_score,
        min_norm_score=config.bm25_min_norm_score,
        norm_scores=bm25_norm_scores,
    )
    filtered_dense, removed_dense = filter_by_thresholds(
        dense_results,
        min_score=config.dense_min_score,
        min_norm_score=config.dense_min_norm_score,
        norm_scores=dense_norm_scores,
    )
    trace: dict[str, object] = {
        "bm25_original_count": len(bm25_results),
        "bm25_after_threshold_count": len(filtered_bm25),
        "dense_original_count": len(dense_results),
        "dense_after_threshold_count": len(filtered_dense),
        "bm25_empty": not filtered_bm25,
        "dense_empty": not filtered_dense,
        "both_empty_after_threshold": not filtered_bm25 and not filtered_dense,
        "thresholds_applied": thresholds_applied(
            config.bm25_min_score,
            config.bm25_min_norm_score,
            config.dense_min_score,
            config.dense_min_norm_score,
        ),
        "removed": {
            "bm25": removed_bm25,
            "dense": removed_dense,
        },
    }
    return filtered_bm25, filtered_dense, trace


def apply_fusion_threshold(
    candidates: list[SearchResult],
    *,
    config: ThresholdConfig,
    top_k: int | None = None,
) -> tuple[list[SearchResult], dict[str, object]]:
    """Filter fused candidates by score and optional top-k."""

    if top_k is not None and top_k < 0:
        raise ValueError("top_k must be >= 0 for apply_fusion_threshold.")
    filtered, removed = filter_by_thresholds(
        candidates,
        min_score=config.fusion_min_score,
        min_norm_score=None,
        norm_scores={},
    )
    if top_k is not None:
        top_k_filtered = filtered[:top_k]
        removed.extend(removed_candidates(filtered[top_k:], "top_k"))
        filtered = top_k_filtered

    trace: dict[str, object] = {
        "fusion_original_count": len(candidates),
        "fusion_after_threshold_count": len(filtered),
        "fusion_min_score": config.fusion_min_score,
        "fused_top_k": top_k,
        "removed_by_fusion_threshold": removed,
    }
    return filtered, trace


def apply_rerank_threshold(
    candidates: list[SearchResult],
    *,
    config: ThresholdConfig,
    top_k: int | None = None,
) -> tuple[list[SearchResult], dict[str, object]]:
    """Filter reranked evidence candidates before context/citation."""

    if top_k is not None and top_k < 0:
        raise ValueError("top_k must be >= 0 for apply_rerank_threshold.")
    filtered, removed = filter_by_thresholds(
        candidates,
        min_score=config.rerank_min_score,
        min_norm_score=None,
        norm_scores={},
    )
    if top_k is not None:
        top_k_filtered = filtered[:top_k]
        removed.extend(removed_candidates(filtered[top_k:], "top_k"))
        filtered = top_k_filtered

    if config.min_evidence_count > 0 and len(filtered) < config.min_evidence_count:
        removed.extend(removed_candidates(filtered, "min_evidence_count"))
        filtered = []

    trace: dict[str, object] = {
        "rerank_original_count": len(candidates),
        "rerank_after_threshold_count": len(filtered),
        "rerank_min_score": config.rerank_min_score,
        "rerank_top_k": top_k,
        "min_evidence_count": config.min_evidence_count,
        "removed_by_rerank_threshold": removed,
        "final_evidence_count": len(filtered),
    }
    return filtered, trace


def normalized_scores_by_chunk_id(results: list[SearchResult]) -> dict[str, float]:
    deduplicated_results = deduplicate_by_best_rank(results)
    if not deduplicated_results:
        return {}

    scores = [result.score for result in deduplicated_results.values()]
    min_score = min(scores)
    max_score = max(scores)
    if min_score == max_score:
        return {chunk_id: 1.0 for chunk_id in deduplicated_results}

    return {
        chunk_id: (result.score - min_score) / (max_score - min_score)
        for chunk_id, result in deduplicated_results.items()
    }


def deduplicate_by_best_rank(results: list[SearchResult]) -> dict[str, SearchResult]:
    best_results: dict[str, SearchResult] = {}
    for result in results:
        chunk_id = result.chunk.chunk_id
        existing = best_results.get(chunk_id)
        if (
            existing is None
            or result.rank < existing.rank
            or (result.rank == existing.rank and result.score > existing.score)
        ):
            best_results[chunk_id] = result
    return best_results


def filter_by_thresholds(
    results: list[SearchResult],
    *,
    min_score: float | None,
    min_norm_score: float | None,
    norm_scores: Mapping[str, float],
) -> tuple[list[SearchResult], list[dict[str, object]]]:
    filtered: list[SearchResult] = []
    removed: list[dict[str, object]] = []
    for result in results:
        norm_score = norm_scores.get(result.chunk.chunk_id)
        reason = threshold_removal_reason(
            result=result,
            norm_score=norm_score,
            min_score=min_score,
            min_norm_score=min_norm_score,
        )
        if reason is None:
            filtered.append(result)
            continue

        removed.append(
            {
                "chunk_id": result.chunk.chunk_id,
                "rank": result.rank,
                "score": result.score,
                "normalized_score": norm_score,
                "reason": reason,
            }
        )
    return filtered, removed


def threshold_removal_reason(
    *,
    result: SearchResult,
    norm_score: float | None,
    min_score: float | None,
    min_norm_score: float | None,
) -> str | None:
    if min_score is not None and result.score < min_score:
        return "score_below_threshold"
    if min_norm_score is not None and norm_score is not None and norm_score < min_norm_score:
        return "normalized_score_below_threshold"
    return None


def thresholds_applied(*thresholds: float | None) -> bool:
    return any(threshold is not None for threshold in thresholds)


def removed_candidates(
    candidates: list[SearchResult],
    reason: str,
) -> list[dict[str, object]]:
    return [
        {
            "chunk_id": candidate.chunk.chunk_id,
            "rank": candidate.rank,
            "score": candidate.score,
            "reason": reason,
        }
        for candidate in candidates
    ]
