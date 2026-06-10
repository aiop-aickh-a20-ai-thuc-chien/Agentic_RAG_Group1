from agentic_rag.core.contracts import Answer, Chunk, SearchResult
from agentic_rag.testing.fixtures import sample_answer, sample_chunks, sample_search_results


def test_sample_chunks_cover_pdf_and_url_sources() -> None:
    chunks = sample_chunks()
    source_types = {chunk.metadata["source_type"] for chunk in chunks}

    assert all(isinstance(chunk, Chunk) for chunk in chunks)
    assert {"pdf", "url"} <= source_types


def test_sample_search_results_are_ranked_and_contract_compatible() -> None:
    results = sample_search_results()

    assert all(isinstance(result, SearchResult) for result in results)
    assert [result.rank for result in results] == [1, 2]
    assert {result.retriever for result in results} == {"hybrid"}


def test_sample_answer_uses_real_sample_citations() -> None:
    answer = sample_answer()

    assert isinstance(answer, Answer)
    assert answer.status == "answered"
    assert answer.citations
    assert answer.citations[0].chunk_id.startswith("pdf_")
