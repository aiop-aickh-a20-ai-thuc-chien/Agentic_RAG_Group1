from collections.abc import Iterator
from typing import cast

import pytest
from pydantic import BaseModel, ValidationError

import agentic_rag.retrieval.fusion as fusion_module
from agentic_rag.core.contracts import Chunk, SearchResult
from agentic_rag.retrieval.fusion import (
    ThresholdConfig,
    apply_fusion_threshold,
    apply_pre_fusion_thresholds,
    apply_rerank_threshold,
    build_evidence_context,
    normalized_score_fusion,
    preload_reranker,
    rerank,
    rerank_with_metadata,
    rrf_fusion,
    weighted_rrf_fusion,
)


@pytest.fixture(autouse=True)
def _clean_model_runtime(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from agentic_rag.model_runtime.factory import clear_model_runtime_caches

    clear_model_runtime_caches()
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setattr("agentic_rag.model_runtime.config.load_local_env", lambda: None)
    yield
    clear_model_runtime_caches()


def test_threshold_config_is_pydantic_contract() -> None:
    config = ThresholdConfig(bm25_min_score=0.2)

    assert isinstance(config, BaseModel)
    assert config.bm25_min_score == 0.2
    assert config.min_evidence_count == 0

    with pytest.raises(ValidationError):
        ThresholdConfig.model_validate({"bm25_min_score": 0.2, "unexpected": True})

    field_name = "bm25_min_score"

    with pytest.raises(ValidationError):
        setattr(config, field_name, 0.4)


def test_rrf_fusion_boosts_chunks_seen_by_both_retrievers() -> None:
    chunk_a = _chunk("chunk-a", "Sparse-first evidence.")
    chunk_b = _chunk("chunk-b", "Shared evidence.")
    chunk_c = _chunk("chunk-c", "Dense-only evidence.")

    fused = rrf_fusion(
        bm25_results=[
            _result(chunk_a, score=12.0, rank=1, retriever="bm25"),
            _result(chunk_b, score=9.0, rank=2, retriever="bm25"),
        ],
        dense_results=[
            _result(chunk_b, score=0.92, rank=1, retriever="dense"),
            _result(chunk_c, score=0.81, rank=2, retriever="dense"),
        ],
    )

    assert [result.chunk.chunk_id for result in fused] == ["chunk-b", "chunk-a", "chunk-c"]
    assert fused[0].score > fused[1].score
    assert fused[0].retriever == "hybrid"


def test_rrf_fusion_deduplicates_duplicate_chunk_ids_within_one_retriever() -> None:
    chunk = _chunk("chunk-a", "Repeated sparse evidence.")

    fused = rrf_fusion(
        bm25_results=[
            _result(chunk, score=0.3, rank=3, retriever="bm25"),
            _result(chunk, score=0.9, rank=1, retriever="bm25"),
        ],
        dense_results=[],
    )

    assert len(fused) == 1
    assert fused[0].chunk.chunk_id == "chunk-a"
    assert fused[0].score == pytest.approx(1.0 / 61.0)


def test_rrf_fusion_accepts_custom_rrf_k() -> None:
    chunk = _chunk("chunk-a", "Sparse evidence.")

    fused = rrf_fusion(
        bm25_results=[_result(chunk, score=0.9, rank=1, retriever="bm25")],
        dense_results=[],
        rrf_k=10,
    )

    assert fused[0].score == pytest.approx(1.0 / 11.0)


def test_rrf_fusion_respects_top_k_and_reassigns_hybrid_ranks() -> None:
    fused = rrf_fusion(
        bm25_results=[
            _result(_chunk("chunk-a", "A"), score=5.0, rank=1, retriever="bm25"),
            _result(_chunk("chunk-b", "B"), score=4.0, rank=2, retriever="bm25"),
            _result(_chunk("chunk-c", "C"), score=3.0, rank=3, retriever="bm25"),
        ],
        dense_results=[],
        top_k=2,
    )

    assert [result.rank for result in fused] == [1, 2]
    assert [result.retriever for result in fused] == ["hybrid", "hybrid"]
    assert [result.chunk.chunk_id for result in fused] == ["chunk-a", "chunk-b"]


def test_rrf_fusion_rejects_non_positive_input_ranks() -> None:
    with pytest.raises(ValueError, match=r"SearchResult\.rank must be >= 1"):
        rrf_fusion(
            bm25_results=[_result(_chunk("chunk-a", "A"), score=1.0, rank=0, retriever="bm25")],
            dense_results=[],
        )


def test_weighted_rrf_fusion_applies_configured_weights() -> None:
    shared_chunk = _chunk("chunk-shared", "Shared evidence.")
    bm25_only_chunk = _chunk("chunk-bm25", "BM25 evidence.")

    fused = weighted_rrf_fusion(
        bm25_results=[
            _result(shared_chunk, score=5.0, rank=2, retriever="bm25"),
            _result(bm25_only_chunk, score=6.0, rank=1, retriever="bm25"),
        ],
        dense_results=[_result(shared_chunk, score=0.9, rank=1, retriever="dense")],
        bm25_weight=0.55,
        dense_weight=0.45,
    )

    expected_shared_score = 0.55 / 62.0 + 0.45 / 61.0
    assert fused[0].chunk.chunk_id == "chunk-shared"
    assert fused[0].score == pytest.approx(expected_shared_score)


def test_weighted_rrf_fusion_handles_empty_retrievers() -> None:
    dense_chunk = _chunk("chunk-dense", "Dense-only evidence.")

    dense_only = weighted_rrf_fusion(
        bm25_results=[],
        dense_results=[_result(dense_chunk, score=0.8, rank=1, retriever="dense")],
    )
    bm25_only = weighted_rrf_fusion(
        bm25_results=[_result(dense_chunk, score=1.2, rank=1, retriever="bm25")],
        dense_results=[],
    )
    both_empty = weighted_rrf_fusion(bm25_results=[], dense_results=[])

    assert [result.chunk.chunk_id for result in dense_only] == ["chunk-dense"]
    assert [result.chunk.chunk_id for result in bm25_only] == ["chunk-dense"]
    assert both_empty == []


def test_normalized_score_fusion_combines_per_retriever_normalized_scores() -> None:
    chunk_a = _chunk("chunk-a", "A")
    chunk_b = _chunk("chunk-b", "B")
    chunk_c = _chunk("chunk-c", "C")

    fused = normalized_score_fusion(
        bm25_results=[
            _result(chunk_a, score=10.0, rank=1, retriever="bm25"),
            _result(chunk_b, score=0.0, rank=2, retriever="bm25"),
        ],
        dense_results=[
            _result(chunk_b, score=0.9, rank=1, retriever="dense"),
            _result(chunk_c, score=0.1, rank=2, retriever="dense"),
        ],
        alpha=0.6,
    )

    assert [result.chunk.chunk_id for result in fused] == ["chunk-a", "chunk-b", "chunk-c"]
    assert fused[0].score == pytest.approx(0.6)
    assert fused[1].score == pytest.approx(0.4)


def test_normalized_score_fusion_handles_equal_scores_and_empty_retriever() -> None:
    chunk_a = _chunk("chunk-a", "A")
    chunk_b = _chunk("chunk-b", "B")

    fused = normalized_score_fusion(
        bm25_results=[
            _result(chunk_a, score=1.0, rank=1, retriever="bm25"),
            _result(chunk_b, score=1.0, rank=2, retriever="bm25"),
        ],
        dense_results=[],
        alpha=0.55,
    )

    assert [result.score for result in fused] == [0.55, 0.55]


def test_apply_pre_fusion_thresholds_filters_noisy_retriever_results() -> None:
    strong_bm25 = _result(_chunk("chunk-strong", "Strong."), score=5.0, rank=1, retriever="bm25")
    weak_bm25 = _result(_chunk("chunk-weak", "Weak."), score=0.1, rank=2, retriever="bm25")

    bm25_results, dense_results, trace = apply_pre_fusion_thresholds(
        bm25_results=[strong_bm25, weak_bm25],
        dense_results=[],
        config=ThresholdConfig(bm25_min_score=1.0),
    )

    assert [result.chunk.chunk_id for result in bm25_results] == ["chunk-strong"]
    assert dense_results == []
    assert trace["bm25_original_count"] == 2
    assert trace["bm25_after_threshold_count"] == 1
    assert trace["dense_empty"] is True
    assert trace["thresholds_applied"] is True
    removed = cast(dict[str, list[dict[str, object]]], trace["removed"])
    assert removed["bm25"][0]["chunk_id"] == "chunk-weak"


def test_apply_fusion_threshold_filters_low_fusion_scores_and_top_k() -> None:
    candidates = [
        _result(_chunk("chunk-a", "A"), score=0.9, rank=1, retriever="hybrid"),
        _result(_chunk("chunk-b", "B"), score=0.4, rank=2, retriever="hybrid"),
        _result(_chunk("chunk-c", "C"), score=0.8, rank=3, retriever="hybrid"),
    ]

    filtered, trace = apply_fusion_threshold(
        candidates,
        config=ThresholdConfig(fusion_min_score=0.5),
        top_k=1,
    )

    assert [result.chunk.chunk_id for result in filtered] == ["chunk-a"]
    assert trace["fusion_original_count"] == 3
    assert trace["fusion_after_threshold_count"] == 1
    removed = cast(list[dict[str, object]], trace["removed_by_fusion_threshold"])
    assert {item["chunk_id"] for item in removed} == {"chunk-b", "chunk-c"}


def test_apply_rerank_threshold_removes_low_score_chunks() -> None:
    strong = _result(_chunk("chunk-strong", "Strong."), score=0.8, rank=1, retriever="rerank")
    weak = _result(_chunk("chunk-weak", "Weak."), score=0.1, rank=2, retriever="rerank")

    filtered, trace = apply_rerank_threshold(
        [strong, weak],
        config=ThresholdConfig(rerank_min_score=0.5),
    )

    assert [result.chunk.chunk_id for result in filtered] == ["chunk-strong"]
    assert trace["rerank_original_count"] == 2
    assert trace["rerank_after_threshold_count"] == 1
    removed = cast(list[dict[str, object]], trace["removed_by_rerank_threshold"])
    assert removed[0]["chunk_id"] == "chunk-weak"


def test_apply_rerank_threshold_can_return_empty_final_evidence() -> None:
    weak = _result(_chunk("chunk-weak", "Weak."), score=0.1, rank=1, retriever="rerank")

    filtered, trace = apply_rerank_threshold(
        [weak],
        config=ThresholdConfig(rerank_min_score=0.5),
    )

    assert filtered == []
    assert trace["final_evidence_count"] == 0


def test_rerank_orders_by_candidate_score_and_reassigns_rerank_ranks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANK_PROVIDER", "score")
    candidates = [
        _result(_chunk("chunk-a", "A"), score=0.2, rank=1, retriever="hybrid"),
        _result(_chunk("chunk-b", "B"), score=0.9, rank=2, retriever="hybrid"),
        _result(_chunk("chunk-c", "C"), score=0.4, rank=3, retriever="hybrid"),
    ]

    reranked = rerank("warranty question", candidates, top_k=2)

    assert [result.chunk.chunk_id for result in reranked] == ["chunk-b", "chunk-c"]
    assert [result.rank for result in reranked] == [1, 2]
    assert [result.retriever for result in reranked] == ["rerank", "rerank"]


def test_rerank_deduplicates_candidates_by_best_rank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RERANK_PROVIDER", "score")
    chunk = _chunk("chunk-a", "Repeated candidate.")

    reranked = rerank(
        "question",
        [
            _result(chunk, score=0.5, rank=3, retriever="hybrid"),
            _result(chunk, score=0.4, rank=1, retriever="hybrid"),
        ],
    )

    assert len(reranked) == 1
    assert reranked[0].chunk.chunk_id == "chunk-a"
    assert reranked[0].score == 0.4
    assert reranked[0].rank == 1


def test_rerank_uses_sentence_transformers_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCrossEncoder:
        def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
            assert pairs == [
                ("warranty question", "A"),
                ("warranty question", "B"),
                ("warranty question", "C"),
            ]
            return [0.1, 0.95, 0.4]

    candidates = [
        _result(_chunk("chunk-a", "A"), score=0.9, rank=1, retriever="hybrid"),
        _result(_chunk("chunk-b", "B"), score=0.2, rank=2, retriever="hybrid"),
        _result(_chunk("chunk-c", "C"), score=0.4, rank=3, retriever="hybrid"),
    ]
    monkeypatch.setenv("RERANK_PROVIDER", "sentence_transformers")
    monkeypatch.setattr(
        "agentic_rag.model_runtime.rerankers._load_cross_encoder",
        lambda model_name, device=None: FakeCrossEncoder(),
    )

    reranked = rerank("warranty question", candidates, top_k=2)

    assert [result.chunk.chunk_id for result in reranked] == ["chunk-b", "chunk-c"]
    assert [result.score for result in reranked] == [0.95, 0.4]
    assert [result.retriever for result in reranked] == ["rerank", "rerank"]


def test_rerank_with_metadata_reports_actual_sentence_transformers_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCrossEncoder:
        def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
            return [0.8, 0.1]

    candidates = [
        _result(_chunk("chunk-a", "A"), score=0.2, rank=1, retriever="hybrid"),
        _result(_chunk("chunk-b", "B"), score=0.9, rank=2, retriever="hybrid"),
    ]
    monkeypatch.setenv("RERANK_PROVIDER", "sentence_transformers")
    monkeypatch.setattr(
        "agentic_rag.model_runtime.rerankers._load_cross_encoder",
        lambda model_name, device=None: FakeCrossEncoder(),
    )

    reranked, metadata = rerank_with_metadata("warranty question", candidates, top_k=2)

    assert [result.chunk.chunk_id for result in reranked] == ["chunk-a", "chunk-b"]
    assert metadata["configured_provider"] == "sentence_transformers"
    assert metadata["used_provider"] == "sentence_transformers"


def test_rerank_metadata_uses_bge_model_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RERANK_PROVIDER", "sentence_transformers")
    monkeypatch.delenv("RERANK_MODEL", raising=False)

    metadata = fusion_module.rerank_metadata()

    assert metadata["provider"] == "sentence_transformers"
    assert metadata["model"] == "BAAI/bge-reranker-v2-m3"


def test_rerank_metadata_reports_configured_bge_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RERANK_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    monkeypatch.setenv("RERANK_DEVICE", "cuda")

    metadata = fusion_module.rerank_metadata()

    assert metadata["provider"] == "sentence_transformers"
    assert metadata["model"] == "BAAI/bge-reranker-v2-m3"
    assert metadata["device"] == "cuda"
    assert metadata["library"] == "sentence-transformers"


def test_preload_reranker_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RERANK_PROVIDER", "sentence_transformers")
    monkeypatch.delenv("RERANK_PRELOAD", raising=False)

    metadata = preload_reranker()

    assert metadata["preload"] is False
    assert metadata["status"] == "disabled"


def test_preload_reranker_skips_score_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RERANK_PROVIDER", "score")
    monkeypatch.setenv("RERANK_PRELOAD", "true")

    metadata = preload_reranker()

    assert metadata["preload"] is True
    assert metadata["status"] == "skipped"
    assert metadata["reason"] == "provider_not_sentence_transformers"


def test_preload_reranker_loads_configured_sentence_transformers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded_models: list[str] = []

    class FakeCrossEncoder:
        def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
            return [0.0 for _pair in pairs]

    def fake_load(model_name: str, device: str | None = None) -> FakeCrossEncoder:
        loaded_models.append(f"{model_name}:{device}")
        return FakeCrossEncoder()

    monkeypatch.setenv("RERANK_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("RERANK_MODEL", "test-reranker")
    monkeypatch.setenv("RERANK_DEVICE", "cuda")
    monkeypatch.setenv("RERANK_PRELOAD", "true")
    monkeypatch.setattr("agentic_rag.model_runtime.rerankers._load_cross_encoder", fake_load)

    metadata = preload_reranker()

    assert loaded_models == ["test-reranker:cuda"]
    assert metadata["status"] == "loaded"
    assert metadata["model"] == "test-reranker"
    assert metadata["device"] == "cuda"
    assert metadata["used_provider"] == "sentence_transformers"


def test_preload_reranker_falls_back_when_cuda_torch_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_cuda_error(model_name: str, device: str | None = None) -> object:
        raise AssertionError("Torch not compiled with CUDA enabled")

    monkeypatch.setenv("RERANK_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("RERANK_MODEL", "test-reranker")
    monkeypatch.setenv("RERANK_DEVICE", "cuda")
    monkeypatch.setenv("RERANK_PRELOAD", "true")
    monkeypatch.setattr(
        "agentic_rag.model_runtime.rerankers._load_cross_encoder",
        raise_cuda_error,
    )

    metadata = preload_reranker()

    assert metadata["status"] == "failed"
    assert metadata["fallback_provider"] == "score"
    assert metadata["device"] == "cuda"
    assert "Torch not compiled with CUDA enabled" in str(metadata["fallback_reason"])


def test_rerank_falls_back_to_score_based_when_sentence_transformers_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_import_error(model_name: str, device: str | None = None) -> object:
        raise ImportError(model_name)

    candidates = [
        _result(_chunk("chunk-a", "A"), score=0.9, rank=1, retriever="hybrid"),
        _result(_chunk("chunk-b", "B"), score=0.2, rank=2, retriever="hybrid"),
    ]
    monkeypatch.setenv("RERANK_PROVIDER", "sentence_transformers")
    monkeypatch.setattr(
        "agentic_rag.model_runtime.rerankers._load_cross_encoder",
        raise_import_error,
    )

    reranked, metadata = rerank_with_metadata("warranty question", candidates)

    assert [result.chunk.chunk_id for result in reranked] == ["chunk-a", "chunk-b"]
    assert metadata["configured_provider"] == "sentence_transformers"
    assert metadata["used_provider"] == "score"
    assert "fallback_reason" in metadata


def test_build_evidence_context_formats_rank_source_location_chunk_and_text() -> None:
    pdf_chunk = _chunk(
        "pdf-1",
        "Pin cao ap\nduoc bao hanh 8 nam.",
        metadata={"source": "warranty.pdf", "source_type": "pdf", "page": 12},
    )
    url_chunk = _chunk(
        "url-1",
        "Noi dung chinh tu website.",
        metadata={
            "source": "https://example.com/warranty",
            "source_type": "url",
            "url": "https://example.com/warranty",
            "section": "main",
        },
    )

    context = build_evidence_context(
        [
            _result(url_chunk, score=0.25, rank=2, retriever="rerank"),
            _result(pdf_chunk, score=0.5, rank=1, retriever="rerank"),
        ]
    )

    assert context.splitlines() == [
        "[1] source=warranty.pdf; page=12; metadata=page_type=pdf, price_type=unknown;"
        " chunk_id=pdf-1; score=0.500000; text=Pin cao ap duoc bao hanh 8 nam.",
        "[2] source=https://example.com/warranty; section=main;"
        " metadata=page_type=url, price_type=unknown;"
        " chunk_id=url-1; score=0.250000; text=Noi dung chinh tu website.",
    ]


def _chunk(
    chunk_id: str,
    text: str,
    metadata: dict[str, object] | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        metadata=metadata or {"source": "test.txt", "source_type": "text"},
    )


def _result(chunk: Chunk, *, score: float, rank: int, retriever: str) -> SearchResult:
    return SearchResult(chunk=chunk, score=score, rank=rank, retriever=retriever)
