"""Layer 1: exact duplicate detection with SHA-256 over normalized text."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable

from agentic_rag.ingestion.dedup_detect.models import DedupDocument, DuplicateMatch
from agentic_rag.ingestion.dedup_detect.normalization import dedup_text, normalize_text


def sha256_fingerprint(text: str) -> str:
    """Return SHA-256 of normalized text."""

    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def find_exact_duplicates(documents: Iterable[DedupDocument]) -> list[DuplicateMatch]:
    """Find documents with the same normalized text SHA-256."""

    by_fingerprint: dict[str, list[DedupDocument]] = defaultdict(list)
    for document in documents:
        fingerprint = document.metadata.get("dedupe_hash")
        if not fingerprint:
            fingerprint = sha256_fingerprint(dedup_text(document))
        by_fingerprint[fingerprint].append(document)

    matches: list[DuplicateMatch] = []
    for fingerprint, group in sorted(by_fingerprint.items()):
        if len(group) < 2:
            continue
        canonical = group[0]
        for duplicate in group[1:]:
            matches.append(
                DuplicateMatch(
                    layer="exact_sha256",
                    document_id=canonical.document_id,
                    duplicate_document_id=duplicate.document_id,
                    score=1.0,
                    distance=0,
                    fingerprint=fingerprint,
                    reason="same normalized text SHA-256",
                )
            )
    return matches
