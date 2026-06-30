"""Metadata-first candidate generation for L2 duplicate review."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from itertools import combinations

from agentic_rag.ingestion.dedup_detect.blocking.keys import metadata_block_key
from agentic_rag.ingestion.dedup_detect.models import DedupDocument


def build_metadata_blocks(
    documents: Sequence[DedupDocument], *, max_block_size: int = 50
) -> dict[str, tuple[DedupDocument, ...]]:
    """Group documents by stable metadata and quarantine overly broad blocks."""

    if max_block_size < 2:
        raise ValueError("max_block_size must be at least 2.")
    blocks: dict[str, list[DedupDocument]] = defaultdict(list)
    for document in documents:
        blocks[metadata_block_key(document.metadata)].append(document)
    return {
        key: tuple(block)
        for key, block in sorted(blocks.items())
        if 2 <= len(block) <= max_block_size
    }


def blocked_candidate_pairs(
    documents: Sequence[DedupDocument], *, max_block_size: int = 50
) -> list[tuple[DedupDocument, DedupDocument]]:
    """Return deterministic pairs only from bounded compatible blocks."""

    pairs: list[tuple[DedupDocument, DedupDocument]] = []
    seen: set[tuple[str, str]] = set()
    for block in build_metadata_blocks(documents, max_block_size=max_block_size).values():
        for left, right in combinations(block, 2):
            key = (
                min(left.document_id, right.document_id),
                max(left.document_id, right.document_id),
            )
            if key not in seen:
                seen.add(key)
                pairs.append((left, right))
    return pairs
