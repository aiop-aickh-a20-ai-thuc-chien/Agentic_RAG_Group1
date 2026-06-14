from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse
from pytest import MonkeyPatch

from agentic_rag.api import (
    AnswerRequest,
    SourceTextRequest,
    SourceUrlRequest,
    _small_talk_answer,
    _stream_answer_events,
    _stream_direct_answer_events,
    answer_question,
    delete_all_sources,
    delete_source,
    health,
    internal_dedup_candidates,
    knowledge_quality_report,
    list_sources,
    scan_knowledge_quality,
    source_debug,
    source_quality,
    source_raw,
    upload_text_source,
    upload_url_source,
)
from agentic_rag.core.contracts import (
    Answer,
    Chunk,
    KnowledgeQualityReport,
    WorkflowRunOutput,
)
from agentic_rag.generation.answering import format_evidence_context
from agentic_rag.ingestion.url import LoadedUrlDocument
from agentic_rag.integrations.local_pdf.providers import LocalPdfEvidenceProvider
from agentic_rag.integrations.local_pdf.storage import StoredRawSource
from agentic_rag.testing.fixtures import sample_search_results


@pytest.fixture(autouse=True)
def _disable_model_runtime_env(monkeypatch: MonkeyPatch) -> Iterator[None]:
    from agentic_rag.model_runtime.factory import clear_model_runtime_caches

    clear_model_runtime_caches()
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.delenv("VECTOR_STORE_PROVIDER", raising=False)
    monkeypatch.delenv("DENSE_VECTOR_STORE", raising=False)
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("QDRANT_API_KEY", raising=False)
    monkeypatch.delenv("QDRANT_COLLECTION", raising=False)
    # api.py chạy load_dotenv() lúc import — phải gỡ NEON_CONNECTION kẻo upload
    # trong test ghi thật vào bảng dedup_candidates trên Neon.
    monkeypatch.delenv("NEON_CONNECTION", raising=False)
    monkeypatch.setattr("agentic_rag.autodata_eval.db._conninfo", None)
    monkeypatch.setattr("agentic_rag.model_runtime.config.load_local_env", lambda: None)
    monkeypatch.setattr("agentic_rag.retrieval.config.load_local_env", lambda: None)
    yield
    clear_model_runtime_caches()


class FakeUploadProvider:
    def __init__(self) -> None:
        self.uploaded: tuple[str, bytes, str | None] | None = None

    def upload_document(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> object:
        self.uploaded = (filename, content, content_type)
        return type(
            "UploadedDocument",
            (),
            {
                "dataset_id": "dataset-1",
                "document_id": "doc-1",
                "name": filename,
                "parse_started": True,
            },
        )()


def test_health_endpoint_shape(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("EVIDENCE_PROVIDER", "local_pdf")
    result = health()
    assert result["status"] == "ok"
    assert result["evidence_provider"] == "local_pdf"


def test_health_endpoint_reports_local_pdf_backends(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("EVIDENCE_PROVIDER", "local_pdf")
    monkeypatch.setenv("LOCAL_SOURCE_STORE", "s3")
    monkeypatch.setenv("AWS_S3_BUCKET", "rag-bucket")
    monkeypatch.setenv("AWS_S3_PREFIX", "sources")
    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://example-qdrant")
    monkeypatch.setenv("QDRANT_COLLECTION", "chunks")

    result = health()

    assert result["source_store"] == "s3"
    assert result["s3_bucket_configured"] == "true"
    assert result["s3_prefix"] == "sources"
    assert result["dense_vector_store"] == "qdrant"
    assert result["qdrant_url_configured"] == "true"
    assert result["qdrant_collection"] == "chunks"


def test_answer_endpoint_returns_not_found_without_evidence(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("EVIDENCE_PROVIDER", "mock")

    answer = answer_question(AnswerRequest(question="Pin bao hanh bao lau?"))

    assert answer.status == "not_found"
    assert answer.citations == []


def test_answer_endpoint_uses_mock_evidence_when_explicitly_enabled(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("EVIDENCE_PROVIDER", "mock")

    answer = answer_question(
        AnswerRequest(question="Pin bao hanh bao lau?", use_mock_evidence=True)
    )

    assert answer.status == "answered"
    assert answer.citations


def test_answer_endpoint_handles_small_talk_without_evidence(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentic_rag.api.evidence_for_question",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("retrieval should not run")),
    )

    answer = answer_question(AnswerRequest(question="Xin chào", use_mock_evidence=False))

    assert answer.status == "answered"
    assert answer.citations == []
    assert "tải tài liệu" in answer.answer


def test_answer_endpoint_passes_excluded_dedup_layers_to_agent(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_run_agent(**kwargs: Any) -> WorkflowRunOutput:
        seen.update(kwargs)
        return WorkflowRunOutput(
            answer=Answer(answer="ok", citations=[], status="answered"),
        )

    monkeypatch.setenv("AGENT_MODE", "true")
    monkeypatch.setattr("agentic_rag.api.source_provider_from_env", lambda: object())
    monkeypatch.setattr("agentic_rag.api.run_agent", fake_run_agent)

    answer = answer_question(
        AnswerRequest(
            question="Pin bao hanh bao lau?",
            document_ids=["doc-1"],
            exclude_dedup_layers=["exact_sha256"],
        )
    )

    assert answer.answer == "ok"
    assert seen["request"].document_ids == ["doc-1"]
    assert seen["request"].exclude_dedup_layers == ["exact_sha256"]


def test_stream_answer_events_include_deltas_citations_and_done() -> None:
    evidence_chunks = sample_search_results()
    events = list(
        _stream_answer_events(
            question="Pin bao hanh bao lau?",
            evidence_context=format_evidence_context(evidence_chunks),
            evidence_chunks=evidence_chunks,
            provider="mock",
        )
    )

    assert events[0].startswith("event: answer_delta\n")
    assert any(event.startswith("event: citation\n") for event in events)
    assert events[-1].startswith("event: done\n")
    assert '"status": "answered"' in events[-1]


def test_stream_direct_answer_events_do_not_emit_citations() -> None:
    answer = _small_talk_answer("cảm ơn")
    assert answer is not None

    events = list(_stream_direct_answer_events(question="cảm ơn", answer=answer))

    assert events[0].startswith("event: answer_delta\n")
    assert not any(event.startswith("event: citation\n") for event in events)
    assert events[-1].startswith("event: done\n")
    assert '"citations": []' in events[-1]


def test_text_source_uploads_plain_text_to_ragflow(monkeypatch: MonkeyPatch) -> None:
    provider = FakeUploadProvider()
    monkeypatch.setenv("EVIDENCE_PROVIDER", "ragflow")
    monkeypatch.setattr("agentic_rag.api.ragflow_provider_from_env", lambda: provider)

    response = upload_text_source(
        SourceTextRequest(title="Ghi chú của tôi", text="Noi dung tai lieu")
    )

    assert response.document_id == "doc-1"
    assert provider.uploaded is not None
    filename, content, content_type = provider.uploaded
    assert filename == "Ghi-ch-c-a-t-i.txt"
    assert content == b"Noi dung tai lieu"
    assert content_type == "text/plain; charset=utf-8"


def test_url_source_fetches_text_and_uploads_to_ragflow(monkeypatch: MonkeyPatch) -> None:
    provider = FakeUploadProvider()
    monkeypatch.setenv("EVIDENCE_PROVIDER", "ragflow")
    monkeypatch.setattr("agentic_rag.api.ragflow_provider_from_env", lambda: provider)
    monkeypatch.setattr(
        "agentic_rag.api._fetch_url_text",
        lambda url: "<html><body><h1>Tieu de</h1><p>Noi dung URL</p></body></html>",
    )

    response = upload_url_source(SourceUrlRequest(url="https://example.com/docs/page"))

    assert response.document_id == "doc-1"
    assert provider.uploaded is not None
    filename, content, content_type = provider.uploaded
    assert filename == "example.com-docs-page.txt"
    assert b"Source URL: https://example.com/docs/page" in content
    assert b"Tieu de" in content
    assert b"Noi dung URL" in content
    assert content_type == "text/plain; charset=utf-8"


def test_url_source_uses_local_provider_when_configured(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    monkeypatch.setenv("EVIDENCE_PROVIDER", "local_pdf")
    monkeypatch.setattr("agentic_rag.api.source_provider_from_env", lambda: provider)
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_url_with_artifacts",
        lambda url, **kwargs: LoadedUrlDocument(
            markdown="# URL\nNoi dung URL",
            chunks=[
                Chunk(
                    chunk_id="url_doc_c0001",
                    text="Noi dung URL",
                    metadata={"source": url, "source_type": "url", "url": url},
                )
            ],
            artifacts=None,
        ),
    )

    response = upload_url_source(SourceUrlRequest(url="https://example.com/docs/page"))

    assert response.provider == "local_pdf"
    assert response.dataset_id == "local_pdf"
    assert response.name == "example.com-docs-page.txt"
    debug = source_debug(response.document_id)
    assert debug.provider == "local_pdf"
    assert debug.source_type == "url"
    assert debug.markdown == "# URL\nNoi dung URL"
    assert debug.chunk_input == "Noi dung URL"
    assert debug.chunk_input_type == "parsed_sections"
    assert debug.total_chunks == 1
    assert debug.chunks[0].chunk.text == "Noi dung URL"


def test_raw_source_returns_local_pdf_file(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    monkeypatch.setenv("EVIDENCE_PROVIDER", "local_pdf")
    monkeypatch.setattr("agentic_rag.api.source_provider_from_env", lambda: provider)

    uploaded = provider.upload_document(
        filename="debug.pdf",
        content=b"%PDF-1.4",
        content_type="application/pdf",
        start_parse=False,
    )

    response = source_raw(uploaded.document_id)

    assert response.media_type == "application/pdf"
    assert isinstance(response, FileResponse)
    assert Path(str(response.path)).name == f"{uploaded.document_id}.pdf"


def test_raw_source_streams_cloud_raw_bytes(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    class FakeCloudSourceStore:
        def read_raw(self, document_id: str) -> StoredRawSource:
            return StoredRawSource(
                content=b"%PDF-1.4",
                content_type="application/pdf",
                name=f"{document_id}.pdf",
            )

    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        source_store=cast(Any, FakeCloudSourceStore()),
    )
    monkeypatch.setenv("EVIDENCE_PROVIDER", "local_pdf")
    monkeypatch.setattr("agentic_rag.api.source_provider_from_env", lambda: provider)

    response = source_raw("doc-1")

    assert response.media_type == "application/pdf"
    assert response.body == b"%PDF-1.4"


def test_raw_cloud_source_encodes_unicode_filename(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeCloudSourceStore:
        def read_raw(self, document_id: str) -> StoredRawSource:
            return StoredRawSource(
                content=b"%PDF-1.4",
                content_type="application/pdf",
                name="Tài liệu tiếng Việt.pdf",
            )

    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        source_store=cast(Any, FakeCloudSourceStore()),
    )
    monkeypatch.setattr("agentic_rag.api.source_provider_from_env", lambda: provider)

    response = source_raw("doc-1")

    assert response.headers["content-disposition"] == (
        "inline; filename*=utf-8''T%C3%A0i%20li%E1%BB%87u%20ti%E1%BA%BFng%20Vi%E1%BB%87t.pdf"
    )
    response.headers["content-disposition"].encode("latin-1")


def test_raw_cloud_source_encodes_header_control_characters(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeCloudSourceStore:
        def read_raw(self, document_id: str) -> StoredRawSource:
            return StoredRawSource(
                content=b"source",
                content_type="text/plain; charset=utf-8",
                name='report"\r\nX-Test: injected.txt',
            )

    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        source_store=cast(Any, FakeCloudSourceStore()),
    )
    monkeypatch.setattr("agentic_rag.api.source_provider_from_env", lambda: provider)

    response = source_raw("doc-1")
    disposition = response.headers["content-disposition"]

    assert disposition.startswith("inline; filename*=utf-8''")
    assert "%22" in disposition
    assert "%0D%0A" in disposition
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert response.body == b"source"
    assert response.media_type == "text/plain; charset=utf-8"


def test_delete_source_returns_bad_gateway_for_qdrant_failure(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    monkeypatch.setattr("agentic_rag.api.source_provider_from_env", lambda: provider)
    monkeypatch.setattr(
        provider,
        "delete_document",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("Qdrant deletion failed; source storage was not deleted.")
        ),
    )

    with pytest.raises(HTTPException) as raised:
        delete_source("doc-1")

    assert raised.value.status_code == 502
    assert "source storage was not deleted" in str(raised.value.detail)


def test_delete_all_sources_returns_bad_gateway_for_qdrant_failure(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    monkeypatch.setattr("agentic_rag.api.source_provider_from_env", lambda: provider)
    monkeypatch.setattr(
        provider,
        "delete_all_documents",
        lambda: (_ for _ in ()).throw(
            RuntimeError("Qdrant deletion failed; source storage was not deleted.")
        ),
    )

    with pytest.raises(HTTPException) as raised:
        delete_all_sources()

    assert raised.value.status_code == 502
    assert "source storage was not deleted" in str(raised.value.detail)


def test_text_source_uses_local_provider_when_configured(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    monkeypatch.setenv("EVIDENCE_PROVIDER", "local_pdf")
    monkeypatch.setattr("agentic_rag.api.source_provider_from_env", lambda: provider)
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

    response = upload_text_source(SourceTextRequest(title="Ghi chu", text="Noi dung"))

    assert response.provider == "local_pdf"
    assert response.dataset_id == "local_pdf"
    assert response.name == "Ghi-chu.txt"


def test_list_sources_returns_local_documents(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    monkeypatch.setenv("EVIDENCE_PROVIDER", "local_pdf")
    monkeypatch.setattr("agentic_rag.api.source_provider_from_env", lambda: provider)
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

    uploaded = upload_text_source(SourceTextRequest(title="Ghi chu", text="Noi dung"))
    response = list_sources()

    assert response.provider == "local_pdf"
    assert len(response.sources) == 1
    assert response.sources[0].document_id == uploaded.document_id
    assert response.sources[0].source_type == "text"
    assert response.sources[0].total_chunks == 1
    assert response.sources[0].chunks == []

    response_with_chunks = list_sources(include_chunks=True)
    assert response_with_chunks.sources[0].chunks[0].chunk.text == "Noi dung"


def test_internal_dedup_candidates_returns_local_pairs(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentic_rag.autodata_eval import dedup_store

    def fake_load_text_chunks(text: str, **kwargs: str) -> list[Chunk]:
        source = kwargs["source"]
        source_key = "a" if source.startswith("Doc-A") else "b"
        return [
            Chunk(
                chunk_id=f"text_{source_key}_c0001",
                text=text,
                metadata={"source": source, "source_type": "text"},
            )
        ]

    # In-memory thay cho bảng Neon: upload ghi vào đây, endpoint đọc từ đây.
    stored_rows: dict[str, dict[str, object]] = {}

    def fake_replace_document(document_id: str, rows: list[dict[str, object]]) -> int:
        for key in [
            k for k, v in stored_rows.items() if v.get("duplicate_document_id") == document_id
        ]:
            stored_rows.pop(key)
        for row in rows:
            stored_rows[str(row["id"])] = row
        return len(rows)

    def fake_query(
        *,
        layer: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, object]:
        rows = [r for r in stored_rows.values() if not layer or r.get("layer") == layer]
        page = rows[offset : offset + limit]
        return {
            "items": [dedup_store._row_to_item(row) for row in page],
            "total": len(rows),
            "limit": limit,
            "offset": offset,
            "counts": {
                "pairs": len(stored_rows),
                "unique_candidates": len(
                    {r.get("duplicate_chunk_id") for r in stored_rows.values()}
                ),
                "exact": sum(1 for r in stored_rows.values() if r.get("layer") == "exact_sha256"),
                "simhash": sum(1 for r in stored_rows.values() if r.get("layer") == "simhash"),
                "embedding": sum(
                    1 for r in stored_rows.values() if r.get("layer") == "embedding_similarity"
                ),
            },
        }

    monkeypatch.setenv("EVIDENCE_PROVIDER", "local_pdf")
    monkeypatch.setenv("DEDUP_ENABLE_EMBEDDING", "false")
    monkeypatch.setattr(dedup_store, "replace_document_candidates", fake_replace_document)
    monkeypatch.setattr(dedup_store, "query_candidates", fake_query)
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        fake_load_text_chunks,
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        lambda chunks: {"enabled": False, "vector_store": "turbovec"},
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    monkeypatch.setattr("agentic_rag.api.source_provider_from_env", lambda: provider)

    first = provider.upload_text(title="Doc A", text="Same body")
    provider.upload_text(title="Doc B", text="Same body")
    response = internal_dedup_candidates(layer="exact_sha256")

    assert response.provider == "local_pdf"
    assert response.total == 1
    assert response.counts.exact == 1
    assert response.items[0].layer == "exact_sha256"
    assert response.items[0].canonical is not None
    assert response.items[0].canonical.document_id == first.document_id
    assert response.items[0].duplicate.document_id != first.document_id


def test_source_quality_returns_local_conflict_report(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_load_text_chunks(text: str, **kwargs: str) -> list[Chunk]:
        source_stem = kwargs["source"].removesuffix(".txt").lower()
        return [
            Chunk(
                chunk_id=f"text_{source_stem}_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ]

    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    monkeypatch.setenv("EVIDENCE_PROVIDER", "local_pdf")
    monkeypatch.setattr("agentic_rag.api.source_provider_from_env", lambda: provider)
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        fake_load_text_chunks,
    )

    base = upload_text_source(SourceTextRequest(title="Base", text="VF8 duoc bao hanh 8 nam."))
    update = upload_text_source(SourceTextRequest(title="Update", text="VF8 duoc bao hanh 6 nam."))

    report = source_quality(base.document_id)

    assert report.metadata["provider"] == "local_pdf"
    assert report.metadata["selected_document_ids"] == [base.document_id]
    assert len(report.findings) == 1
    assert report.findings[0].kind == "conflict"
    assert set(report.findings[0].chunk_ids) == {
        f"{base.document_id}_c0001",
        f"{update.document_id}_c0001",
    }
    assert len(report.facts) == 2


def test_knowledge_quality_scan_can_filter_and_refresh_local_metadata(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_load_text_chunks(text: str, **kwargs: str) -> list[Chunk]:
        source_stem = kwargs["source"].removesuffix(".txt").lower()
        return [
            Chunk(
                chunk_id=f"text_{source_stem}_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ]

    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    monkeypatch.setenv("EVIDENCE_PROVIDER", "local_pdf")
    monkeypatch.setattr("agentic_rag.api.source_provider_from_env", lambda: provider)
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        fake_load_text_chunks,
    )
    base = upload_text_source(SourceTextRequest(title="Base", text="VF8 duoc bao hanh 8 nam."))
    update = upload_text_source(SourceTextRequest(title="Update", text="VF8 duoc bao hanh 6 nam."))

    filtered = knowledge_quality_report(document_ids=[update.document_id])
    rescanned = scan_knowledge_quality()

    assert filtered.metadata["selected_document_ids"] == [update.document_id]
    assert len(filtered.findings) == 1
    assert rescanned.metadata["selected_document_ids"] is None
    assert len(rescanned.findings) == 1
    for document_id in (base.document_id, update.document_id):
        chunk = provider.document_chunks(document_id=document_id).chunks[0]
        assert chunk.metadata["knowledge_quality"]["conflict_count"] == 1


def test_knowledge_quality_endpoints_reject_non_local_provider(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("EVIDENCE_PROVIDER", "ragflow")
    monkeypatch.setattr("agentic_rag.api.source_provider_from_env", lambda: object())

    with pytest.raises(HTTPException) as source_raised:
        source_quality("doc-1")
    with pytest.raises(HTTPException) as aggregate_raised:
        knowledge_quality_report()
    with pytest.raises(HTTPException) as scan_raised:
        scan_knowledge_quality()

    assert source_raised.value.status_code == 404
    assert aggregate_raised.value.status_code == 404
    assert scan_raised.value.status_code == 404
    assert "local PDF" in str(source_raised.value.detail)


def test_knowledge_quality_endpoints_forward_selected_methods(
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, list[str] | None, list[str] | None]] = []

        def knowledge_quality_report(
            self,
            *,
            document_ids: list[str] | None = None,
            methods: list[str] | None = None,
        ) -> KnowledgeQualityReport:
            self.calls.append(("report", document_ids, methods))
            return KnowledgeQualityReport(metadata={"methods": methods or []})

        def rescan_knowledge_quality(
            self,
            *,
            document_ids: list[str] | None = None,
            methods: list[str] | None = None,
        ) -> KnowledgeQualityReport:
            self.calls.append(("scan", document_ids, methods))
            return KnowledgeQualityReport(metadata={"methods": methods or []})

    provider = FakeProvider()
    monkeypatch.setattr("agentic_rag.api._local_pdf_quality_provider", lambda: provider)

    source_quality("doc-1", methods="metadata_rules,semantic_rules")
    knowledge_quality_report(methods="semantic_rules")
    scan_knowledge_quality(methods="deterministic_v1,metadata_rules")

    assert provider.calls == [
        ("report", ["doc-1"], ["metadata_rules", "semantic_rules"]),
        ("report", None, ["semantic_rules"]),
        ("scan", None, ["deterministic_v1", "metadata_rules"]),
    ]


def test_knowledge_quality_endpoint_rejects_unknown_method(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("agentic_rag.api._local_pdf_quality_provider", lambda: object())

    with pytest.raises(HTTPException) as raised:
        knowledge_quality_report(methods="unknown")

    assert raised.value.status_code == 422


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (
            "agentic_rag.ingestion.knowledge_quality.KnowledgeQualityConfigurationError",
            422,
        ),
        (
            "agentic_rag.ingestion.knowledge_quality.KnowledgeQualityInvocationError",
            502,
        ),
    ],
)
def test_knowledge_quality_endpoint_maps_model_method_errors(
    monkeypatch: MonkeyPatch,
    error: str,
    status_code: int,
) -> None:
    module_name, class_name = error.rsplit(".", 1)
    error_type = getattr(__import__(module_name, fromlist=[class_name]), class_name)

    class FakeProvider:
        def knowledge_quality_report(self, **kwargs: object) -> KnowledgeQualityReport:
            raise error_type("quality method failed")

    monkeypatch.setattr(
        "agentic_rag.api._local_pdf_quality_provider",
        lambda: FakeProvider(),
    )

    with pytest.raises(HTTPException) as raised:
        knowledge_quality_report(methods="semantic_verifier")

    assert raised.value.status_code == status_code
