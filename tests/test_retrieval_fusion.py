import pytest

import agentic_rag.retrieval.fusion as fusion_module
from agentic_rag.core.contracts import Chunk, SearchResult
from agentic_rag.retrieval.fusion import build_evidence_context, rerank, rrf_fusion


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


def test_rerank_orders_by_candidate_score_and_reassigns_rerank_ranks() -> None:
    candidates = [
        _result(_chunk("chunk-a", "A"), score=0.2, rank=1, retriever="hybrid"),
        _result(_chunk("chunk-b", "B"), score=0.9, rank=2, retriever="hybrid"),
        _result(_chunk("chunk-c", "C"), score=0.4, rank=3, retriever="hybrid"),
    ]

    reranked = rerank("warranty question", candidates, top_k=2)

    assert [result.chunk.chunk_id for result in reranked] == ["chunk-b", "chunk-c"]
    assert [result.rank for result in reranked] == [1, 2]
    assert [result.retriever for result in reranked] == ["rerank", "rerank"]


def test_rerank_deduplicates_candidates_by_best_rank() -> None:
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


def test_rerank_uses_cross_encoder_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setenv("RERANK_PROVIDER", "cross-encoder")
    monkeypatch.setattr(
        fusion_module,
        "_load_cross_encoder_model",
        lambda model_name: FakeCrossEncoder(),
    )

    reranked = rerank("warranty question", candidates, top_k=2)

    assert [result.chunk.chunk_id for result in reranked] == ["chunk-b", "chunk-c"]
    assert [result.score for result in reranked] == [0.95, 0.4]
    assert [result.retriever for result in reranked] == ["rerank", "rerank"]


def test_rerank_falls_back_to_score_based_when_cross_encoder_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_import_error(model_name: str) -> object:
        raise ImportError(model_name)

    candidates = [
        _result(_chunk("chunk-a", "A"), score=0.9, rank=1, retriever="hybrid"),
        _result(_chunk("chunk-b", "B"), score=0.2, rank=2, retriever="hybrid"),
    ]
    monkeypatch.setenv("RERANK_PROVIDER", "cross-encoder")
    monkeypatch.setattr(fusion_module, "_load_cross_encoder_model", raise_import_error)

    reranked = rerank("warranty question", candidates)

    assert [result.chunk.chunk_id for result in reranked] == ["chunk-a", "chunk-b"]


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
        "[1] source=warranty.pdf; page=12; chunk_id=pdf-1; "
        "score=0.500000; text=Pin cao ap duoc bao hanh 8 nam.",
        "[2] source=https://example.com/warranty; section=main; chunk_id=url-1; "
        "score=0.250000; text=Noi dung chinh tu website.",
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
