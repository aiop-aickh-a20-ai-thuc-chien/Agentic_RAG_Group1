"""Hybrid fusion, reranking, and evidence context boundaries."""

from __future__ import annotations

from collections.abc import Mapping

from agentic_rag.core.contracts import RerankInput, SearchResult
from agentic_rag.model_runtime.config import resolve_reranker_config
from agentic_rag.model_runtime.errors import ModelRuntimeError
from agentic_rag.model_runtime.factory import get_reranker, preload_configured_models
from agentic_rag.model_runtime.rerankers import ScoreReranker
from agentic_rag.retrieval.evidence_metadata import format_prompt_metadata
from agentic_rag.retrieval.fusion_strategies import (
    DEFAULT_BM25_WEIGHT,
    DEFAULT_DENSE_WEIGHT,
    DEFAULT_NORMALIZED_SCORE_ALPHA,
    RRF_K,
    normalized_score_fusion,
    normalized_score_fusion_n,
    rrf_fusion,
    weighted_rrf_fusion,
    weighted_rrf_fusion_n,
)
from agentic_rag.retrieval.thresholds import (
    ThresholdConfig,
    apply_fusion_threshold,
    apply_pre_fusion_thresholds,
    apply_rerank_threshold,
    deduplicate_by_best_rank,
)

RERANK_PROVIDER_SCORE = "score"


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

    unique_candidates = list(deduplicate_by_best_rank(candidates).values())
    request = RerankInput(query=query, candidates=unique_candidates, top_k=top_k)
    try:
        output = get_reranker().rerank(request)
        return output.results, dict(output.metadata)
    except ModelRuntimeError as exc:
        fallback = ScoreReranker().rerank(request)
        metadata = dict(fallback.metadata)
        metadata.update(
            {
                "configured_provider": resolve_reranker_config().provider,
                "fallback_reason": f"{type(exc).__name__}: {exc}",
                "fallback_provider": RERANK_PROVIDER_SCORE,
            }
        )
        return fallback.results, metadata


def rerank_metadata() -> dict[str, object]:
    """Return the rerank strategy currently selected by environment config."""

    config = resolve_reranker_config()
    metadata: dict[str, object] = {
        "provider": config.provider,
        "fallback_provider": RERANK_PROVIDER_SCORE,
    }
    if config.provider == "sentence_transformers":
        metadata["model"] = config.model
        metadata["device"] = config.device or "auto"
        metadata["library"] = "sentence-transformers"
    elif config.provider == RERANK_PROVIDER_SCORE:
        metadata["method"] = "score_based_sort"
    else:
        metadata["model"] = config.model
        metadata["library"] = "litellm"
    return metadata


def preload_reranker() -> dict[str, object]:
    """Load the configured reranker early when startup preload is enabled."""

    result = preload_configured_models().get("reranker", {})
    return dict(result) if isinstance(result, dict) else {"status": "disabled"}


def build_evidence_context(evidence_chunks: list[SearchResult]) -> str:
    """Format final evidence chunks into context for generation."""

    lines: list[str] = []
    for result in sorted(evidence_chunks, key=lambda item: item.rank):
        metadata = result.chunk.metadata
        source = _metadata_text(metadata, "source") or "unknown"
        page = _metadata_text(metadata, "page")
        section_path = metadata.get("section_path")
        if isinstance(section_path, list) and section_path:
            section: str | None = " > ".join(str(s) for s in section_path)
        else:
            section = _metadata_text(metadata, "section")
        location = _format_location(page=page, section=section)
        prompt_metadata = format_prompt_metadata(metadata)
        text = _normalize_text(result.chunk.text)
        lines.append(
            f"[{result.rank}] source={source}{location}{prompt_metadata}; "
            f"chunk_id={result.chunk.chunk_id}; score={result.score:.6f}; text={text}"
        )

    return "\n".join(lines)


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


__all__ = [
    "DEFAULT_BM25_WEIGHT",
    "DEFAULT_DENSE_WEIGHT",
    "DEFAULT_NORMALIZED_SCORE_ALPHA",
    "RRF_K",
    "ThresholdConfig",
    "apply_fusion_threshold",
    "apply_pre_fusion_thresholds",
    "apply_rerank_threshold",
    "build_evidence_context",
    "normalized_score_fusion",
    "normalized_score_fusion_n",
    "preload_reranker",
    "rerank",
    "rerank_metadata",
    "rerank_with_metadata",
    "rrf_fusion",
    "weighted_rrf_fusion",
    "weighted_rrf_fusion_n",
]
