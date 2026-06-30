"""Metadata blocking for L2 duplicate review."""

from agentic_rag.ingestion.dedup_detect.blocking.keys import (
    EMPTY_BUCKET,
    metadata_block_key,
    normalize_block_value,
)
from agentic_rag.ingestion.dedup_detect.blocking.metadata import (
    blocked_candidate_pairs,
    build_metadata_blocks,
)

__all__ = [
    "EMPTY_BUCKET",
    "blocked_candidate_pairs",
    "build_metadata_blocks",
    "metadata_block_key",
    "normalize_block_value",
]
