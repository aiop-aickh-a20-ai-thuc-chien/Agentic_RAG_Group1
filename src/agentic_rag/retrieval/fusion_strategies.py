"""Fusion strategies for sparse and dense retrieval results."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import SearchResult
from agentic_rag.retrieval.thresholds import (
    deduplicate_by_best_rank,
    normalized_scores_by_chunk_id,
)

RRF_K = 60
DEFAULT_BM25_WEIGHT = 0.55
DEFAULT_DENSE_WEIGHT = 0.45
DEFAULT_NORMALIZED_SCORE_ALPHA = 0.55


class FusedCandidate(BaseModel):
    """Internal accumulator for fusion strategies."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    representative: SearchResult
    score: float
    best_rank: int


def rrf_fusion_nway(
    result_lists: list[list[SearchResult]],
    *,
    top_k: int = 10,
    rrf_k: int = RRF_K,
) -> list[SearchResult]:
    """Fuse an arbitrary number of retriever result lists via RRF.

    Each list is one retriever (bm25, dense, question-index, ...). RRF is
    rank-based, so retrievers on different score scales fuse without
    normalization. Empty lists contribute nothing.
    """

    if top_k < 0:
        raise ValueError("top_k must be >= 0 for rrf_fusion_nway.")
    if rrf_k < 0:
        raise ValueError("rrf_k must be >= 0 for rrf_fusion_nway.")
    if top_k == 0:
        return []

    fused_by_chunk_id: dict[str, FusedCandidate] = {}
    for results in result_lists:
        accumulate_rrf_scores(fused_by_chunk_id, results, rrf_k=rrf_k)
    return rank_fused_candidates(fused_by_chunk_id.values(), top_k=top_k)


def rrf_fusion(
    bm25_results: list[SearchResult],
    dense_results: list[SearchResult],
    top_k: int = 10,
    *,
    rrf_k: int = RRF_K,
) -> list[SearchResult]:
    """Fuse BM25 and dense results into a final ranked result list."""

    return rrf_fusion_nway([bm25_results, dense_results], top_k=top_k, rrf_k=rrf_k)


def weighted_rrf_fusion(
    bm25_results: list[SearchResult],
    dense_results: list[SearchResult],
    *,
    top_k: int = 10,
    rrf_k: int = RRF_K,
    bm25_weight: float = DEFAULT_BM25_WEIGHT,
    dense_weight: float = DEFAULT_DENSE_WEIGHT,
) -> list[SearchResult]:
    """Fuse results with retriever-specific RRF weights."""

    if top_k < 0:
        raise ValueError("top_k must be >= 0 for weighted_rrf_fusion.")
    if rrf_k < 0:
        raise ValueError("rrf_k must be >= 0 for weighted_rrf_fusion.")
    if top_k == 0:
        return []

    fused_by_chunk_id: dict[str, FusedCandidate] = {}
    accumulate_weighted_rrf_scores(
        fused_by_chunk_id,
        bm25_results,
        weight=bm25_weight,
        rrf_k=rrf_k,
    )
    accumulate_weighted_rrf_scores(
        fused_by_chunk_id,
        dense_results,
        weight=dense_weight,
        rrf_k=rrf_k,
    )
    return rank_fused_candidates(fused_by_chunk_id.values(), top_k=top_k)


def normalized_score_fusion(
    bm25_results: list[SearchResult],
    dense_results: list[SearchResult],
    *,
    top_k: int = 10,
    alpha: float = DEFAULT_NORMALIZED_SCORE_ALPHA,
) -> list[SearchResult]:
    """Fuse results by min-max normalized retriever scores."""

    if top_k < 0:
        raise ValueError("top_k must be >= 0 for normalized_score_fusion.")
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha must be between 0.0 and 1.0.")
    if top_k == 0:
        return []

    normalized_bm25 = normalized_scores_by_chunk_id(bm25_results)
    normalized_dense = normalized_scores_by_chunk_id(dense_results)
    best_results = {
        **deduplicate_by_best_rank(dense_results),
        **deduplicate_by_best_rank(bm25_results),
    }

    fused_candidates: list[FusedCandidate] = []
    for chunk_id, representative in best_results.items():
        fused_score = alpha * normalized_bm25.get(chunk_id, 0.0) + (1.0 - alpha) * (
            normalized_dense.get(chunk_id, 0.0)
        )
        fused_candidates.append(
            FusedCandidate(
                representative=representative,
                score=fused_score,
                best_rank=representative.rank,
            )
        )

    return rank_fused_candidates(fused_candidates, top_k=top_k)


def accumulate_rrf_scores(
    fused_by_chunk_id: dict[str, FusedCandidate],
    results: list[SearchResult],
    *,
    rrf_k: int = RRF_K,
) -> None:
    for result in deduplicate_by_best_rank(results).values():
        if result.rank < 1:
            raise ValueError("SearchResult.rank must be >= 1 for rrf_fusion.")

        chunk_id = result.chunk.chunk_id
        candidate = fused_by_chunk_id.get(chunk_id)
        contribution = 1.0 / (rrf_k + result.rank)
        if candidate is None:
            fused_by_chunk_id[chunk_id] = FusedCandidate(
                representative=result,
                score=contribution,
                best_rank=result.rank,
            )
            continue

        fused_by_chunk_id[chunk_id] = _updated_candidate(
            candidate,
            result,
            additional_score=contribution,
        )


def accumulate_weighted_rrf_scores(
    fused_by_chunk_id: dict[str, FusedCandidate],
    results: list[SearchResult],
    *,
    weight: float,
    rrf_k: int,
) -> None:
    for result in deduplicate_by_best_rank(results).values():
        if result.rank < 1:
            raise ValueError("SearchResult.rank must be >= 1 for weighted_rrf_fusion.")

        chunk_id = result.chunk.chunk_id
        candidate = fused_by_chunk_id.get(chunk_id)
        contribution = weight / (rrf_k + result.rank)
        if candidate is None:
            fused_by_chunk_id[chunk_id] = FusedCandidate(
                representative=result,
                score=contribution,
                best_rank=result.rank,
            )
            continue

        fused_by_chunk_id[chunk_id] = _updated_candidate(
            candidate,
            result,
            additional_score=contribution,
        )


def rank_fused_candidates(
    candidates: Iterable[FusedCandidate],
    *,
    top_k: int,
) -> list[SearchResult]:
    ranked_candidates = sorted(
        candidates,
        key=lambda candidate: (
            -candidate.score,
            candidate.best_rank,
            candidate.representative.chunk.chunk_id,
        ),
    )
    return [
        SearchResult(
            chunk=candidate.representative.chunk,
            score=candidate.score,
            rank=rank,
            retriever="hybrid",
        )
        for rank, candidate in enumerate(ranked_candidates[:top_k], start=1)
    ]


def _updated_candidate(
    candidate: FusedCandidate,
    result: SearchResult,
    *,
    additional_score: float,
) -> FusedCandidate:
    updates: dict[str, object] = {"score": candidate.score + additional_score}
    if result.rank < candidate.best_rank or (
        result.rank == candidate.best_rank and result.score > candidate.representative.score
    ):
        updates["representative"] = result
        updates["best_rank"] = result.rank
    return candidate.model_copy(update=updates)
