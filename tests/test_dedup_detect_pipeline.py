from __future__ import annotations

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.dedup_detect import (
    DedupConfig,
    detect_duplicates,
    documents_from_chunks,
)


def test_documents_from_chunks_prefers_url_dedupe_text_metadata() -> None:
    chunks = [
        Chunk(
            chunk_id="url-1",
            text="Warranty applies. https://example.com/a?utm_source=mail",
            metadata={"dedupe_text": "warranty applies."},
        ),
        Chunk(
            chunk_id="url-2",
            text="Warranty applies. https://example.com/b?utm_source=social",
            metadata={"dedupe_text": "warranty applies."},
        ),
    ]

    documents = documents_from_chunks(chunks)
    report = detect_duplicates(
        documents,
        config=DedupConfig(enable_exact=True, enable_simhash=False, enable_embedding=False),
    )

    assert [document.text for document in documents] == [
        "warranty applies.",
        "warranty applies.",
    ]
    assert documents[0].metadata["dedup_text_source"] == "metadata.dedupe_text"
    assert len(report.exact_matches) == 1
    assert report.exact_matches[0].document_id == "url-1"
    assert report.exact_matches[0].duplicate_document_id == "url-2"
