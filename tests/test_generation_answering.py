from pytest import MonkeyPatch

from agentic_rag.core.contracts import Answer, Chunk, SearchResult
from agentic_rag.generation.answering import (
    NOT_FOUND_ANSWER,
    AnswerDelta,
    AnswerDone,
    apply_citation_markers,
    build_grounded_prompt,
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


class FakeClientWithStructuredAnswer:
    def complete(self, prompt: str) -> str:
        return (
            '{"answer": "Noi dung chinh tu website ve chinh sach bao hanh.", '
            '"status": "answered", "used_citation_ids": [2], '
            '"reason": "supported by URL chunk"}'
        )

    def stream_complete(self, prompt: str):  # type: ignore[no-untyped-def]
        yield self.complete(prompt)


class FakeClientWithInvalidCitation:
    def complete(self, prompt: str) -> str:
        return "Pin bao hanh 8 nam. [99]"

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


def test_generate_answer_accepts_structured_citation_ids(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentic_rag.generation.answering.configured_llm_client",
        lambda: FakeClientWithStructuredAnswer(),
    )

    answer = generate_answer(
        question="Website noi ve gi?",
        evidence_context=format_evidence_context(sample_search_results()),
        evidence_chunks=sample_search_results(),
    )

    assert answer.status == "answered"
    assert answer.answer == "Noi dung chinh tu website ve chinh sach bao hanh. [1]"
    assert len(answer.citations) == 1
    assert answer.citations[0].chunk_id == "url_001_smain_c01"


def test_generate_answer_renumbers_non_sequential_inline_citations(
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeClientWithSecondCitation:
        def complete(self, prompt: str) -> str:
            return "Noi dung website noi ve chinh sach bao hanh. [2]"

        def stream_complete(self, prompt: str):  # type: ignore[no-untyped-def]
            yield self.complete(prompt)

    monkeypatch.setattr(
        "agentic_rag.generation.answering.configured_llm_client",
        lambda: FakeClientWithSecondCitation(),
    )

    answer = generate_answer(
        question="Website noi ve gi?",
        evidence_context=format_evidence_context(sample_search_results()),
        evidence_chunks=sample_search_results(),
    )

    assert answer.answer == "Noi dung website noi ve chinh sach bao hanh. [1]"
    assert len(answer.citations) == 1
    assert answer.citations[0].chunk_id == "url_001_smain_c01"


def test_generate_answer_rejects_invalid_inline_citation_marker(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentic_rag.generation.answering.configured_llm_client",
        lambda: FakeClientWithInvalidCitation(),
    )

    answer = generate_answer(
        question="Pin bao hanh bao lau?",
        evidence_context=format_evidence_context(sample_search_results()),
        evidence_chunks=sample_search_results(),
    )

    assert answer == Answer(answer=NOT_FOUND_ANSWER, status="not_found", citations=[])


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


def test_format_evidence_context_includes_price_source_metadata() -> None:
    vehicle_price = SearchResult(
        chunk=Chunk(
            chunk_id="vf3-price",
            text="VF 3 Eco co gia ban tu 262.100.700 VND.",
            metadata={
                "source": "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-dien-vf3.html",
                "source_type": "url",
                "url": "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-dien-vf3.html",
                "title": "Dat coc xe dien VF 3",
            },
        ),
        score=0.9,
        rank=1,
        retriever="hybrid",
    )
    accessory_price = SearchResult(
        chunk=Chunk(
            chunk_id="vf3-accessory",
            text="Bo thanh ngang gia noc VF 3 co gia 2.074.000 VND.",
            metadata={
                "source": "https://shop.vinfastauto.com/vn_vi/5007",
                "source_type": "url",
                "url": "https://shop.vinfastauto.com/vn_vi/5007",
                "title": "Phu kien VF 3",
            },
        ),
        score=0.8,
        rank=2,
        retriever="hybrid",
    )

    context = format_evidence_context([vehicle_price, accessory_price])

    # format_evidence_context uses source/page/section; metadata enrichment is
    # handled by build_evidence_context in fusion.py (agent path).
    assert "vf3-price" in context
    assert "vf3-accessory" in context
    assert "source=https://shop.vinfastauto.com" in context


def test_grounded_prompt_allows_partial_supported_answers() -> None:
    prompt = build_grounded_prompt(
        question="So sanh VF3, VF5 va VF8",
        evidence_context=format_evidence_context(sample_search_results()),
    )

    assert "Every factual sentence must include at least one evidence marker" in prompt
    assert "If the evidence is insufficient" in prompt
    assert NOT_FOUND_ANSWER in prompt
    assert "Do not invent facts or citations" in prompt


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
