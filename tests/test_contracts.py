import pytest
from pydantic import ValidationError

from agentic_rag.core.contracts import Answer, Chunk, Citation, SearchResult


def test_chunk_keeps_stack_neutral_metadata() -> None:
    chunk = Chunk(
        chunk_id="pdf_001_p12_c01",
        text="Pin cao ap duoc bao hanh 8 nam.",
        metadata={
            "source": "vinfast_warranty.pdf",
            "source_type": "pdf",
            "file_name": "vinfast_warranty.pdf",
            "url": None,
            "page": 12,
            "section": None,
        },
    )

    assert chunk.chunk_id == "pdf_001_p12_c01"
    assert chunk.metadata["source_type"] == "pdf"
    assert chunk.metadata["page"] == 12


def test_search_result_references_chunk_and_rank() -> None:
    chunk = Chunk(chunk_id="url_001_smain_c01", text="Noi dung chinh.", metadata={})
    result = SearchResult(chunk=chunk, score=0.91, rank=1, retriever="dense")

    assert result.chunk is chunk
    assert result.retriever == "dense"
    assert result.rank == 1


def test_answer_supports_found_and_not_found_statuses() -> None:
    citation = Citation(source="vinfast_warranty.pdf", chunk_id="pdf_001_p12_c01", page=12)
    answered = Answer(answer="Pin duoc bao hanh 8 nam.", citations=[citation], status="answered")
    not_found = Answer(
        answer="Khong co trong tai lieu duoc cung cap.", citations=[], status="not_found"
    )

    assert answered.citations == [citation]
    assert not_found.status == "not_found"


def test_answer_converts_nested_citation_dicts() -> None:
    answer = Answer(
        answer="Pin duoc bao hanh 8 nam.",
        status="answered",
        citations=[{"source": "vinfast_warranty.pdf", "chunk_id": "pdf_001_p12_c01"}],
    )

    assert answer.citations == [Citation(source="vinfast_warranty.pdf", chunk_id="pdf_001_p12_c01")]
    assert answer.model_dump()["citations"][0]["chunk_id"] == "pdf_001_p12_c01"


def test_answer_rejects_invalid_citation_list_items() -> None:
    with pytest.raises(ValidationError):
        Answer(answer="Invalid citation.", status="answered", citations=["not-a-citation"])


def test_search_result_converts_nested_chunk_dict() -> None:
    result = SearchResult(
        chunk={
            "chunk_id": "url_001_smain_c01",
            "text": "Noi dung tu website.",
            "metadata": {"source_type": "url"},
        },
        score=0.7,
        rank=2,
        retriever="bm25",
    )

    assert result.chunk == Chunk(
        chunk_id="url_001_smain_c01",
        text="Noi dung tu website.",
        metadata={"source_type": "url"},
    )


def test_contracts_reject_extra_top_level_fields() -> None:
    payload: dict[str, object] = {
        "chunk_id": "bad",
        "text": "Bad chunk.",
        "metadata": {},
        "unexpected": True,
    }

    with pytest.raises(ValidationError):
        Chunk.model_validate(payload)


def test_answer_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        Answer(answer="Invalid status.", status="done")


def test_contract_models_are_frozen() -> None:
    chunk = Chunk(chunk_id="immutable", text="Cannot mutate this.", metadata={})
    field_name = "text"

    with pytest.raises(ValidationError):
        setattr(chunk, field_name, "Mutated")
