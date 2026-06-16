from __future__ import annotations

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.dedup_detect import (
    chunk_metadata_contract_issues,
    chunk_metadata_contract_summary,
)


def test_chunk_metadata_contract_summary_tracks_required_source_type() -> None:
    chunks = [
        Chunk(
            chunk_id="url-1",
            text="A",
            metadata={
                "source": "https://example.com/a",
                "source_type": "unknown",
                "updated_date": "2026-06-16T00:00:00+00:00",
            },
        ),
        Chunk(
            chunk_id="pdf-1",
            text="B",
            metadata={
                "source": "guide.pdf",
                "source_type": "internal",
                "document_type": "policy",
                "updated_date": "2026-06-16T00:00:00+00:00",
            },
        ),
        Chunk(chunk_id="bad-1", text="C", metadata={"source": "missing-source-type"}),
    ]

    issues = chunk_metadata_contract_issues(chunks)
    summary = chunk_metadata_contract_summary(chunks)

    assert issues == [
        {
            "chunk_id": "bad-1",
            "missing_required": ["source_type", "updated_date"],
            "source": "missing-source-type",
            "source_type": None,
        }
    ]
    assert summary["required_fields"] == ["source_type", "updated_date"]
    assert summary["valid_chunk_count"] == 2
    assert summary["missing_required_count"] == 1
    assert summary["source_type_counts"] == {"internal": 1, "missing": 1, "unknown": 1}
    assert summary["document_type_counts"] == {"missing": 2, "policy": 1}
