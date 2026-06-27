"""Quality gates — cheap merge-time filters that drop junk/poisoned triples.

Applied in stage [3] BEFORE anything enters the graph. The LLM cannot reliably
self-filter these, so we gate deterministically.
"""

from __future__ import annotations

import os

from kg.embeddings import norm_text
from kg.schema import OpenTriple

# Vietnamese pronouns / demonstratives = unresolved coreference -> drop the edge
PRONOUN_STOPLIST = {
    "xe này",
    "xe đó",
    "xe ấy",
    "hãng",
    "nó",
    "sản phẩm này",
    "dòng này",
    "cái này",
    "chiếc này",
    "mẫu này",
    "họ",
    "chúng",
    "này",
    "đó",
    "chúng tôi",
}

GENERIC_TYPES = {"generic", "other", "unknown", "accessory", ""}

# Narrative/policy docs leak whole CLAUSES as endpoints/predicates ("bất cứ thời điểm
# nào trong ngày và tất cả..."). Instead of a hard-coded char limit, we flag spans
# whose length is a statistical OUTLIER vs the corpus itself (Tukey upper fence). The
# only constant is the textbook outlier multiplier — not a domain/data assumption.
OUTLIER_K = float(os.getenv("KG_OUTLIER_K", "2.5"))


def _upper_fence(values: list[int], k: float) -> float | None:
    """Tukey upper fence Q3 + k·IQR. None when there's too little data or no spread
    (so nothing is dropped unless a genuine long tail of clauses exists)."""
    if len(values) < 8:
        return None
    s = sorted(values)
    q1, q3 = s[len(s) // 4], s[(3 * len(s)) // 4]
    iqr = q3 - q1
    return q3 + k * iqr if iqr > 0 else None


def length_fences(staged) -> tuple[float | None, float | None]:
    """Adaptive (endpoint_max, predicate_max) derived from the corpus length
    distribution — no hard-coded character limits."""
    ep = [len(t.subject.strip()) for t in staged] + [len(t.object.strip()) for t in staged]
    pr = [len(t.predicate.strip()) for t in staged]
    return _upper_fence(ep, OUTLIER_K), _upper_fence(pr, OUTLIER_K)


def is_pronoun(s: str) -> bool:
    return norm_text(s) in PRONOUN_STOPLIST


def evidence_locates(evidence: str, chunk_text: str) -> tuple[int, int] | None:
    """Return (start, end) offset if the evidence is a real substring of the
    chunk (under NFC+lowercase+collapse), else None. Catches hallucinated quotes."""

    if not evidence:
        return None
    e, c = norm_text(evidence), norm_text(chunk_text)
    idx = c.find(e)
    return (idx, idx + len(e)) if idx >= 0 else None


def gate_triple(
    t: OpenTriple,
    chunk_text: str,
    endpoint_max: float | None = None,
    predicate_max: float | None = None,
) -> tuple[bool, str, tuple[int, int] | None]:
    """Return (keep, reason, evidence_offset). `endpoint_max`/`predicate_max` are the
    adaptive clause fences from `length_fences` (None disables the length gate)."""

    if is_pronoun(t.subject) or is_pronoun(t.object):
        return False, "pronoun_endpoint", None
    if norm_text(t.subject_type) in GENERIC_TYPES and norm_text(t.object_type) in GENERIC_TYPES:
        return False, "both_generic", None
    if endpoint_max is not None and (
        len(t.subject.strip()) > endpoint_max or len(t.object.strip()) > endpoint_max
    ):
        return False, "clause_endpoint", None
    if predicate_max is not None and len(t.predicate.strip()) > predicate_max:
        return False, "clause_predicate", None
    offset = evidence_locates(t.evidence, chunk_text)
    if offset is None:
        return False, "evidence_not_found", None
    return True, "ok", offset
