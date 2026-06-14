"""Sample contract-compatible objects for module-level tests and demos."""

from __future__ import annotations

from agentic_rag.core.contracts import Answer, Chunk, Citation, SearchResult


def sample_chunks() -> list[Chunk]:
    """Return representative chunks for PDF and URL sources."""

    return [
        Chunk(
            chunk_id="pdf_001_p12_c01",
            text="Pin cao ap duoc bao hanh 8 nam hoac 160.000 km.",
            metadata={
                "source": "vinfast_warranty.pdf",
                "source_type": "pdf",
                "file_name": "vinfast_warranty.pdf",
                "url": None,
                "page": 12,
                "section": None,
            },
        ),
        Chunk(
            chunk_id="url_001_smain_c01",
            text="Noi dung chinh tu website ve chinh sach bao hanh.",
            metadata={
                "source": "https://example.com/warranty",
                "source_type": "url",
                "file_name": None,
                "url": "https://example.com/warranty",
                "page": None,
                "section": "main",
            },
        ),
    ]


def sample_knowledge_quality_chunks() -> list[Chunk]:
    """Return a compact KB with duplicates and factual conflicts for demos."""

    return [
        Chunk(
            chunk_id="quality_warranty_a_c0001",
            text="Pin VF8 duoc bao hanh 8 nam hoac 160.000 km.",
            metadata={"source": "warranty-a.txt", "document_id": "quality_warranty_a"},
        ),
        Chunk(
            chunk_id="quality_warranty_copy_c0001",
            text="Pin VF8 duoc bao hanh 8 nam hoac 160.000 km.",
            metadata={"source": "warranty-copy.txt", "document_id": "quality_warranty_copy"},
        ),
        Chunk(
            chunk_id="quality_warranty_near_c0001",
            text="Pin VF8 bao hanh trong 8 nam va gioi han 160000 km.",
            metadata={"source": "warranty-near.txt", "document_id": "quality_warranty_near"},
        ),
        Chunk(
            chunk_id="quality_warranty_conflict_c0001",
            text="Pin VF8 duoc bao hanh 6 nam hoac 160.000 km.",
            metadata={
                "source": "warranty-conflict.txt",
                "document_id": "quality_warranty_conflict",
            },
        ),
        Chunk(
            chunk_id="quality_price_a_c0001",
            text="VF9 co gia niem yet 1,2 ty dong.",
            metadata={"source": "price-a.txt", "document_id": "quality_price_a"},
        ),
        Chunk(
            chunk_id="quality_price_b_c0001",
            text="VF9 co gia niem yet 1,5 ty dong.",
            metadata={"source": "price-b.txt", "document_id": "quality_price_b"},
        ),
        Chunk(
            chunk_id="quality_range_a_c0001",
            text="VF7 Plus di duoc 450 km sau mot lan sac.",
            metadata={"source": "range-a.txt", "document_id": "quality_range_a"},
        ),
        Chunk(
            chunk_id="quality_range_b_c0001",
            text="VF7 Plus di duoc 500 km sau mot lan sac.",
            metadata={"source": "range-b.txt", "document_id": "quality_range_b"},
        ),
    ]


def sample_search_results() -> list[SearchResult]:
    """Return ranked hybrid results built from sample chunks."""

    return [
        SearchResult(chunk=chunk, score=1.0 / rank, rank=rank, retriever="hybrid")
        for rank, chunk in enumerate(sample_chunks(), start=1)
    ]


def sample_answer() -> Answer:
    """Return a grounded answer with a citation to the first sample chunk."""

    return Answer(
        answer="Pin cao ap duoc bao hanh 8 nam hoac 160.000 km.",
        citations=[
            Citation(
                source="vinfast_warranty.pdf",
                chunk_id="pdf_001_p12_c01",
                page=12,
            )
        ],
        status="answered",
    )


def sample_ragflow_chunk_payload() -> dict[str, object]:
    """Return a RAGFlow-like chunk payload for adapter tests and demos."""

    return {
        "id": "ragflow_pdf_001_p12_c01",
        "content": "Pin cao ap duoc bao hanh 8 nam hoac 160.000 km.",
        "document_name": "vinfast_warranty.pdf",
        "page": 12,
        "metadata": {
            "source": "vinfast_warranty.pdf",
            "source_type": "ragflow",
            "file_name": "vinfast_warranty.pdf",
            "url": None,
            "page": 12,
            "section": "warranty",
        },
    }


def sample_ragflow_hit_payload() -> dict[str, object]:
    """Return a RAGFlow-like retrieval hit payload."""

    return {
        "rank": 1,
        "score": 0.93,
        "chunk": sample_ragflow_chunk_payload(),
    }


def sample_ragflow_answer_payload() -> dict[str, object]:
    """Return a RAGFlow-like answer payload."""

    return {
        "answer": "Pin cao ap duoc bao hanh 8 nam hoac 160.000 km.",
        "citations": [
            {
                "source": "vinfast_warranty.pdf",
                "chunk_id": "ragflow_pdf_001_p12_c01",
                "page": 12,
                "section": "warranty",
            }
        ],
        "status": "answered",
    }
