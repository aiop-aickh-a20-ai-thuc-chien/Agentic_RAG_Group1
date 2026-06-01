from pytest import MonkeyPatch

from agentic_rag.core.contracts import Answer
from agentic_rag.generation.answering import (
    NOT_FOUND_ANSWER,
    AnswerDelta,
    AnswerDone,
    apply_citation_markers,
    format_evidence_context,
    generate_answer,
    stream_answer,
    validate_answer_with_citations,
)
from agentic_rag.testing.fixtures import sample_answer, sample_search_results


class FakeClientWithReferenceList:
    def complete(self, prompt: str) -> str:
        return "Pin bao hanh 8 nam. [1]\n\n[1] vinfast_warranty.pdf\n[2] vinfast_warranty.pdf"

    def stream_complete(self, prompt: str):  # type: ignore[no-untyped-def]
        yield self.complete(prompt)


def test_generate_answer_returns_not_found_without_evidence() -> None:
    answer = generate_answer(
        question="Pin bao hanh bao lau?",
        evidence_context="",
        evidence_chunks=[],
    )

    assert answer == Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[])


def test_generate_answer_uses_evidence_fallback_without_openai_key(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "agentic_rag.generation.answering.configured_llm_client",
        lambda: None,
    )
    evidence_chunks = sample_search_results()

    answer = generate_answer(
        question="Pin bao hanh bao lau?",
        evidence_context=format_evidence_context(evidence_chunks),
        evidence_chunks=evidence_chunks,
    )

    assert answer.status == "answered"
    assert answer.answer.startswith(evidence_chunks[0].chunk.text)
    assert f"{evidence_chunks[0].chunk.text} [1]" in answer.answer
    assert "[2]" in answer.answer
    assert answer.citations[0].chunk_id == evidence_chunks[0].chunk.chunk_id


def test_generate_answer_removes_llm_reference_list(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentic_rag.generation.answering.configured_llm_client",
        lambda: FakeClientWithReferenceList(),
    )

    answer = generate_answer(
        question="Pin bao hanh bao lau?",
        evidence_context=format_evidence_context(sample_search_results()),
        evidence_chunks=sample_search_results(),
    )

    assert answer.answer == "Pin bao hanh 8 nam. [1]"
    assert "vinfast_warranty.pdf" not in answer.answer


def test_validate_answer_accepts_citations_from_evidence() -> None:
    evidence_chunks = sample_search_results()
    citation = {
        "source": "vinfast_warranty.pdf",
        "chunk_id": "pdf_001_p12_c01",
        "page": 12,
    }

    assert validate_answer_with_citations("Pin bao hanh 8 nam.", [citation], evidence_chunks)


def test_validate_answer_rejects_fake_chunk_citation() -> None:
    citation = {
        "source": "vinfast_warranty.pdf",
        "chunk_id": "fake_chunk",
        "page": 12,
    }

    assert not validate_answer_with_citations(
        "Pin bao hanh 8 nam.",
        [citation],
        sample_search_results(),
    )


def test_validate_answer_rejects_wrong_source_for_known_chunk() -> None:
    citation = {
        "source": "wrong.pdf",
        "chunk_id": "pdf_001_p12_c01",
        "page": 12,
    }

    assert not validate_answer_with_citations(
        "Pin bao hanh 8 nam.",
        [citation],
        sample_search_results(),
    )


def test_validate_answer_accepts_not_found_without_citations() -> None:
    assert validate_answer_with_citations(NOT_FOUND_ANSWER, [], sample_search_results())


def test_format_evidence_context_includes_source_and_chunk_id() -> None:
    context = format_evidence_context(sample_search_results())

    assert "pdf_001_p12_c01" in context
    assert "vinfast_warranty.pdf" in context


def test_apply_citation_markers_adds_marker_to_supported_sentence() -> None:
    citations = sample_answer().citations

    marked_answer = apply_citation_markers("Pin bao hanh 8 nam.", citations)

    assert marked_answer == "Pin bao hanh 8 nam. [1]"


def test_apply_citation_markers_distributes_markers_across_sentences() -> None:
    citations = sample_search_results()[:2]
    citation_models = [
        sample_answer().citations[0],
        sample_answer().citations[0].model_copy(update={"chunk_id": citations[1].chunk.chunk_id}),
    ]

    marked_answer = apply_citation_markers(
        "Pin bao hanh 8 nam. Dieu kien bao hanh nam trong tai lieu.",
        citation_models,
    )

    assert marked_answer == ("Pin bao hanh 8 nam. [1] Dieu kien bao hanh nam trong tai lieu. [2]")


def test_stream_answer_yields_deltas_and_final_answer_without_llm_key(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "agentic_rag.generation.answering.configured_llm_client",
        lambda: None,
    )
    evidence_chunks = sample_search_results()

    events = list(
        stream_answer(
            question="Pin bao hanh bao lau?",
            evidence_context=format_evidence_context(evidence_chunks),
            evidence_chunks=evidence_chunks,
        )
    )

    deltas = [event.text for event in events if isinstance(event, AnswerDelta)]
    done_events = [event for event in events if isinstance(event, AnswerDone)]

    streamed_text = "".join(deltas)
    assert "[1]" in streamed_text
    assert "[2]" in streamed_text
    assert len(done_events) == 1
    assert done_events[0].answer.status == "answered"
    assert "[1]" in done_events[0].answer.answer
    assert "[2]" in done_events[0].answer.answer
