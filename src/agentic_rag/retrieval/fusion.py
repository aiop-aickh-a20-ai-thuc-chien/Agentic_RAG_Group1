"""Hybrid fusion, reranking, and evidence context boundaries."""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, cast

from agentic_rag.core.contracts import SearchResult

RRF_K = 60
RERANK_PROVIDER_ENV = "RERANK_PROVIDER"
RERANK_MODEL_ENV = "RERANK_CROSS_ENCODER_MODEL"
RERANK_PROVIDER_SCORE = "score"
RERANK_PROVIDER_CROSS_ENCODER = "cross-encoder"
DEFAULT_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class _CrossEncoderModel(Protocol):
    def predict(self, sentences: list[tuple[str, str]]) -> object:
        """Return relevance scores for query/document pairs."""


@dataclass
class _FusedCandidate:
    """Internal accumulator for Reciprocal Rank Fusion."""

    representative: SearchResult
    score: float
    best_rank: int


def rrf_fusion(
    bm25_results: list[SearchResult],
    dense_results: list[SearchResult],
    top_k: int = 10,
) -> list[SearchResult]:
    """Fuse BM25 and dense results into a final ranked result list."""

    if top_k < 0:
        raise ValueError("top_k must be >= 0 for rrf_fusion.")
    if top_k == 0:
        return []

    fused_by_chunk_id: dict[str, _FusedCandidate] = {}
    _accumulate_rrf_scores(fused_by_chunk_id, bm25_results)
    _accumulate_rrf_scores(fused_by_chunk_id, dense_results)

    ranked_candidates = sorted(
        fused_by_chunk_id.values(),
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


def rerank(
    query: str,
    candidates: list[SearchResult],
    top_k: int = 5,
) -> list[SearchResult]:
    """Rerank fused candidates with a cross-encoder when configured."""

    results, _metadata = rerank_with_metadata(query=query, candidates=candidates, top_k=top_k)
    return results


def rerank_with_metadata(
    query: str,
    candidates: list[SearchResult],
    top_k: int = 5,
) -> tuple[list[SearchResult], dict[str, object]]:
    """Rerank fused candidates and return the actual strategy used."""

    if top_k < 0:
        raise ValueError("top_k must be >= 0 for rerank.")
    if top_k == 0:
        return [], rerank_metadata()

    unique_candidates = list(_deduplicate_by_best_rank(candidates).values())
    provider = _configured_rerank_provider()
    if provider == RERANK_PROVIDER_CROSS_ENCODER and query.strip():
        model_name = _configured_cross_encoder_model_name()
        try:
            return _cross_encoder_rerank(
                query=query,
                candidates=unique_candidates,
                top_k=top_k,
            ), {
                "configured_provider": provider,
                "used_provider": RERANK_PROVIDER_CROSS_ENCODER,
                "model": model_name,
                "library": "sentence-transformers",
            }
        except (ImportError, RuntimeError, OSError) as exc:
            return _score_based_rerank(unique_candidates, top_k=top_k), {
                "configured_provider": provider,
                "used_provider": RERANK_PROVIDER_SCORE,
                "fallback_reason": f"{type(exc).__name__}: {exc}",
                "fallback_provider": RERANK_PROVIDER_SCORE,
                "requested_model": model_name,
                "method": "score_based_sort",
            }

    return _score_based_rerank(unique_candidates, top_k=top_k), {
        "configured_provider": provider,
        "used_provider": RERANK_PROVIDER_SCORE,
        "method": "score_based_sort",
    }


def rerank_metadata() -> dict[str, object]:
    """Return the rerank strategy currently selected by environment config."""

    provider = _configured_rerank_provider()
    metadata: dict[str, object] = {
        "provider": provider,
        "fallback_provider": RERANK_PROVIDER_SCORE,
    }
    if provider == RERANK_PROVIDER_CROSS_ENCODER:
        metadata["model"] = _configured_cross_encoder_model_name()
        metadata["library"] = "sentence-transformers"
    else:
        metadata["method"] = "score_based_sort"
    return metadata


def _score_based_rerank(candidates: list[SearchResult], *, top_k: int) -> list[SearchResult]:
    ranked_candidates = sorted(
        candidates,
        key=lambda candidate: (
            -candidate.score,
            candidate.rank,
            candidate.chunk.chunk_id,
        ),
    )

    return [
        SearchResult(
            chunk=candidate.chunk,
            score=candidate.score,
            rank=rank,
            retriever="rerank",
        )
        for rank, candidate in enumerate(ranked_candidates[:top_k], start=1)
    ]


def _cross_encoder_rerank(
    *,
    query: str,
    candidates: list[SearchResult],
    top_k: int,
) -> list[SearchResult]:
    model = _load_cross_encoder_model(_configured_cross_encoder_model_name())
    pairs = [(query, candidate.chunk.text) for candidate in candidates]
    scores = _coerce_scores(model.predict(pairs))
    if len(scores) != len(candidates):
        raise RuntimeError("Cross-encoder returned an unexpected number of scores.")

    scored_candidates = sorted(
        zip(candidates, scores, strict=True),
        key=lambda item: (
            -item[1],
            item[0].rank,
            item[0].chunk.chunk_id,
        ),
    )

    return [
        SearchResult(
            chunk=candidate.chunk,
            score=score,
            rank=rank,
            retriever="rerank",
        )
        for rank, (candidate, score) in enumerate(scored_candidates[:top_k], start=1)
    ]


def build_evidence_context(evidence_chunks: list[SearchResult]) -> str:
    """Format final evidence chunks into context for generation."""

    lines: list[str] = []
    for result in sorted(evidence_chunks, key=lambda item: item.rank):
        metadata = result.chunk.metadata
        source = _metadata_text(metadata, "source") or "unknown"
        page = _metadata_text(metadata, "page")
        section = _metadata_text(metadata, "section")
        location = _format_location(page=page, section=section)
        text = _normalize_text(result.chunk.text)
        lines.append(
            f"[{result.rank}] source={source}{location}; "
            f"chunk_id={result.chunk.chunk_id}; score={result.score:.6f}; text={text}"
        )

    return "\n".join(lines)


def _accumulate_rrf_scores(
    fused_by_chunk_id: dict[str, _FusedCandidate],
    results: list[SearchResult],
) -> None:
    for result in _deduplicate_by_best_rank(results).values():
        if result.rank < 1:
            raise ValueError("SearchResult.rank must be >= 1 for rrf_fusion.")

        chunk_id = result.chunk.chunk_id
        candidate = fused_by_chunk_id.get(chunk_id)
        contribution = 1.0 / (RRF_K + result.rank)
        if candidate is None:
            fused_by_chunk_id[chunk_id] = _FusedCandidate(
                representative=result,
                score=contribution,
                best_rank=result.rank,
            )
            continue

        candidate.score += contribution
        if result.rank < candidate.best_rank or (
            result.rank == candidate.best_rank and result.score > candidate.representative.score
        ):
            candidate.representative = result
            candidate.best_rank = result.rank


def _deduplicate_by_best_rank(results: list[SearchResult]) -> dict[str, SearchResult]:
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


def _configured_rerank_provider() -> str:
    raw_provider = os.getenv(RERANK_PROVIDER_ENV, RERANK_PROVIDER_SCORE).strip().lower()
    if raw_provider in {"cross_encoder", "cross-encoder", "sentence-transformers"}:
        return RERANK_PROVIDER_CROSS_ENCODER
    return RERANK_PROVIDER_SCORE


def _configured_cross_encoder_model_name() -> str:
    return os.getenv(RERANK_MODEL_ENV, DEFAULT_CROSS_ENCODER_MODEL).strip() or (
        DEFAULT_CROSS_ENCODER_MODEL
    )


@lru_cache(maxsize=1)
def _load_cross_encoder_model(model_name: str) -> _CrossEncoderModel:
    sentence_transformers = importlib.import_module("sentence_transformers")
    cross_encoder = sentence_transformers.CrossEncoder
    return cast(_CrossEncoderModel, cross_encoder(model_name))


def _coerce_scores(raw_scores: object) -> list[float]:
    if hasattr(raw_scores, "tolist"):
        raw_scores = raw_scores.tolist()
    if not isinstance(raw_scores, Iterable) or isinstance(raw_scores, str | bytes):
        raise RuntimeError("Cross-encoder scores must be an iterable of numbers.")
    return [float(score) for score in raw_scores]


def _metadata_text(metadata: Mapping[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    return str(value)


def _format_location(*, page: str | None, section: str | None) -> str:
    parts: list[str] = []
    if page:
        parts.append(f"page={page}")
    if section:
        parts.append(f"section={section}")
    return f"; {', '.join(parts)}" if parts else ""


def _normalize_text(text: str) -> str:
    return " ".join(text.split())
