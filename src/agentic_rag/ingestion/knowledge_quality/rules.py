"""Deterministic metadata and semantic conflict rules."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from typing import NamedTuple

from agentic_rag.core.contracts import Chunk, KnowledgeQualityFinding

_ENTITY_RE = re.compile(r"\b(?:vinfast\s+)?vf\s*-?\s*[0-9][a-z0-9]*(?:\s+plus)?\b", re.I)
_SEMANTIC_MODALITIES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "recommendation",
        "recommendation",
        "negative",
        ("should not", "not recommended", "do not recommend", "khong nen"),
    ),
    (
        "recommendation",
        "recommendation",
        "positive",
        ("should", "recommended", "recommend", "nen"),
    ),
    (
        "policy",
        "obligation",
        "negative",
        ("not required", "optional", "khong bat buoc"),
    ),
    (
        "policy",
        "obligation",
        "positive",
        ("required", "must", "bat buoc"),
    ),
    (
        "policy",
        "availability",
        "negative",
        ("unsupported", "unavailable", "not supported", "khong ho tro"),
    ),
    (
        "policy",
        "availability",
        "positive",
        ("supported", "available", "ho tro"),
    ),
    (
        "policy",
        "permission",
        "negative",
        (
            "cannot",
            "can not",
            "not allowed",
            "forbidden",
            "prohibited",
            "khong duoc phep",
            "khong duoc",
            "cam",
        ),
    ),
    (
        "policy",
        "permission",
        "positive",
        ("allowed", "permitted", "can", "duoc phep"),
    ),
)
_ACTION_STOPWORDS = {
    "a",
    "an",
    "are",
    "be",
    "for",
    "is",
    "owners",
    "owner",
    "the",
    "to",
    "vehicle",
    "xe",
}


class _MetadataClaim(NamedTuple):
    chunk: Chunk
    entity: str
    attribute: str
    value: str
    effective_date: str | None
    version: str | None


class _SemanticClaim(NamedTuple):
    chunk: Chunk
    entity: str
    conflict_type: str
    axis: str
    polarity: str
    action_tokens: frozenset[str]
    span: str


def metadata_rule_findings(chunks: list[Chunk]) -> list[KnowledgeQualityFinding]:
    """Return conflicts backed by explicit source metadata."""

    groups: dict[tuple[str, str], list[_MetadataClaim]] = defaultdict(list)
    for chunk in chunks:
        claim = _metadata_claim(chunk)
        if claim is not None:
            groups[(_normalize(claim.entity), _normalize(claim.attribute))].append(claim)

    findings: list[KnowledgeQualityFinding] = []
    for claims in groups.values():
        for left_index, left in enumerate(claims):
            for right in claims[left_index + 1 :]:
                if _normalize(left.value) == _normalize(right.value):
                    continue
                if _explicitly_supersedes(left.chunk, right.chunk):
                    continue
                conflict_type = (
                    "temporal"
                    if left.effective_date != right.effective_date or left.version != right.version
                    else "entity_relation"
                )
                chunk_ids = sorted([left.chunk.chunk_id, right.chunk.chunk_id])
                findings.append(
                    KnowledgeQualityFinding(
                        finding_id=_finding_id(
                            "metadata_rules",
                            conflict_type,
                            chunk_ids,
                        ),
                        kind="conflict",
                        severity="warning",
                        chunk_ids=chunk_ids,
                        summary=(
                            f"{left.entity} has conflicting {left.attribute} metadata: "
                            f"{left.value} vs {right.value}."
                        ),
                        suggested_action=(
                            "Review source authority and effective dates before selecting a value."
                        ),
                        confidence=0.9,
                        metadata={
                            "method": "metadata_rules",
                            "conflict_type": conflict_type,
                            "entity": left.entity,
                            "attribute": left.attribute,
                            "left_value": left.value,
                            "right_value": right.value,
                            "left_effective_date": left.effective_date,
                            "right_effective_date": right.effective_date,
                        },
                    )
                )
    return findings


def semantic_rule_findings(chunks: list[Chunk]) -> list[KnowledgeQualityFinding]:
    """Return modal and recommendation conflicts without model calls."""

    claims = [claim for chunk in chunks if (claim := _semantic_claim(chunk)) is not None]
    findings: list[KnowledgeQualityFinding] = []
    for left_index, left in enumerate(claims):
        for right in claims[left_index + 1 :]:
            if left.chunk.chunk_id == right.chunk.chunk_id:
                continue
            if left.entity != right.entity or left.axis != right.axis:
                continue
            if left.polarity == right.polarity:
                continue
            if _token_similarity(left.action_tokens, right.action_tokens) < 0.6:
                continue
            chunk_ids = sorted([left.chunk.chunk_id, right.chunk.chunk_id])
            findings.append(
                KnowledgeQualityFinding(
                    finding_id=_finding_id(
                        "semantic_rules",
                        left.conflict_type,
                        chunk_ids,
                    ),
                    kind="conflict",
                    severity="warning",
                    chunk_ids=chunk_ids,
                    summary=(f"Opposite {left.axis} statements were found for {left.entity}."),
                    suggested_action="Review the policy context and source authority.",
                    confidence=0.88,
                    metadata={
                        "method": "semantic_rules",
                        "conflict_type": left.conflict_type,
                        "entity": left.entity,
                        "axis": left.axis,
                        "verdict": "contradiction",
                        "evidence_spans": [left.span, right.span],
                    },
                )
            )
    return findings


def _metadata_claim(chunk: Chunk) -> _MetadataClaim | None:
    entity = chunk.metadata.get("entity")
    attribute = chunk.metadata.get("attribute")
    value = chunk.metadata.get("value")
    if not all(isinstance(item, str) and item.strip() for item in (entity, attribute, value)):
        return None
    return _MetadataClaim(
        chunk=chunk,
        entity=str(entity).strip(),
        attribute=str(attribute).strip(),
        value=str(value).strip(),
        effective_date=_optional_text(chunk.metadata.get("effective_date")),
        version=_optional_text(chunk.metadata.get("version")),
    )


def _semantic_claim(chunk: Chunk) -> _SemanticClaim | None:
    normalized = _normalize(chunk.text)
    for conflict_type, axis, polarity, phrases in _SEMANTIC_MODALITIES:
        phrase = next(
            (
                candidate
                for candidate in phrases
                if re.search(rf"\b{re.escape(candidate)}\b", normalized)
            ),
            None,
        )
        if phrase is None:
            continue
        action = re.sub(rf"\b{re.escape(phrase)}\b", " ", normalized)
        entity = _normalized_entity(chunk.text)
        action_tokens = frozenset(
            token
            for token in action.split()
            if token not in _ACTION_STOPWORDS and token not in entity.split()
        )
        return _SemanticClaim(
            chunk=chunk,
            entity=entity,
            conflict_type=conflict_type,
            axis=axis,
            polarity=polarity,
            action_tokens=action_tokens,
            span=chunk.text.strip(),
        )
    return None


def _explicitly_supersedes(left: Chunk, right: Chunk) -> bool:
    return _supersedes(left, right) or _supersedes(right, left)


def _supersedes(newer: Chunk, older: Chunk) -> bool:
    raw = newer.metadata.get("supersedes") or newer.metadata.get("replaces")
    values = raw if isinstance(raw, list) else [raw]
    older_ids = {
        str(value)
        for value in (
            older.chunk_id,
            older.metadata.get("document_id"),
            older.metadata.get("source"),
        )
        if value is not None
    }
    return any(str(value) in older_ids for value in values if value is not None)


def _normalized_entity(text: str) -> str:
    match = _ENTITY_RE.search(text)
    return _normalize(match.group(0)).replace("vinfast ", "") if match else "global"


def _normalize(value: str) -> str:
    value = value.casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())


def _optional_text(value: object) -> str | None:
    return str(value).strip() if value is not None and str(value).strip() else None


def _token_similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _finding_id(method: str, conflict_type: str, chunk_ids: list[str]) -> str:
    raw = f"{method}:{conflict_type}:{'|'.join(chunk_ids)}"
    return f"kq-{hashlib.sha1(raw.encode()).hexdigest()[:12]}"
