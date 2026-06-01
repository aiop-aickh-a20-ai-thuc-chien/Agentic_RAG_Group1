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
    upload_text_source,
    upload_url_source,
)
from agentic_rag.generation.answering import format_evidence_context
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


def test_health_endpoint_shape() -> None:
    assert health() == {"status": "ok"}


def test_answer_endpoint_uses_mock_evidence_by_default(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("EVIDENCE_PROVIDER", "mock")

    answer = answer_question(AnswerRequest(question="Pin bao hanh bao lau?"))

    assert answer.status == "answered"
    assert answer.citations


def test_answer_endpoint_can_disable_mock_evidence(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("EVIDENCE_PROVIDER", "mock")

    answer = answer_question(
        AnswerRequest(question="Pin bao hanh bao lau?", use_mock_evidence=False)
    )

    assert answer.status == "not_found"
    assert answer.citations == []


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
