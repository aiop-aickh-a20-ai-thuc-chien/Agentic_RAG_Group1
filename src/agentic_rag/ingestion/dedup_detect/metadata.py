"""Metadata helpers for duplicate detection results."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.dedup_detect.models import DedupReport, DuplicateMatch

DEDUP_METADATA_KEY = "deduplication"


def duplicate_metadata_by_document(report: DedupReport) -> dict[str, dict[str, Any]]:
    """Build duplicate metadata keyed by document or chunk id."""

    matches_by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    layers_by_document: dict[str, set[str]] = defaultdict(set)

    for match in report.matches:
        _append_match_metadata(
            matches_by_document,
            layers_by_document,
            document_id=match.document_id,
            other_document_id=match.duplicate_document_id,
            role="canonical",
            match=match,
        )
        _append_match_metadata(
            matches_by_document,
            layers_by_document,
            document_id=match.duplicate_document_id,
            other_document_id=match.document_id,
            role="duplicate_candidate",
            match=match,
        )

    metadata: dict[str, dict[str, Any]] = {}
    for document_id, matches in matches_by_document.items():
        metadata[document_id] = {
            "has_duplicate": True,
            "match_count": len(matches),
            "detected_layers": sorted(layers_by_document[document_id]),
            "matches": matches,
        }
    return metadata


def add_duplicate_metadata_to_chunks(chunks: list[Chunk], report: DedupReport) -> list[Chunk]:
    """Return chunks with duplicate-detection metadata attached."""

    by_document = duplicate_metadata_by_document(report)
    enriched: list[Chunk] = []
    for chunk in chunks:
        dedup_metadata = by_document.get(chunk.chunk_id)
        if dedup_metadata is None:
            enriched.append(chunk)
            continue
        metadata = dict(chunk.metadata)
        metadata[DEDUP_METADATA_KEY] = dedup_metadata
        enriched.append(chunk.model_copy(update={"metadata": metadata}))
    return enriched


def _append_match_metadata(
    matches_by_document: dict[str, list[dict[str, Any]]],
    layers_by_document: dict[str, set[str]],
    *,
    document_id: str,
    other_document_id: str,
    role: str,
    match: DuplicateMatch,
) -> None:
    layers_by_document[document_id].add(match.layer)
    matches_by_document[document_id].append(
        {
            "other_document_id": other_document_id,
            "role": role,
            "detected_layer": match.layer,
            "score": match.score,
            "distance": match.distance,
            "fingerprint": match.fingerprint,
            "reason": match.reason,
            "detection_summary": _detection_summary(match, role),
            "metadata": match.metadata,
        }
    )


def _detection_summary(match: DuplicateMatch, role: str) -> str:
    role_label = "canonical side" if role == "canonical" else "duplicate-candidate side"
    if match.layer == "exact_sha256":
        return f"{role_label}: exact normalized text duplicate detected."
    if match.layer == "simhash":
        return f"{role_label}: near-duplicate detected by SimHash distance."
    return f"{role_label}: near-duplicate detected by embedding cosine similarity."
