"""Metadata helpers for duplicate detection results."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.dedup_detect.models import DedupReport, DuplicateMatch

DEDUP_METADATA_KEY = "deduplication"
DEDUP_STATUS_DUPLICATE_CANDIDATE = "duplicate_candidate"
DEDUP_REVIEW_PENDING = "pending"


def duplicate_metadata_by_document(
    report: DedupReport,
    *,
    chunks: Sequence[Chunk] = (),
) -> dict[str, dict[str, Any]]:
    """Build candidate-only duplicate metadata keyed by chunk id.

    ``DuplicateMatch.document_id`` is treated as canonical and
    ``duplicate_document_id`` is treated as the candidate that should be reviewed.
    Canonical chunks stay clean so downstream UI/retrieval does not mark both sides
    of a pair as problematic.
    """

    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    matches_by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    layers_by_candidate: dict[str, set[str]] = defaultdict(set)

    for match in report.matches:
        _append_match_metadata(
            matches_by_candidate,
            layers_by_candidate,
            candidate_chunk_id=match.duplicate_document_id,
            canonical_chunk_id=match.document_id,
            match=match,
            chunk_by_id=chunk_by_id,
        )

    _LAYER_RANK = {"exact_sha256": 0, "simhash": 1, "embedding_similarity": 2}

    metadata: dict[str, dict[str, Any]] = {}
    for candidate_chunk_id, matches in matches_by_candidate.items():
        detected_layers = sorted(
            layers_by_candidate[candidate_chunk_id],
            key=lambda l: _LAYER_RANK.get(l, 99),
        )
        primary_layer = detected_layers[0]
        primary_match = next(
            (m for m in matches if m["detected_layer"] == primary_layer), matches[0]
        )
        metadata[candidate_chunk_id] = {
            "status": DEDUP_STATUS_DUPLICATE_CANDIDATE,
            "review_status": DEDUP_REVIEW_PENDING,
            "has_duplicate": True,
            "primary_layer": primary_layer,
            "match_count": len(matches),
            "detected_layers": detected_layers,
            "canonical_chunk_id": primary_match["canonical_chunk_id"],
            "canonical_document_id": primary_match.get("canonical_document_id"),
            "group_id": _group_id(
                str(primary_match["canonical_chunk_id"]),
                candidate_chunk_id,
            ),
            "matches": matches,
        }
    return metadata


def add_duplicate_metadata_to_chunks(
    chunks: list[Chunk],
    report: DedupReport,
    *,
    reference_chunks: Sequence[Chunk] = (),
) -> list[Chunk]:
    """Return chunks with candidate-only duplicate metadata attached."""

    by_document = duplicate_metadata_by_document(
        report,
        chunks=reference_chunks or chunks,
    )
    enriched: list[Chunk] = []
    for chunk in chunks:
        dedup_metadata = by_document.get(chunk.chunk_id)
        metadata = _metadata_without_dedup(chunk)
        if dedup_metadata is None:
            enriched.append(chunk.model_copy(update={"metadata": metadata}))
            continue
        metadata[DEDUP_METADATA_KEY] = dedup_metadata
        enriched.append(chunk.model_copy(update={"metadata": metadata}))
    return enriched


def remove_duplicate_metadata_from_chunks(chunks: Sequence[Chunk]) -> list[Chunk]:
    """Return chunks with stale duplicate metadata removed."""

    return [
        chunk.model_copy(update={"metadata": _metadata_without_dedup(chunk)}) for chunk in chunks
    ]


def _append_match_metadata(
    matches_by_candidate: dict[str, list[dict[str, Any]]],
    layers_by_candidate: dict[str, set[str]],
    *,
    candidate_chunk_id: str,
    canonical_chunk_id: str,
    match: DuplicateMatch,
    chunk_by_id: dict[str, Chunk],
) -> None:
    canonical_chunk = chunk_by_id.get(canonical_chunk_id)
    candidate_chunk = chunk_by_id.get(candidate_chunk_id)
    layers_by_candidate[candidate_chunk_id].add(match.layer)
    matches_by_candidate[candidate_chunk_id].append(
        {
            "canonical_chunk_id": canonical_chunk_id,
            "canonical_document_id": _chunk_document_id(canonical_chunk),
            "duplicate_chunk_id": candidate_chunk_id,
            "duplicate_document_id": _chunk_document_id(candidate_chunk),
            "role": DEDUP_STATUS_DUPLICATE_CANDIDATE,
            "detected_layer": match.layer,
            "score": match.score,
            "distance": match.distance,
            "fingerprint": match.fingerprint,
            "reason": match.reason,
            "detection_summary": _detection_summary(match),
            "metadata": match.metadata,
        }
    )


def _metadata_without_dedup(chunk: Chunk) -> dict[str, Any]:
    metadata = dict(chunk.metadata)
    metadata.pop(DEDUP_METADATA_KEY, None)
    return metadata


def _chunk_document_id(chunk: Chunk | None) -> str | None:
    if chunk is None:
        return None
    raw_document_id = chunk.metadata.get("document_id")
    return str(raw_document_id) if raw_document_id not in {None, ""} else None


def _group_id(canonical_chunk_id: str, candidate_chunk_id: str) -> str:
    return f"{canonical_chunk_id}::{candidate_chunk_id}"


def _detection_summary(match: DuplicateMatch) -> str:
    if match.layer == "exact_sha256":
        return "candidate side: exact normalized text duplicate detected."
    if match.layer == "simhash":
        return "candidate side: near-duplicate detected by SimHash distance."
    return "candidate side: near-duplicate detected by embedding cosine similarity."
