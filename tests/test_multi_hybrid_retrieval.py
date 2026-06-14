from __future__ import annotations

from typing import cast

import pytest
from pytest import MonkeyPatch

from agentic_rag.core.contracts import Chunk, RetrievalInput, SearchResult
from agentic_rag.integrations.local_pdf.providers import (
    _fuse_results_multi,
    _multi_fusion_weights,
    _retrieve_multi_hybrid,
)
from agentic_rag.retrieval.search import Store


def _sr(chunk_id: str, score: float, rank: int, retriever: str) -> SearchResult:
    return SearchResult(
        chunk=Chunk(chunk_id=chunk_id, text=chunk_id, metadata={}),
        score=score,
        rank=rank,
        retriever=retriever,
    )


def _store() -> Store:
    return Store(
        [
            Chunk(chunk_id="c1", text="lich bao duong lop xe", metadata={}),
            Chunk(chunk_id="c2", text="pin vf8 duoc bao hanh 8 nam", metadata={}),
        ]
    )


def test_fuse_results_multi_defaults_to_rrf_over_three_retrievers(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("FUSION_METHOD", raising=False)
    results = {
        "bm25": [_sr("a", 5.0, 1, "bm25"), _sr("b", 4.0, 2, "bm25")],
        "splade": [_sr("a", 3.0, 1, "splade")],
        "colbert": [_sr("a", 0.9, 1, "colbert")],
    }

    fused, trace = _fuse_results_multi(results, candidate_k=5)

    assert trace["method"] == "reciprocal_rank_fusion"
    assert trace["retrievers"] == ["bm25", "splade", "colbert"]
    assert fused[0].chunk.chunk_id == "a"
    assert fused[0].retriever == "hybrid"


def test_fuse_results_multi_weighted_records_weights(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("FUSION_METHOD", "weighted_rrf")
    monkeypatch.setenv("FUSION_BM25_WEIGHT", "0.3")
    monkeypatch.delenv("FUSION_DENSE_WEIGHT", raising=False)
    results = {
        "bm25": [_sr("a", 5.0, 1, "bm25")],
        "dense": [_sr("a", 0.9, 1, "dense")],
    }

    _fused, trace = _fuse_results_multi(results, candidate_k=5)

    assert trace["method"] == "weighted_rrf"
    weights = cast(dict[str, float], trace["weights"])
    assert weights["bm25"] == pytest.approx(0.3)
    assert weights["dense"] == pytest.approx(0.5)


def test_multi_fusion_weights_uses_defaults_and_env(monkeypatch: MonkeyPatch) -> None:
    for name in ("FUSION_BM25_WEIGHT", "FUSION_SPLADE_WEIGHT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FUSION_COLBERT_WEIGHT", "0.7")

    weights = _multi_fusion_weights(["bm25", "splade", "colbert"])

    assert weights == {"bm25": 0.4, "splade": 0.4, "colbert": 0.7}


def test_retrieve_multi_hybrid_bm25_only_returns_fused_results(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RETRIEVERS", "bm25")
    store = _store()
    preprocessed = store.preprocess_query("pin bao hanh")

    output = _retrieve_multi_hybrid(
        store=store,
        request=RetrievalInput(question="pin bao hanh"),
        preprocessed_query=preprocessed,
        normalized_query=preprocessed["normalized"],
        top_k=2,
        candidate_k=5,
        preprocess_latency_ms=0,
    )

    assert output.results
    assert output.results[0].chunk.chunk_id == "c2"
    assert output.results[0].retriever == "hybrid"
    pipeline_trace = output.results[0].chunk.metadata["pipeline_trace"]
    assert "bm25" in pipeline_trace["retrievers"]


def test_retrieve_multi_hybrid_degrades_failing_retriever(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVERS", "bm25,colbert")
    store = _store()
    original_search = store.retriever_search

    def flaky(provider: str, query: str, top_k: int = 10) -> list[SearchResult]:
        if provider == "colbert":
            raise RuntimeError("model boom")
        return original_search(provider, query, top_k=top_k)

    monkeypatch.setattr(store, "retriever_search", flaky)
    preprocessed = store.preprocess_query("pin bao hanh")

    output = _retrieve_multi_hybrid(
        store=store,
        request=RetrievalInput(question="pin bao hanh"),
        preprocessed_query=preprocessed,
        normalized_query=preprocessed["normalized"],
        top_k=2,
        candidate_k=5,
        preprocess_latency_ms=0,
    )

    assert output.results
    errors = output.results[0].chunk.metadata["retriever_errors"]
    assert errors["colbert"] == "model boom"
