"""Conservative classification of metadata-blocked duplicate candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from agentic_rag.ingestion.dedup_detect.blocking import blocked_candidate_pairs
from agentic_rag.ingestion.dedup_detect.models import (
    DedupDocument,
    DuplicateClassification,
    DuplicateReview,
)
from agentic_rag.ingestion.dedup_detect.normalization import normalize_text

CRITICAL_STATE_FIELDS = (
    "edition_id",
    "seat_layout",
    "exterior_id",
    "interior_id",
    "surcharge",
    "compatibility",
    "image_url",
    "availability",
    "specifications",
)
EVIDENCE_REF_FIELDS = (
    "before_snapshot_ref",
    "after_snapshot_ref",
    "artifact_ref",
    "state_diff_ref",
    "evidence_ref",
)


class DuplicatePairReviewer(Protocol):
    """Adapter boundary for an LLM duplicate classifier."""

    def __call__(
        self, left: DedupDocument, right: DedupDocument
    ) -> DuplicateReview | Mapping[str, object]: ...


def review_blocked_candidates(
    documents: Sequence[DedupDocument],
    *,
    reviewer: DuplicatePairReviewer | None = None,
    max_block_size: int = 50,
    exclude_pairs: set[tuple[str, str]] | None = None,
) -> list[DuplicateReview]:
    """Review only metadata-compatible pairs and retain all provenance."""

    excluded = exclude_pairs or set()
    reviews: list[DuplicateReview] = []
    for left, right in blocked_candidate_pairs(documents, max_block_size=max_block_size):
        pair = tuple(sorted((left.document_id, right.document_id)))
        if pair in excluded:
            continue
        deterministic = _state_guard_review(left, right)
        if deterministic is not None:
            reviews.append(deterministic)
        elif reviewer is None:
            reviews.append(_review(left, right, "needs_review", 0.0, "LLM review required."))
        else:
            result = reviewer(left, right)
            reviews.append(
                result
                if isinstance(result, DuplicateReview)
                else DuplicateReview.model_validate(result)
            )
    return reviews


def _state_guard_review(left: DedupDocument, right: DedupDocument) -> DuplicateReview | None:
    left_state = str(left.metadata.get("state_id") or "")
    right_state = str(right.metadata.get("state_id") or "")
    changed = _changed_critical_fields(left.metadata, right.metadata)
    if changed:
        return _review(
            left,
            right,
            "not_duplicate",
            1.0,
            f"Retrieval-critical state fields differ: {', '.join(changed)}.",
        )
    if left_state and right_state and left_state != right_state:
        return _review(
            left,
            right,
            "not_duplicate",
            0.99,
            "Sibling dynamic states are not duplicates solely from shared template text.",
        )
    left_fact = _state_fact_text(left)
    right_fact = _state_fact_text(right)
    if left_state and left_state == right_state and left_fact == right_fact:
        return _review(left, right, "duplicate", 1.0, "Replay of the same stable state.")
    return None


def _review(
    left: DedupDocument,
    right: DedupDocument,
    classification: DuplicateClassification,
    confidence: float,
    reason: str,
) -> DuplicateReview:
    compared = {
        field: (str(left.metadata.get(field) or ""), str(right.metadata.get(field) or ""))
        for field in (
            "product_model",
            "scope_type",
            "attribute_group",
            "language",
            "scope_path",
            *CRITICAL_STATE_FIELDS,
        )
        if left.metadata.get(field) is not None or right.metadata.get(field) is not None
    }
    return DuplicateReview(
        classification=classification,
        confidence=confidence,
        reason=reason,
        document_id=left.document_id,
        duplicate_document_id=right.document_id,
        compared_metadata_fields=compared,
        cited_chunk_ids=(left.document_id, right.document_id),
        evidence_refs=_evidence_refs(left, right),
        pair_category=_pair_category(left, right),
    )


def _state_fact_text(document: DedupDocument) -> str:
    text = document.text
    inherited = str(document.metadata.get("inherited_parent_text") or "").strip()
    if inherited:
        text = text.replace(inherited, "", 1)
    return normalize_text(text)


def _changed_critical_fields(
    left: Mapping[str, object], right: Mapping[str, object]
) -> list[str]:
    return [
        field
        for field in CRITICAL_STATE_FIELDS
        if left.get(field) is not None
        and right.get(field) is not None
        and left.get(field) != right.get(field)
    ]


def _evidence_refs(left: DedupDocument, right: DedupDocument) -> tuple[str, ...]:
    refs: list[str] = []
    for metadata in (left.metadata, right.metadata):
        for field in EVIDENCE_REF_FIELDS:
            value = metadata.get(field)
            if value and str(value) not in refs:
                refs.append(str(value))
        values = metadata.get("evidence_refs")
        if isinstance(values, list | tuple):
            refs.extend(str(value) for value in values if str(value) not in refs)
    return tuple(refs)


def _pair_category(left: DedupDocument, right: DedupDocument) -> str:
    left_model = left.metadata.get("product_model")
    right_model = right.metadata.get("product_model")
    if left_model and right_model and left_model != right_model:
        return "cross_model"
    left_state = left.metadata.get("state_id")
    right_state = right.metadata.get("state_id")
    if left_state and left_state == right_state:
        return "same_state_replay"
    if left.metadata.get("parent_state_id") == right.metadata.get("parent_state_id"):
        return "sibling_state"
    if (
        left.document_id == right.metadata.get("parent_chunk_id")
        or right.document_id == left.metadata.get("parent_chunk_id")
    ):
        return "parent_child"
    return "cross_source_representation"
