from __future__ import annotations

import pytest

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.dedup_detect import (
    DedupConfig,
    DedupDocument,
    add_duplicate_metadata_to_chunks,
    cosine_similarity,
    detect_duplicates,
    documents_from_chunks,
    duplicate_metadata_by_document,
    find_embedding_duplicates,
    find_exact_duplicates,
    find_simhash_duplicates,
    hamming_distance,
    normalize_text,
    sha256_fingerprint,
    simhash_fingerprint,
)


def test_normalize_text_collapses_case_unicode_and_whitespace() -> None:
    assert normalize_text("  VinFast\u200b  VF 9\n") == "vinfast vf 9"


def test_exact_duplicate_detection_uses_sha256_of_normalized_text() -> None:
    documents = [
        DedupDocument(document_id="a", text="VinFast VF 9"),
        DedupDocument(document_id="b", text=" vinfast   vf 9 "),
        DedupDocument(document_id="c", text="VinFast VF 8"),
    ]

    matches = find_exact_duplicates(documents)

    assert len(matches) == 1
    assert matches[0].layer == "exact_sha256"
    assert matches[0].document_id == "a"
    assert matches[0].duplicate_document_id == "b"
    assert matches[0].fingerprint == sha256_fingerprint("vinfast vf 9")


def test_simhash_finds_near_duplicate_text() -> None:
    first = "VinFast VF 9 has seven seats and a battery range up to 626 km."
    second = "VinFast VF9 has 7 seats and battery range up to 626 kilometers."
    different = "Showroom opening hours and service center address."
    documents = [
        DedupDocument(document_id="a", text=first),
        DedupDocument(document_id="b", text=second),
        DedupDocument(document_id="c", text=different),
    ]

    matches = find_simhash_duplicates(
        documents,
        shingle_size=2,
        hamming_threshold=28,
    )

    assert any({match.document_id, match.duplicate_document_id} == {"a", "b"} for match in matches)
    assert all({match.document_id, match.duplicate_document_id} != {"a", "c"} for match in matches)


def test_simhash_hamming_distance_is_zero_for_same_text() -> None:
    fingerprint = simhash_fingerprint("same text", shingle_size=2)

    assert hamming_distance(fingerprint, fingerprint) == 0


def test_embedding_similarity_uses_cosine_over_supplied_vectors() -> None:
    documents = [
        DedupDocument(document_id="a", text="first"),
        DedupDocument(document_id="b", text="same meaning"),
        DedupDocument(document_id="c", text="different"),
    ]
    vectors = {
        "a": [1.0, 0.0, 0.0],
        "b": [0.98, 0.02, 0.0],
        "c": [0.0, 1.0, 0.0],
    }

    matches = find_embedding_duplicates(
        documents,
        vectors=vectors,
        similarity_threshold=0.95,
        method="unit-test-vectors",
    )

    assert len(matches) == 1
    assert matches[0].layer == "embedding_similarity"
    assert matches[0].metadata["method"] == "unit-test-vectors"


def test_cosine_similarity_rejects_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="same dimensions"):
        cosine_similarity([1.0], [1.0, 0.0])


def test_detect_duplicates_runs_three_layers_with_embedding_enabled() -> None:
    documents = [
        DedupDocument(document_id="a", text="VinFast VF 9 price"),
        DedupDocument(document_id="b", text=" vinfast vf 9 price "),
        DedupDocument(document_id="c", text="VinFast VF9 listed price"),
        DedupDocument(document_id="d", text="Warranty service"),
    ]
    vectors = {
        "a": [1.0, 0.0],
        "b": [1.0, 0.0],
        "c": [0.99, 0.01],
        "d": [0.0, 1.0],
    }

    report = detect_duplicates(
        documents,
        config=DedupConfig(
            enable_embedding=True,
            simhash_shingle_size=2,
            simhash_hamming_threshold=16,
            embedding_similarity_threshold=0.95,
            embedding_method="unit-test-vectors",
        ),
        embedding_vectors=vectors,
    )

    assert report.document_count == 4
    assert len(report.exact_matches) == 1
    assert report.matches
    assert all(
        {match.document_id, match.duplicate_document_id} != {"a", "b"}
        for match in report.embedding_matches
    )


def test_embedding_layer_requires_vectors_or_client_when_enabled() -> None:
    with pytest.raises(ValueError, match="embedding_vectors or embedding_client"):
        detect_duplicates(
            [DedupDocument(document_id="a", text="text")],
            config=DedupConfig(enable_embedding=True),
        )


def test_documents_from_chunks_preserves_chunk_identity_and_metadata() -> None:
    chunk = Chunk(
        chunk_id="chunk-1",
        text="Chunk text",
        metadata={"source_type": "url"},
    )

    documents = documents_from_chunks([chunk])

    assert documents == [
        DedupDocument(
            document_id="chunk-1",
            text="Chunk text",
            metadata={"source_type": "url"},
        )
    ]


def test_duplicate_metadata_records_detection_layers_without_resolve_action() -> None:
    report = detect_duplicates(
        [
            DedupDocument(document_id="chunk-a", text="Same text"),
            DedupDocument(document_id="chunk-b", text=" same   text "),
        ]
    )

    metadata = duplicate_metadata_by_document(report)

    assert metadata["chunk-a"]["detected_layers"] == ["exact_sha256"]
    assert metadata["chunk-b"]["matches"][0]["detected_layer"] == "exact_sha256"
    assert metadata["chunk-b"]["matches"][0]["role"] == "duplicate_candidate"
    assert "detection_summary" in metadata["chunk-b"]["matches"][0]
    assert "auto_resolve_candidates" not in metadata["chunk-b"]
    assert "auto_resolve_enabled" not in metadata["chunk-b"]
    assert "judgement" not in metadata["chunk-b"]["matches"][0]
    assert "auto_resolve_action" not in metadata["chunk-b"]["matches"][0]


def test_add_duplicate_metadata_to_chunks_returns_enriched_copies() -> None:
    chunks = [
        Chunk(chunk_id="chunk-a", text="Same text", metadata={"source_type": "url"}),
        Chunk(chunk_id="chunk-b", text="same text", metadata={"source_type": "url"}),
    ]
    report = detect_duplicates(documents_from_chunks(chunks))

    enriched = add_duplicate_metadata_to_chunks(chunks, report)

    assert "deduplication" not in chunks[0].metadata
    assert enriched[0].metadata["deduplication"]["has_duplicate"] is True
    assert enriched[1].metadata["deduplication"]["matches"][0]["detected_layer"] == "exact_sha256"
