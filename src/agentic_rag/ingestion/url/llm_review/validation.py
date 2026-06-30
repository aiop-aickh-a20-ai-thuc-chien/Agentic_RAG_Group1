"""Deterministic validation for URL LLM review output."""

from __future__ import annotations

import json

from agentic_rag.ingestion.url.chunking import normalize_space
from agentic_rag.ingestion.url.llm_review.models import (
    UrlLlmReviewInput,
    UrlLlmReviewOutput,
)


def validate_review_output(
    output: UrlLlmReviewOutput,
    review_input: UrlLlmReviewInput,
) -> UrlLlmReviewOutput:
    """Mark unsupported LLM-proposed facts as unvalidated."""

    evidence_text = _combined_evidence_text(review_input)
    unvalidated = list(output.unvalidated_facts)
    for field, value in output.field_mapping.items():
        cleaned_value = normalize_space(value)
        if not cleaned_value:
            continue
        if cleaned_value.casefold() not in evidence_text:
            unvalidated.append(f"{field}: {cleaned_value}")
    deduped = _dedupe(unvalidated)
    return output.model_copy(
        update={
            "unvalidated_facts": deduped,
            "needs_human_review": output.needs_human_review or bool(deduped),
        }
    )


def _combined_evidence_text(review_input: UrlLlmReviewInput) -> str:
    parts = [review_input.markdown, json.dumps(review_input.current_metadata, ensure_ascii=False)]
    for evidence in review_input.evidence:
        parts.append(evidence.text)
        parts.append(json.dumps(evidence.metadata, ensure_ascii=False))
    return "\n".join(parts).casefold()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


__all__ = ["validate_review_output"]
