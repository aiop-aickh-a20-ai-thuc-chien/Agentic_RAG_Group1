"""Evidence-preserving reconciliation for URL strategy outputs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from agentic_rag.ingestion.integration.url.models import (
    UrlConflictCandidate,
    UrlEvidenceFact,
    UrlEvidenceRef,
    UrlStrategyOutput,
    UrlStructuredSection,
)


def reconcile_strategy_outputs(
    outputs: Sequence[UrlStrategyOutput],
) -> tuple[
    tuple[UrlStructuredSection, ...],
    tuple[UrlEvidenceFact, ...],
    tuple[UrlEvidenceRef, ...],
    tuple[UrlConflictCandidate, ...],
]:
    evidence_by_id: dict[str, UrlEvidenceRef] = {}
    sections_by_key: dict[tuple[str, str | None], UrlStructuredSection] = {}
    facts_by_value: dict[tuple[str, str, str | None, str], UrlEvidenceFact] = {}

    for output in outputs:
        for evidence in output.evidence:
            evidence_by_id.setdefault(evidence.evidence_id, evidence)
        for section in output.sections:
            key = (section.section_id, section.state_id)
            current = sections_by_key.get(key)
            if current is None or len(section.markdown) > len(current.markdown):
                sections_by_key[key] = section
        for fact in output.facts:
            fact_key = (
                fact.subject.casefold(),
                fact.attribute.casefold(),
                fact.state_id,
                _normalized_value(fact.value),
            )
            existing = facts_by_value.get(fact_key)
            if existing is None:
                facts_by_value[fact_key] = fact
            else:
                facts_by_value[fact_key] = existing.model_copy(
                    update={
                        "evidence_refs": tuple(
                            dict.fromkeys((*existing.evidence_refs, *fact.evidence_refs))
                        ),
                        "confidence": max(existing.confidence, fact.confidence),
                    }
                )

    facts = tuple(facts_by_value.values())
    
    # Priority rule: If visually_inferred fact conflicts with source_backed for the same key, mark it rejected
    source_backed_keys = {
        (fact.subject.casefold(), fact.attribute.casefold(), fact.state_id)
        for fact in facts
        if fact.origin == "source_backed"
    }
    reconciled_facts = []
    for fact in facts:
        key = (fact.subject.casefold(), fact.attribute.casefold(), fact.state_id)
        if fact.origin == "visually_inferred" and key in source_backed_keys:
            reconciled_facts.append(fact.model_copy(update={"validation_status": "rejected"}))
        else:
            reconciled_facts.append(fact)
    facts = tuple(reconciled_facts)

    conflicts = _conflicts(facts)
    sections = tuple(
        section.model_copy(update={"reading_order": index})
        for index, section in enumerate(
            sorted(sections_by_key.values(), key=lambda item: item.reading_order)
        )
    )
    return sections, facts, tuple(evidence_by_id.values()), conflicts


def _conflicts(facts: Sequence[UrlEvidenceFact]) -> tuple[UrlConflictCandidate, ...]:
    groups: dict[tuple[str, str, str | None], list[tuple[int, UrlEvidenceFact]]] = defaultdict(list)
    for index, fact in enumerate(facts):
        groups[(fact.subject.casefold(), fact.attribute.casefold(), fact.state_id)].append(
            (index, fact)
        )
    conflicts: list[UrlConflictCandidate] = []
    for group in groups.values():
        values = tuple(dict.fromkeys(item.value for _, item in group))
        if len({_normalized_value(value) for value in values}) < 2:
            continue
        conflicts.append(
            UrlConflictCandidate(
                subject=group[0][1].subject,
                attribute=group[0][1].attribute,
                values=values,
                fact_indexes=tuple(index for index, _ in group),
                reason="Strategies produced different source-backed values; preserve for review.",
            )
        )
    # TODO [url/TODO_dedup.md §5 – Route conflicts to knowledge_quality]:
    # Conflicting product facts (different prices for the same model+variant)
    # should be forwarded to `knowledge_quality` for LLM or human review.
    # This function only collects conflicts; it must NOT resolve them silently.
    # Add an integration test proving that a VF 9 price conflict from two
    # strategies surfaces as a UrlConflictCandidate and reaches the quality module.
    # Reference: url/TODO_dedup.md §5
    return tuple(conflicts)


def _normalized_value(value: str) -> str:
    return " ".join(value.split()).casefold()
