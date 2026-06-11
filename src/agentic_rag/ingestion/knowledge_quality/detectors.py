"""Deterministic duplicate and conflict detection for ingested chunks."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from typing import NamedTuple

from agentic_rag.core.contracts import (
    Chunk,
    KnowledgeQualityFact,
    KnowledgeQualityFinding,
    KnowledgeQualityReport,
)

_ENTITY_RE = re.compile(r"\b(?:vinfast\s+)?vf\s*-?\s*[0-9][a-z0-9]*(?:\s+plus)?\b", re.I)
_DURATION_RE = re.compile(
    r"(?P<value>\d+(?:[,.]\d+)?)\s*(?P<unit>năm|nam|tháng|thang|year|years|month|months)\b",
    re.I,
)
_DISTANCE_RE = re.compile(
    r"(?P<value>\d{1,3}(?:[.,]\d{3})+|\d+(?:[,.]\d+)?)\s*(?P<unit>km|kilometer|kilometers)\b",
    re.I,
)
_PRICE_RE = re.compile(
    r"(?P<value>\d+(?:[,.]\d+)?)\s*(?P<unit>triệu|trieu|tỷ|ty|đồng|dong|vnd)\b",
    re.I,
)
_DATE_RE = re.compile(
    r"\b(?P<value>\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4})\b",
    re.I,
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NEAR_DUPLICATE_THRESHOLD = 0.55
_PRICE_MULTIPLIERS = {
    "triệu": 1_000_000,
    "trieu": 1_000_000,
    "tỷ": 1_000_000_000,
    "ty": 1_000_000_000,
    "đồng": 1,
    "dong": 1,
    "vnd": 1,
}


class _FactCandidate(NamedTuple):
    chunk: Chunk
    entity: str
    attribute: str
    value: str
    normalized_value: float | str
    unit: str | None
    span: str
    start: int
    end: int


class DeterministicKnowledgeQualityProcessor:
    """Annotate chunks with deterministic duplicate/conflict quality metadata."""

    def process(self, chunks: list[Chunk]) -> list[Chunk]:
        """Return chunks annotated with quality metadata."""

        return annotate_chunks_with_quality(chunks)


def analyze_chunks(
    chunks: list[Chunk],
    *,
    existing_chunks: list[Chunk] | None = None,
) -> KnowledgeQualityReport:
    """Return duplicate/conflict findings for the provided chunks."""

    all_chunks = [*(existing_chunks or []), *chunks]
    facts = _extract_facts(all_chunks)
    findings = [
        *_exact_duplicate_findings(all_chunks),
        *_near_duplicate_findings(all_chunks),
        *_conflict_findings(facts),
    ]
    return KnowledgeQualityReport(
        facts=facts,
        findings=findings,
        metadata={
            "chunk_count": len(all_chunks),
            "new_chunk_count": len(chunks),
            "existing_chunk_count": len(existing_chunks or []),
            "method": "deterministic_offline",
        },
    )


def annotate_chunks_with_quality(
    chunks: list[Chunk],
    *,
    existing_chunks: list[Chunk] | None = None,
) -> list[Chunk]:
    """Attach a compact quality summary to each provided chunk."""

    report = analyze_chunks(chunks, existing_chunks=existing_chunks)
    chunk_findings = _findings_by_chunk(report.findings)
    facts_by_chunk = _facts_by_chunk(report.facts)
    output: list[Chunk] = []
    target_ids = {chunk.chunk_id for chunk in chunks}
    for chunk in chunks:
        findings = chunk_findings.get(chunk.chunk_id, [])
        facts = facts_by_chunk.get(chunk.chunk_id, [])
        summary = {
            "duplicate_count": sum(
                1 for finding in findings if finding.kind in {"exact_duplicate", "near_duplicate"}
            ),
            "conflict_count": sum(1 for finding in findings if finding.kind == "conflict"),
            "fact_count": len(facts),
            "finding_ids": [finding.finding_id for finding in findings],
            "fact_ids": [fact.fact_id for fact in facts],
        }
        metadata = {**chunk.metadata, "knowledge_quality": summary}
        output.append(chunk.model_copy(update={"metadata": metadata}))

    # Existing chunks participate in analysis but are intentionally not rewritten.
    assert {chunk.chunk_id for chunk in output} == target_ids
    return output


def _extract_facts(chunks: list[Chunk]) -> list[KnowledgeQualityFact]:
    candidates = [candidate for chunk in chunks for candidate in _fact_candidates(chunk)]
    return [
        KnowledgeQualityFact(
            fact_id=_fact_id(candidate, index),
            chunk_id=candidate.chunk.chunk_id,
            entity=candidate.entity,
            attribute=candidate.attribute,
            value=candidate.value,
            normalized_value=candidate.normalized_value,
            unit=candidate.unit,
            span=candidate.span,
            start=candidate.start,
            end=candidate.end,
            metadata={
                "source": _chunk_source(candidate.chunk),
                "document_id": candidate.chunk.metadata.get("document_id"),
            },
        )
        for index, candidate in enumerate(candidates, start=1)
    ]


def _fact_candidates(chunk: Chunk) -> list[_FactCandidate]:
    text = chunk.text
    entities = _entities_for_text(text)
    candidates: list[_FactCandidate] = []
    for match in _PRICE_RE.finditer(text):
        candidates.extend(
            _candidate_for_match(
                chunk=chunk,
                match=match,
                entities=entities,
                attribute="price",
                normalized_value=_normalized_price(match),
                unit="vnd",
            )
        )
    for match in _DURATION_RE.finditer(text):
        attribute = (
            "warranty_duration" if _has_warranty_context(text, match.start()) else "duration"
        )
        candidates.extend(
            _candidate_for_match(
                chunk=chunk,
                match=match,
                entities=entities,
                attribute=attribute,
                normalized_value=_normalized_duration_months(match),
                unit="months",
            )
        )
    for match in _DISTANCE_RE.finditer(text):
        candidates.extend(
            _candidate_for_match(
                chunk=chunk,
                match=match,
                entities=entities,
                attribute="distance_km",
                normalized_value=_number(match.group("value")),
                unit="km",
            )
        )
    for match in _DATE_RE.finditer(text):
        if _overlaps_existing_match(match, candidates):
            continue
        candidates.extend(
            _candidate_for_match(
                chunk=chunk,
                match=match,
                entities=entities,
                attribute="date",
                normalized_value=match.group("value"),
                unit=None,
            )
        )
    return candidates


def _candidate_for_match(
    *,
    chunk: Chunk,
    match: re.Match[str],
    entities: list[str],
    attribute: str,
    normalized_value: float | str,
    unit: str | None,
) -> list[_FactCandidate]:
    value = match.group("value")
    span = _sentence_span(chunk.text, match.start(), match.end())
    return [
        _FactCandidate(
            chunk=chunk,
            entity=entity,
            attribute=attribute,
            value=f"{value} {match.groupdict().get('unit', '')}".strip(),
            normalized_value=normalized_value,
            unit=unit,
            span=span,
            start=match.start(),
            end=match.end(),
        )
        for entity in entities
    ]


def _exact_duplicate_findings(chunks: list[Chunk]) -> list[KnowledgeQualityFinding]:
    groups: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        normalized = _normalize_text(chunk.text)
        if normalized:
            groups[normalized].append(chunk)

    findings: list[KnowledgeQualityFinding] = []
    for group in groups.values():
        if len(group) < 2:
            continue
        chunk_ids = sorted(chunk.chunk_id for chunk in group)
        findings.append(
            KnowledgeQualityFinding(
                finding_id=_finding_id("exact_duplicate", chunk_ids),
                kind="exact_duplicate",
                severity="info",
                chunk_ids=chunk_ids,
                summary=f"Exact duplicate text appears in {len(chunk_ids)} chunks.",
                suggested_action="Keep the most authoritative source or remove duplicate chunks.",
                confidence=1.0,
                metadata={"sources": [_chunk_source(chunk) for chunk in group]},
            )
        )
    return findings


def _near_duplicate_findings(chunks: list[Chunk]) -> list[KnowledgeQualityFinding]:
    findings: list[KnowledgeQualityFinding] = []
    exact_pairs = {
        tuple(finding.chunk_ids)
        for finding in _exact_duplicate_findings(chunks)
        if len(finding.chunk_ids) == 2
    }
    for left_index, left in enumerate(chunks):
        left_shingles = _shingles(left.text)
        if not left_shingles:
            continue
        for right in chunks[left_index + 1 :]:
            chunk_ids = sorted([left.chunk_id, right.chunk_id])
            if tuple(chunk_ids) in exact_pairs:
                continue
            right_shingles = _shingles(right.text)
            if not right_shingles:
                continue
            score = _jaccard(left_shingles, right_shingles)
            if score >= _NEAR_DUPLICATE_THRESHOLD and _normalize_text(left.text) != _normalize_text(
                right.text
            ):
                findings.append(
                    KnowledgeQualityFinding(
                        finding_id=_finding_id("near_duplicate", chunk_ids),
                        kind="near_duplicate",
                        severity="info",
                        chunk_ids=chunk_ids,
                        summary="Near-duplicate chunks contain substantially similar text.",
                        suggested_action=(
                            "Review whether the chunks should be merged or one ignored."
                        ),
                        confidence=round(score, 4),
                        metadata={
                            "similarity": round(score, 4),
                            "sources": [_chunk_source(left), _chunk_source(right)],
                        },
                    )
                )
    return findings


def _conflict_findings(facts: list[KnowledgeQualityFact]) -> list[KnowledgeQualityFinding]:
    groups: dict[tuple[str, str, str | None], list[KnowledgeQualityFact]] = defaultdict(list)
    for fact in facts:
        groups[(_normalize_entity(fact.entity), fact.attribute, fact.unit)].append(fact)

    findings: list[KnowledgeQualityFinding] = []
    for (_entity_key, attribute, _unit), group in groups.items():
        for left_index, left in enumerate(group):
            for right in group[left_index + 1 :]:
                if left.chunk_id == right.chunk_id:
                    continue
                if not _values_conflict(left.normalized_value, right.normalized_value):
                    continue
                chunk_ids = sorted([left.chunk_id, right.chunk_id])
                fact_ids = sorted([left.fact_id, right.fact_id])
                findings.append(
                    KnowledgeQualityFinding(
                        finding_id=_finding_id("conflict", [*chunk_ids, *fact_ids]),
                        kind="conflict",
                        severity="warning",
                        chunk_ids=chunk_ids,
                        fact_ids=fact_ids,
                        summary=(
                            f"{left.entity} has conflicting {attribute}: "
                            f"{left.value} vs {right.value}."
                        ),
                        suggested_action=(
                            "Review conflicting chunks before answering; prefer the newer or "
                            "more authoritative source."
                        ),
                        confidence=0.95,
                        metadata={
                            "entity": left.entity,
                            "attribute": attribute,
                            "left_value": left.value,
                            "right_value": right.value,
                            "left_source": left.metadata.get("source"),
                            "right_source": right.metadata.get("source"),
                        },
                    )
                )
    return _deduplicate_findings(findings)


def _normalize_text(text: str) -> str:
    text = text.casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9]+", " ", without_marks)
    return " ".join(normalized.split())


def _entities_for_text(text: str) -> list[str]:
    entities: list[str] = []
    for match in _ENTITY_RE.finditer(text):
        entity = _format_entity(match.group(0))
        if entity not in entities:
            entities.append(entity)
    return entities or ["global"]


def _format_entity(value: str) -> str:
    compact = re.sub(r"\s+", " ", value.replace("-", " ")).strip().upper()
    compact = compact.replace("VINFAST ", "")
    return compact.replace("VF ", "VF ", 1)


def _normalize_entity(value: str) -> str:
    return _normalize_text(value).replace(" ", "")


def _has_warranty_context(text: str, start: int) -> bool:
    window = _normalize_text(text[max(0, start - 80) : start + 80])
    return any(term in window for term in ("bao hanh", "warranty", "guarantee"))


def _normalized_price(match: re.Match[str]) -> float:
    unit = _normalize_text(match.group("unit"))
    return _number(match.group("value")) * _PRICE_MULTIPLIERS.get(unit, 1)


def _normalized_duration_months(match: re.Match[str]) -> float:
    value = _number(match.group("value"))
    unit = _normalize_text(match.group("unit"))
    if unit in {"nam", "year", "years"}:
        return value * 12
    return value


def _number(value: str) -> float:
    text = value.strip()
    if "." in text and "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    return float(text)


def _sentence_span(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start))
    right_candidates = [idx for idx in (text.find(".", end), text.find("\n", end)) if idx != -1]
    right = min(right_candidates) if right_candidates else len(text)
    return text[left + 1 : right].strip()


def _overlaps_existing_match(match: re.Match[str], candidates: list[_FactCandidate]) -> bool:
    return any(
        match.start() < candidate.end and match.end() > candidate.start for candidate in candidates
    )


def _shingles(text: str, size: int = 2) -> set[str]:
    tokens = _TOKEN_RE.findall(_normalize_text(text))
    if len(tokens) < size:
        return set(tokens)
    return {" ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _values_conflict(left: float | str, right: float | str) -> bool:
    if isinstance(left, float | int) and isinstance(right, float | int):
        tolerance = max(abs(float(left)), abs(float(right)), 1.0) * 0.01
        return abs(float(left) - float(right)) > tolerance
    return str(left) != str(right)


def _fact_id(candidate: _FactCandidate, index: int) -> str:
    raw = (
        f"{candidate.chunk.chunk_id}:{candidate.entity}:{candidate.attribute}:"
        f"{candidate.normalized_value}:{index}"
    )
    return f"fact-{hashlib.sha1(raw.encode()).hexdigest()[:12]}"


def _finding_id(kind: str, values: Iterable[str]) -> str:
    raw = f"{kind}:{'|'.join(sorted(values))}"
    return f"kq-{hashlib.sha1(raw.encode()).hexdigest()[:12]}"


def _chunk_source(chunk: Chunk) -> str:
    return str(
        chunk.metadata.get("source")
        or chunk.metadata.get("file_name")
        or chunk.metadata.get("url")
        or chunk.chunk_id
    )


def _findings_by_chunk(
    findings: list[KnowledgeQualityFinding],
) -> dict[str, list[KnowledgeQualityFinding]]:
    by_chunk: dict[str, list[KnowledgeQualityFinding]] = defaultdict(list)
    for finding in findings:
        for chunk_id in finding.chunk_ids:
            by_chunk[chunk_id].append(finding)
    return by_chunk


def _facts_by_chunk(facts: list[KnowledgeQualityFact]) -> dict[str, list[KnowledgeQualityFact]]:
    by_chunk: dict[str, list[KnowledgeQualityFact]] = defaultdict(list)
    for fact in facts:
        by_chunk[fact.chunk_id].append(fact)
    return by_chunk


def _deduplicate_findings(
    findings: list[KnowledgeQualityFinding],
) -> list[KnowledgeQualityFinding]:
    deduped: dict[str, KnowledgeQualityFinding] = {}
    for finding in findings:
        deduped[finding.finding_id] = finding
    return list(deduped.values())
