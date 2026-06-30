"""Metadata helpers for duplicate detection results."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.dedup_detect.models import DedupReport, DuplicateMatch
from agentic_rag.ingestion.metadata import REQUIRED_METADATA_FIELDS, missing_required_metadata

DEDUP_METADATA_KEY = "deduplication"
DEDUP_STATUS_DUPLICATE_CANDIDATE = "duplicate_candidate"
DEDUP_REVIEW_PENDING = "pending"


def chunk_metadata_contract_issues(chunks: Sequence[Chunk]) -> list[dict[str, Any]]:
    """Return chunks that miss required shared ingestion metadata."""

    issues: list[dict[str, Any]] = []
    for chunk in chunks:
        metadata = _chunk_metadata_dict(chunk)
        missing = missing_required_metadata(metadata)
        if not missing:
            continue
        issues.append(
            {
                "chunk_id": chunk.chunk_id,
                "missing_required": list(missing),
                "source": metadata.get("source"),
                "source_type": metadata.get("source_type"),
            }
        )
    return issues


def chunk_metadata_contract_summary(chunks: Sequence[Chunk]) -> dict[str, Any]:
    """Summarize source metadata readiness before dedup review."""

    source_type_counts: dict[str, int] = defaultdict(int)
    document_type_counts: dict[str, int] = defaultdict(int)
    for chunk in chunks:
        metadata = _chunk_metadata_dict(chunk)
        source_type = str(metadata.get("source_type") or "missing")
        document_type = str(metadata.get("document_type") or "missing")
        source_type_counts[source_type] += 1
        document_type_counts[document_type] += 1
    issues = chunk_metadata_contract_issues(chunks)
    return {
        "required_fields": list(REQUIRED_METADATA_FIELDS),
        "chunk_count": len(chunks),
        "valid_chunk_count": len(chunks) - len(issues),
        "missing_required_count": len(issues),
        "source_type_counts": dict(sorted(source_type_counts.items())),
        "document_type_counts": dict(sorted(document_type_counts.items())),
        "issues": issues,
    }


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

    _LAYER_RANK = {
        "exact_sha256": 0,
        "metadata_llm": 1,
        "simhash": 2,
        "embedding_similarity": 3,
    }

    metadata: dict[str, dict[str, Any]] = {}
    for candidate_chunk_id, matches in matches_by_candidate.items():
        detected_layers = sorted(
            layers_by_candidate[candidate_chunk_id],
            key=lambda layer: _LAYER_RANK.get(layer, 99),
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

    # TODO [url/TODO_dedup.md §4 – Variant merge guard]:
    # Before marking two chunks as duplicates, verify they are not different
    # product variants (e.g. VF 9 Eco vs VF 9 Plus) that merely share the same
    # model family or page template. Check `product_model`, `variant_id`, and
    # `battery_option` in both chunks' metadata. If these differ, downgrade the
    # match to `needs_review` instead of `duplicate_candidate`.
    # Reference: url/TODO_dedup.md §4
    #
    # TODO [url/TODO_dedup.md §5 – Stale/conflicting facts → knowledge_quality]:
    # If two chunks share the same entity but have conflicting product facts
    # (e.g. different prices for the same model+variant), do NOT resolve the
    # conflict here. Instead, route the conflict to `knowledge_quality` for
    # human or LLM review. This layer only reports duplicates, not resolves them.
    # Reference: url/TODO_dedup.md §5

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
    metadata = _chunk_metadata_dict(chunk)
    metadata.pop(DEDUP_METADATA_KEY, None)
    return metadata


def _chunk_document_id(chunk: Chunk | None) -> str | None:
    if chunk is None:
        return None
    raw_document_id = _chunk_metadata_dict(chunk).get("document_id")
    return str(raw_document_id) if raw_document_id not in {None, ""} else None


def _chunk_metadata_dict(chunk: Chunk) -> dict[str, Any]:
    metadata = chunk.metadata
    if isinstance(metadata, BaseModel):
        return metadata.model_dump(mode="json", exclude_none=True)
    return dict(metadata)


def _group_id(canonical_chunk_id: str, candidate_chunk_id: str) -> str:
    return f"{canonical_chunk_id}::{candidate_chunk_id}"


def _detection_summary(match: DuplicateMatch) -> str:
    if match.layer == "exact_sha256":
        return "candidate side: exact normalized text duplicate detected."
    if match.layer == "simhash":
        return "candidate side: near-duplicate detected by SimHash distance."
    if match.layer == "metadata_llm":
        return "candidate side: duplicate confirmed by metadata-blocked review."
    return "candidate side: near-duplicate detected by embedding cosine similarity."
