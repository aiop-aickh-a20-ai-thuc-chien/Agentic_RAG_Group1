import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from pytest import MonkeyPatch

from agentic_rag.core.contracts import Chunk, SearchResult
from agentic_rag.ingestion.pdf import LoadedPdfDocument
from agentic_rag.ingestion.pdf.config import PdfIngestionConfig
from agentic_rag.ingestion.url import LoadedUrlDocument
from agentic_rag.integrations.local_pdf.providers import LocalPdfEvidenceProvider
from agentic_rag.retrieval.search import Store


def _mock_openai_client(monkeypatch: MonkeyPatch) -> None:
    class FakeOpenAI:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self._call_count = 0
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, *_args: object, **_kwargs: object) -> object:
            self._call_count += 1
            if self._call_count == 1:
                content = "decompose"
            else:
                content = json.dumps(
                    {
                        "method": "decompose",
                        "transformed_queries": ["pin bao hanh bao lau"],
                    }
                )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)


def test_local_pdf_provider_uploads_chunks_and_lists_them(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    seen_kwargs: dict[str, str] = {}

    def fake_load_pdf_with_markdown(path: str, **kwargs: str) -> LoadedPdfDocument:
        seen_kwargs.update(kwargs)
        return LoadedPdfDocument(
            markdown="# Bao hanh\nPin VF8 duoc bao hanh 8 nam.",
            chunks=[
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
            parser=kwargs["strategy_name"],
            pipeline=kwargs["pipeline_name"],
            strategy=kwargs["strategy_name"],
            chunker=kwargs["chunker_name"],
        )

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_pdf_with_markdown",
        fake_load_pdf_with_markdown,
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
    assert trace["parse"]["markdown_chars"] == 39
    assert trace["parse"]["markdown_preview"] == "# Bao hanh\nPin VF8 duoc bao hanh 8 nam."
    assert "markdown" not in trace["parse"]
    assert seen_kwargs == {
        "pipeline_name": "ocr",
        "strategy_name": "docling",
        "chunker_name": "deterministic",
    }
    assert trace["chunking"]["chunk_count"] == 2
    assert trace["parse"]["pipeline"] == "ocr"
    assert trace["parse"]["strategy"] == "docling"
    assert trace["chunking"]["chunker"] == "deterministic"
    assert trace["index_write"]["type"] == "jsonl"
    assert document_chunks.total_chunks == 2
    assert [chunk.chunk_id for chunk in document_chunks.chunks] == [
        "pdf_doc_c0001",
        "pdf_doc_c0002",
    ]
    assert document_chunks.chunks[0].metadata["document_id"] == uploaded.document_id
    assert document_chunks.chunks[0].metadata["source"] == "warranty.pdf"
    assert (tmp_path / "chunks" / f"{uploaded.document_id}.jsonl").exists()
    markdown_path = tmp_path / "parsed" / f"{uploaded.document_id}.md"
    assert trace["parse"]["markdown_path"] == str(markdown_path)
    assert markdown_path.read_text(encoding="utf-8") == ("# Bao hanh\nPin VF8 duoc bao hanh 8 nam.")


def test_local_pdf_provider_can_include_full_markdown_in_trace(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_TRACE_FULL_CONTENT", "true")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_pdf_with_markdown",
        lambda path, **kwargs: LoadedPdfDocument(
            markdown="# Full\nMarkdown noi dung.",
            chunks=[],
        ),
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    uploaded = provider.upload_document(
        filename="notes.pdf",
        content=b"%PDF-1.4",
        content_type="application/pdf",
    )

    trace = cast(dict[str, dict[str, Any]], uploaded.trace)
    assert trace["parse"]["markdown"] == "# Full\nMarkdown noi dung."


def test_local_pdf_provider_passes_configured_parser_and_chunker(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    seen_kwargs: dict[str, str] = {}

    def fake_load_pdf_with_markdown(path: str, **kwargs: str) -> LoadedPdfDocument:
        seen_kwargs.update(kwargs)
        return LoadedPdfDocument(
            markdown="# Configured\nNoi dung.",
            chunks=[],
            parser=kwargs["strategy_name"],
            pipeline=kwargs["pipeline_name"],
            strategy=kwargs["strategy_name"],
            chunker=kwargs["chunker_name"],
        )

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_pdf_with_markdown",
        fake_load_pdf_with_markdown,
    )
    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        pdf_config=PdfIngestionConfig(
            pipeline_name="vlm",
            strategy_name="mineru",
            chunker_name="deterministic",
        ),
    )

    uploaded = provider.upload_document(
        filename="configured.pdf",
        content=b"%PDF-1.4",
        content_type="application/pdf",
    )

    trace = cast(dict[str, dict[str, Any]], uploaded.trace)
    assert seen_kwargs == {
        "pipeline_name": "vlm",
        "strategy_name": "mineru",
        "chunker_name": "deterministic",
    }
    assert trace["parse"]["parser"] == "mineru"
    assert trace["parse"]["pipeline"] == "vlm"
    assert trace["parse"]["strategy"] == "mineru"
    assert trace["chunking"]["chunker"] == "deterministic"


def test_local_pdf_provider_uploads_url_chunks(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_url_with_artifacts",
        lambda url, **kwargs: LoadedUrlDocument(
            markdown="# Trang chinh sach\n\n## Chinh sach\n\nNoi dung URL ve chinh sach mua nha.",
            chunks=[
                Chunk(
                    chunk_id="url_doc_c0001",
                    text="Noi dung URL ve chinh sach mua nha.",
                    metadata={
                        "source": url,
                        "source_type": "url",
                        "url": url,
                        "title": "Trang chinh sach",
                        "section": "Chinh sach",
                        "chunking_method": "deterministic-character-overlap",
                        "chunking_provider": None,
                        "chunking_model": None,
                    },
                )
            ],
            artifacts=None,
        ),
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    uploaded = provider.upload_url(url="https://example.com/chinh-sach")
    document_chunks = provider.document_chunks(document_id=uploaded.document_id)

    assert uploaded.dataset_id == "local_pdf"
    assert uploaded.name == "example.com-chinh-sach.txt"
    assert uploaded.parse_started is True
    trace = cast(dict[str, dict[str, Any]], uploaded.trace)
    assert trace["source_upload"]["source_type"] == "url"
    assert trace["source_upload"]["requested_url"] == "https://example.com/chinh-sach"
    assert trace["source_upload"]["final_url"] == "https://example.com/chinh-sach"
    assert trace["parse"]["parser"] == "url.load_url_with_artifacts"
    assert trace["parse"]["title"] == "Trang chinh sach"
    assert trace["parse"]["section_count"] == 1
    assert trace["parse"]["sections"] == ["Chinh sach"]
    assert trace["parse"]["markdown_path"] is None
    assert trace["parse"]["markdown_chars"] == 70
    assert trace["parse"]["markdown_preview"].startswith("# Trang chinh sach")
    assert trace["chunking"]["chunk_count"] == 1
    assert trace["chunking"]["chunking_methods"] == ["deterministic-character-overlap"]
    assert document_chunks.total_chunks == 1
    chunk = document_chunks.chunks[0]
    assert chunk.metadata["document_id"] == uploaded.document_id
    assert chunk.metadata["source_type"] == "url"
    assert chunk.metadata["source"] == "https://example.com/chinh-sach"
    assert chunk.metadata["url"] == "https://example.com/chinh-sach"


def test_local_pdf_provider_uploads_text_chunks(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    uploaded = provider.upload_text(title="Ghi chu", text="Noi dung tu nguoi dung")
    document_chunks = provider.document_chunks(document_id=uploaded.document_id)

    assert uploaded.name == "Ghi-chu.txt"
    assert document_chunks.total_chunks == 1
    chunk = document_chunks.chunks[0]
    assert chunk.metadata["document_id"] == uploaded.document_id
    assert chunk.metadata["source_type"] == "text"
    assert chunk.text == "Noi dung tu nguoi dung"


def test_local_pdf_provider_retrieves_matching_chunks(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANK_PROVIDER", "score")
    _mock_openai_client(monkeypatch)
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_pdf_with_markdown",
        lambda path, **kwargs: LoadedPdfDocument(
            markdown="# Warranty\nPin VF8 duoc bao hanh 8 nam.",
            chunks=[
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
        ),
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
        == "source_ingestion -> bm25 + dense -> rrf -> rerank"
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
    assert pipeline_trace["rrf_fusion"]["tech"]["method"] == "reciprocal_rank_fusion"
    assert pipeline_trace["rrf_fusion"]["tech"]["rrf_k"] == 60
    assert pipeline_trace["rrf_fusion"]["input"]["bm25_results"][0]["retriever"] == "bm25"
    assert pipeline_trace["rrf_fusion"]["output"][0]["retriever"] == "hybrid"
    rrf_contributions = pipeline_trace["rrf_fusion"]["output"][0]["contributions"]
    assert rrf_contributions["bm25"]["retriever"] == "bm25"
    assert rrf_contributions["dense"]["retriever"] == "dense"
    assert rrf_contributions["total_rrf_score"] > 0
    assert pipeline_trace["thresholds"]["pre_fusion"]["bm25_original_count"] >= 1
    assert pipeline_trace["thresholds"]["pre_fusion"]["thresholds_applied"] is False
    assert pipeline_trace["thresholds"]["fusion"]["fusion_min_score"] is None
    assert pipeline_trace["thresholds"]["rerank"]["final_evidence_count"] == len(results)
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
