"""Layer 2: near-duplicate detection with token-shingle SimHash."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from agentic_rag.ingestion.dedup_detect.models import DedupDocument, DuplicateMatch
from agentic_rag.ingestion.dedup_detect.normalization import dedup_text, normalize_text

_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)


def simhash_fingerprint(text: str, *, bits: int = 64, shingle_size: int = 4) -> int:
    """Return a SimHash fingerprint for normalized token shingles."""

    if bits <= 0:
        raise ValueError("bits must be positive.")
    if shingle_size <= 0:
        raise ValueError("shingle_size must be positive.")

    tokens = _TOKEN_RE.findall(normalize_text(text))
    if not tokens:
        return 0
    shingles = _token_shingles(tokens, shingle_size=shingle_size)
    weights = [0] * bits
    for shingle in shingles:
        digest = hashlib.sha256(shingle.encode("utf-8")).digest()
        value = int.from_bytes(digest, "big")
        for bit in range(bits):
            if value & (1 << bit):
                weights[bit] += 1
            else:
                weights[bit] -= 1

    fingerprint = 0
    for bit, weight in enumerate(weights):
        if weight >= 0:
            fingerprint |= 1 << bit
    return fingerprint


def hamming_distance(left: int, right: int) -> int:
    """Return Hamming distance between two integer fingerprints."""

    return (left ^ right).bit_count()


def find_simhash_duplicates(
    documents: Iterable[DedupDocument],
    *,
    bits: int = 64,
    shingle_size: int = 4,
    hamming_threshold: int = 6,
    exclude_pairs: set[tuple[str, str]] | None = None,
    exclude_chunk_ids: set[str] | None = None,
) -> list[DuplicateMatch]:
    """Find near-duplicate document pairs by SimHash Hamming distance.

    ``exclude_chunk_ids`` skips any document that was already caught as a
    duplicate by an earlier layer — ensuring chunk-level cascade (once flagged,
    done) rather than only pair-level deduplication.
    """

    if hamming_threshold < 0:
        raise ValueError("hamming_threshold must be non-negative.")

    excluded_pairs = exclude_pairs or set()
    excluded_chunks = exclude_chunk_ids or set()
    indexed = [
        (
            document,
            simhash_fingerprint(dedup_text(document), bits=bits, shingle_size=shingle_size),
        )
        for document in documents
        if document.document_id not in excluded_chunks
    ]
    matches: list[DuplicateMatch] = []
    for left_index, (left, left_hash) in enumerate(indexed):
        for right, right_hash in indexed[left_index + 1 :]:
            pair = _pair_key(left.document_id, right.document_id)
            if pair in excluded_pairs:
                continue
            distance = hamming_distance(left_hash, right_hash)
            if distance > hamming_threshold:
                continue
            matches.append(
                DuplicateMatch(
                    layer="simhash",
                    document_id=left.document_id,
                    duplicate_document_id=right.document_id,
                    score=round(1.0 - (distance / bits), 6),
                    distance=distance,
                    fingerprint=f"{left_hash:0{bits // 4}x}:{right_hash:0{bits // 4}x}",
                    reason="SimHash Hamming distance within threshold",
                    metadata={
                        "bits": bits,
                        "shingle_size": shingle_size,
                        "hamming_threshold": hamming_threshold,
                    },
                )
            )
    return matches


def _token_shingles(tokens: list[str], *, shingle_size: int) -> list[str]:
    if len(tokens) <= shingle_size:
        return [" ".join(tokens)]
    return [
        " ".join(tokens[index : index + shingle_size])
        for index in range(len(tokens) - shingle_size + 1)
    ]


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)
