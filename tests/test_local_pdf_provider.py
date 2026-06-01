from pathlib import Path
from typing import Any, cast

from pytest import MonkeyPatch

from agentic_rag.core.contracts import Chunk, SearchResult
from agentic_rag.integrations.local_pdf.providers import LocalPdfEvidenceProvider
from agentic_rag.retrieval.search import Store


def test_local_pdf_provider_uploads_chunks_and_lists_them(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_pdf_chunks",
        lambda path: [
            Chunk(
                chunk_id="pdf_doc_c0001",
                text="Pin VF8 duoc bao hanh 8 nam.",
                metadata={"chunk_index": 1, "section": "Bao hanh"},
            ),
            Chunk(
                chunk_id="pdf_doc_c0002",
                text="Dieu kien bao hanh can co hoa don.",
                metadata={"chunk_index": 2, "section": "Dieu kien"},
            ),
        ],
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    uploaded = provider.upload_document(
        filename="warranty.pdf",
        content=b"%PDF-1.4",
        content_type="application/pdf",
    )
    document_chunks = provider.document_chunks(document_id=uploaded.document_id)

    assert uploaded.dataset_id == "local_pdf"
    assert uploaded.name == "warranty.pdf"
    assert uploaded.parse_started is True
    trace = cast(dict[str, dict[str, Any]], uploaded.trace)
    assert trace["source_upload"]["filename"] == "warranty.pdf"
    assert trace["parse"]["parser"] == "docling"
    assert trace["chunking"]["chunk_count"] == 2
    assert trace["index_write"]["type"] == "jsonl"
    assert document_chunks.total_chunks == 2
    assert [chunk.chunk_id for chunk in document_chunks.chunks] == [
        "pdf_doc_c0001",
        "pdf_doc_c0002",
    ]
    assert document_chunks.chunks[0].metadata["document_id"] == uploaded.document_id
    assert document_chunks.chunks[0].metadata["source"] == "warranty.pdf"
    assert (tmp_path / "chunks" / f"{uploaded.document_id}.jsonl").exists()


def test_local_pdf_provider_retrieves_matching_chunks(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANK_PROVIDER", "score")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_pdf_chunks",
        lambda path: [
            Chunk(
                chunk_id="pdf_doc_c0001",
                text="Pin VF8 duoc bao hanh 8 nam.",
                metadata={"chunk_index": 1},
            ),
            Chunk(
                chunk_id="pdf_doc_c0002",
                text="Lich bao duong lop xe.",
                metadata={"chunk_index": 2},
            ),
        ],
    )

    def fake_dense_search(self: Store, query: str, top_k: int = 10) -> list[SearchResult]:
        return [
            SearchResult(
                chunk=self._chunks[0],
                score=0.95,
                rank=1,
                retriever="dense",
            )
        ][:top_k]

    monkeypatch.setattr(Store, "dense_search", fake_dense_search)
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    uploaded = provider.upload_document(
        filename="warranty.pdf",
        content=b"%PDF-1.4",
        content_type="application/pdf",
    )

    results = provider.retrieve(
        question="pin bao hanh bao lau",
        document_ids=[uploaded.document_id],
    )

    assert len(results) >= 1
    assert results[0].chunk.chunk_id == "pdf_doc_c0001"
    assert results[0].retriever == "rerank"
    assert results[0].rank == 1
    assert (
        results[0].chunk.metadata["retrieval_pipeline"]
        == "pdf_ingestion -> bm25 + dense -> rrf -> rerank"
    )
    assert results[0].chunk.metadata["bm25"] is not None
    assert results[0].chunk.metadata["dense"] is not None
    assert results[0].chunk.metadata["dense_error"] is None
    assert results[0].chunk.metadata["rrf"] is not None
    pipeline_trace = cast(dict[str, Any], results[0].chunk.metadata["pipeline_trace"])
    assert pipeline_trace["preprocess_query"]["input"]["query"] == "pin bao hanh bao lau"
    assert isinstance(pipeline_trace["preprocess_query"]["latency_ms"], int)
    assert pipeline_trace["preprocess_query"]["output"]["normalized"] == "pin bao hanh bao lau"
    assert pipeline_trace["bm25_search"]["input"]["query"] == "pin bao hanh bao lau"
    assert pipeline_trace["bm25_search"]["output"][0]["retriever"] == "bm25"
    assert pipeline_trace["dense_search"]["tech"]["model"] == "text-embedding-3-small"
    assert pipeline_trace["dense_search"]["output"]["results"][0]["retriever"] == "dense"
    assert pipeline_trace["rrf_fusion"]["input"]["bm25_results"][0]["retriever"] == "bm25"
    assert pipeline_trace["rrf_fusion"]["output"][0]["retriever"] == "hybrid"
    rrf_contributions = pipeline_trace["rrf_fusion"]["output"][0]["contributions"]
    assert rrf_contributions["bm25"]["retriever"] == "bm25"
    assert rrf_contributions["dense"]["retriever"] == "dense"
    assert rrf_contributions["total_rrf_score"] > 0
    assert results[0].chunk.metadata["rrf_contributions"]["total_rrf_score"] > 0
    assert pipeline_trace["rerank"]["tech"]["used_provider"] == "score"
    assert pipeline_trace["rerank"]["input"]["candidates"][0]["retriever"] == "hybrid"
    assert pipeline_trace["rerank"]["output"][0]["retriever"] == "rerank"


def test_local_pdf_provider_rejects_non_pdf_upload(tmp_path: Path) -> None:
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    try:
        provider.upload_document(
            filename="notes.txt",
            content=b"hello",
            content_type="text/plain",
        )
    except ValueError as exc:
        assert "only supports PDF" in str(exc)
    else:
        raise AssertionError("Expected non-PDF upload to be rejected.")
