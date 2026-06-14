from agentic_rag.core.contracts import Answer, Chunk, SearchResult
from agentic_rag.ingestion.knowledge_quality import analyze_chunks
from agentic_rag.testing.fixtures import (
    sample_answer,
    sample_chunks,
    sample_knowledge_quality_chunks,
    sample_search_results,
)


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


def test_sample_knowledge_quality_chunks_cover_demo_findings() -> None:
    chunks = sample_knowledge_quality_chunks()
    report = analyze_chunks(chunks)

    assert all(isinstance(chunk, Chunk) for chunk in chunks)
    assert len(chunks) == 8
    assert {finding.kind for finding in report.findings} >= {
        "exact_duplicate",
        "near_duplicate",
        "conflict",
    }
    assert {
        finding.metadata.get("attribute")
        for finding in report.findings
        if finding.kind == "conflict"
    } >= {"warranty_duration", "price", "distance_km"}


def test_sample_answer_uses_real_sample_citations() -> None:
    answer = sample_answer()

    assert isinstance(answer, Answer)
    assert answer.status == "answered"
    assert answer.citations
    assert answer.citations[0].chunk_id.startswith("pdf_")
