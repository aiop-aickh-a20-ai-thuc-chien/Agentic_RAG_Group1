"""Query preprocessing, BM25 search, and dense search boundaries."""

from __future__ import annotations

from agentic_rag.core.contracts import Chunk, SearchResult


def preprocess_query(query: str) -> dict[str, str]:
    """Normalize a raw user query before retrieval."""

    raise NotImplementedError("preprocess_query is scaffolded for retrieval.")


def build_bm25_index(chunks: list[Chunk]) -> None:
    """Build or refresh a BM25 index from shared chunks."""

    raise NotImplementedError("build_bm25_index is scaffolded for retrieval.")


def bm25_search(query: str, top_k: int = 10) -> list[SearchResult]:
    """Return top-k BM25 retrieval results."""

    raise NotImplementedError("bm25_search is scaffolded for retrieval.")


def build_vector_index(chunks: list[Chunk]) -> None:
    """Build or refresh a dense vector index from shared chunks."""

    raise NotImplementedError("build_vector_index is scaffolded for retrieval.")


def dense_search(query: str, top_k: int = 10) -> list[SearchResult]:
    """Return top-k dense retrieval results."""

    raise NotImplementedError("dense_search is scaffolded for retrieval.")
