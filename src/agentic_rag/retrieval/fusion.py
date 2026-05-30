"""Hybrid fusion, reranking, and evidence context boundaries."""

from __future__ import annotations

from agentic_rag.core.contracts import SearchResult


def rrf_fusion(
    bm25_results: list[SearchResult],
    dense_results: list[SearchResult],
    top_k: int = 10,
) -> list[SearchResult]:
    """Fuse BM25 and dense results into a final ranked result list."""

    raise NotImplementedError("rrf_fusion is scaffolded for retrieval fusion.")


def rerank(
    query: str,
    candidates: list[SearchResult],
    top_k: int = 5,
) -> list[SearchResult]:
    """Optionally rerank fused candidates."""

    raise NotImplementedError("rerank is scaffolded for retrieval fusion.")


def build_evidence_context(evidence_chunks: list[SearchResult]) -> str:
    """Format final evidence chunks into context for generation."""

    raise NotImplementedError("build_evidence_context is scaffolded for retrieval fusion.")
