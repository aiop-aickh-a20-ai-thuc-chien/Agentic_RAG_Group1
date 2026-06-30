"""Final Pydantic-backed trust gate for integrated URL evidence."""

from __future__ import annotations

from collections.abc import Sequence

from agentic_rag.ingestion.integration.url.models import (
    UrlEvidenceFact,
    UrlEvidenceRef,
    UrlStructuredSection,
)


def validate_evidence_links(
    sections: Sequence[UrlStructuredSection],
    facts: Sequence[UrlEvidenceFact],
    evidence: Sequence[UrlEvidenceRef],
) -> tuple[tuple[UrlEvidenceFact, ...], tuple[UrlEvidenceFact, ...]]:
    known = {item.evidence_id for item in evidence}
    for section in sections:
        unknown = set(section.evidence_refs) - known
        if unknown:
            raise ValueError(
                f"Section {section.section_id!r} cites unknown evidence IDs: {sorted(unknown)}"
            )

    accepted: list[UrlEvidenceFact] = []
    rejected: list[UrlEvidenceFact] = []
    for fact in facts:
        unknown = set(fact.evidence_refs) - known
        is_vlm = fact.extraction_strategy.startswith("vlm") or fact.origin == "visually_inferred"
        if not fact.evidence_refs or unknown or (is_vlm and fact.confidence <= 0.0) or fact.validation_status == "rejected":
            rejected.append(fact.model_copy(update={"validation_status": "rejected"}))
            continue
        # TODO [url/TODO_LLM.md §5 – Unvalidated LLM output isolation]:
        # Any fact produced by an LLM review step (not a source-backed extractor)
        # should be stored as `interaction_review.llm_notes` in artifact metadata
        # and NOT promoted into accepted chunk facts until confirmed by a
        # deterministic validator (DOM text match, network payload, OCR).
        # Reference: url/TODO_LLM.md §5, Evidence-First Flow
        accepted.append(fact.model_copy(update={"validation_status": "validated"}))
    return tuple(accepted), tuple(rejected)

