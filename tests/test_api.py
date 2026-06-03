from pathlib import Path

from pytest import MonkeyPatch

from agentic_rag.api import (
    AnswerRequest,
    SourceTextRequest,
    SourceUrlRequest,
    _small_talk_answer,
    _stream_answer_events,
    _stream_direct_answer_events,
    answer_question,
    health,
    source_debug,
    source_raw,
    upload_text_source,
    upload_url_source,
)
from agentic_rag.core.contracts import Chunk
from agentic_rag.generation.answering import format_evidence_context
from agentic_rag.ingestion.url import LoadedUrlDocument
from agentic_rag.integrations.local_pdf.providers import LocalPdfEvidenceProvider
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
    assert Path(str(response.path)).name == f"{uploaded.document_id}.pdf"


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
