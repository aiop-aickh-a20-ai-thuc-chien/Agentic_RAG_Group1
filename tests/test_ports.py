from typing import get_type_hints

from agentic_rag.core.contracts import Answer, Chunk, SearchResult
from agentic_rag.core.ports import (
    BM25Searcher,
    DenseSearcher,
    EvidenceContextBuilder,
    Generator,
    PdfIngestor,
    UrlIngestor,
)


def test_pdf_ingestor_protocol_exposes_pdf_signature() -> None:
    hints = get_type_hints(PdfIngestor.load_pdf_chunks)

    assert hints["path"] is str
    assert hints["return"] == list[Chunk]


def test_url_ingestor_protocol_exposes_url_signature() -> None:
    url_hints = get_type_hints(UrlIngestor.load_url_chunks)

    assert url_hints["url"] is str
    assert url_hints["return"] == list[Chunk]


def test_retrieval_protocols_expose_search_signatures() -> None:
    bm25_hints = get_type_hints(BM25Searcher.bm25_search)
    dense_hints = get_type_hints(DenseSearcher.dense_search)

    assert bm25_hints["query"] is str
    assert bm25_hints["top_k"] is int
    assert bm25_hints["return"] == list[SearchResult]
    assert dense_hints["query"] is str
    assert dense_hints["top_k"] is int
    assert dense_hints["return"] == list[SearchResult]


def test_evidence_and_generation_protocols_expose_integration_signatures() -> None:
    evidence_hints = get_type_hints(EvidenceContextBuilder.build_evidence_context)
    generation_hints = get_type_hints(Generator.generate_answer)

    assert evidence_hints["evidence_chunks"] == list[SearchResult]
    assert evidence_hints["return"] is str
    assert generation_hints["question"] is str
    assert generation_hints["evidence_context"] is str
    assert generation_hints["evidence_chunks"] == list[SearchResult]
    assert generation_hints["return"] is Answer
