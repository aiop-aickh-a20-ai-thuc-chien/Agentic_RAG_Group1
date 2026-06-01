from agentic_rag.core.contracts import Answer, Chunk, Citation, SearchResult
from agentic_rag.integrations.ragflow import (
    answer_from_ragflow_payload,
    chunk_from_ragflow_payload,
    citations_from_search_results,
    search_result_from_ragflow_hit,
)
from agentic_rag.testing.fixtures import (
    sample_ragflow_answer_payload,
    sample_ragflow_chunk_payload,
    sample_ragflow_hit_payload,
)


def test_ragflow_chunk_payload_converts_to_shared_chunk() -> None:
    chunk = chunk_from_ragflow_payload(sample_ragflow_chunk_payload())

    assert isinstance(chunk, Chunk)
    assert chunk.chunk_id == "ragflow_pdf_001_p12_c01"
    assert chunk.metadata["source"] == "vinfast_warranty.pdf"
    assert chunk.metadata["page"] == 12


def test_ragflow_hit_payload_converts_to_search_result() -> None:
    result = search_result_from_ragflow_hit(sample_ragflow_hit_payload())

    assert isinstance(result, SearchResult)
    assert result.rank == 1
    assert result.score == 0.93
    assert result.retriever == "ragflow"


def test_citations_are_derived_from_evidence_metadata() -> None:
    result = search_result_from_ragflow_hit(sample_ragflow_hit_payload())

    citations = citations_from_search_results([result])

    assert citations == [
        Citation(
            source="vinfast_warranty.pdf",
            chunk_id="ragflow_pdf_001_p12_c01",
            page=12,
            section="warranty",
        )
    ]


def test_ragflow_answer_payload_converts_to_shared_answer() -> None:
    answer = answer_from_ragflow_payload(sample_ragflow_answer_payload())

    assert isinstance(answer, Answer)
    assert answer.status == "answered"
    assert answer.citations[0].chunk_id == "ragflow_pdf_001_p12_c01"


def test_ragflow_answer_can_derive_citations_from_evidence() -> None:
    result = search_result_from_ragflow_hit(sample_ragflow_hit_payload())

    answer = answer_from_ragflow_payload(
        {"answer": "Pin cao ap duoc bao hanh 8 nam."},
        evidence_chunks=[result],
    )

    assert answer.status == "answered"
    assert answer.citations[0].chunk_id == result.chunk.chunk_id


def test_empty_ragflow_answer_becomes_not_found_without_citations() -> None:
    result = search_result_from_ragflow_hit(sample_ragflow_hit_payload())

    answer = answer_from_ragflow_payload({"answer": ""}, evidence_chunks=[result])

    assert answer == Answer(answer="", status="not_found", citations=[])
