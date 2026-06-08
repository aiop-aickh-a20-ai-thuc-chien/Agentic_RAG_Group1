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
    list_sources,
    source_debug,
    source_raw,
    upload_text_source,
    upload_url_source,
)
from agentic_rag.core.contracts import Chunk
from agentic_rag.generation.answering import format_evidence_context
from agentic_rag.ingestion.url import LoadedUrlDocument
from agentic_rag.integrations.local_pdf.providers import LocalPdfEvidenceProvider
from agentic_rag.integrations.local_pdf.storage import StoredRawSource
from agentic_rag.testing.fixtures import sample_search_results


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
