"""Contracts for ingestion duplicate detection."""

from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DuplicateLayer = Literal[
    "exact_sha256", "metadata_llm", "simhash", "embedding_similarity"
]
DuplicateClassification = Literal["duplicate", "not_duplicate", "needs_review"]


class _DedupModel(BaseModel):
    """Base model for strict ingestion duplicate-detection contracts."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class DedupDocument(_DedupModel):
    """Text document or chunk prepared for duplicate detection."""

    document_id: str = Field(min_length=1)
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    # TODO [url/TODO_dedup.md §3 – URL blocking metadata fields]:
    # For URL-sourced chunks, the metadata dict should contain the blocking keys
    # that `build_metadata_blocks()` uses for SimHash/embedding candidate pairing:
    #   - domain, page_type, entity_type, entity_name, attribute_group, language
    #   - entity_hash, vehicle_segment (for VinFast-specific grouping)
    # Verify these fields are populated by `enrich_chunks_with_url_metadata()`
    # before chunks reach this layer.
    # Reference: url/TODO_dedup.md §3


class DedupConfig(_DedupModel):
    """Configuration for the three duplicate-detection layers."""

    enable_exact: bool = True
    enable_simhash: bool = True
    enable_embedding: bool = False
    enable_metadata_llm: bool = False
    metadata_block_max_size: int = Field(default=50, ge=2)
    simhash_bits: int = Field(default=64, ge=8, le=256)
    simhash_shingle_size: int = Field(default=4, ge=1, le=12)
    simhash_hamming_threshold: int = Field(default=6, ge=0)
    embedding_similarity_threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    embedding_method: str | None = None
    embedding_batch_size: int = Field(
        default_factory=lambda: int(os.getenv("DEDUP_EMBEDDING_BATCH_SIZE", "32")),
        ge=1,
    )


class DuplicateMatch(_DedupModel):
    """One duplicate or near-duplicate pair detected by a specific layer."""

    layer: DuplicateLayer
    document_id: str
    duplicate_document_id: str
    score: float = Field(ge=0.0, le=1.0)
    distance: int | None = Field(default=None, ge=0)
    fingerprint: str | None = None
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DuplicateReview(_DedupModel):
    """Conservative L2 classification for one metadata-blocked pair."""

    classification: DuplicateClassification
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    document_id: str
    duplicate_document_id: str
    compared_metadata_fields: dict[str, tuple[str, str]] = Field(default_factory=dict)
    cited_chunk_ids: tuple[str, str]
    evidence_refs: tuple[str, ...] = ()
    pair_category: str = "cross_source_representation"


class DedupReport(_DedupModel):
    """Duplicate detection result across all enabled layers."""

    document_count: int
    exact_matches: list[DuplicateMatch] = Field(default_factory=list)
    simhash_matches: list[DuplicateMatch] = Field(default_factory=list)
    embedding_matches: list[DuplicateMatch] = Field(default_factory=list)
    metadata_llm_matches: list[DuplicateMatch] = Field(default_factory=list)
    metadata_reviews: list[DuplicateReview] = Field(default_factory=list)

    @property
    def matches(self) -> list[DuplicateMatch]:
        """Return all matches in layer order."""

        return [
            *self.exact_matches,
            *self.metadata_llm_matches,
            *self.simhash_matches,
            *self.embedding_matches,
        ]
