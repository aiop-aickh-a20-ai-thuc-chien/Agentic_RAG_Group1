"""Contracts for ingestion duplicate detection."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DuplicateLayer = Literal["exact_sha256", "simhash", "embedding_similarity"]


class _DedupModel(BaseModel):
    """Base model for strict ingestion duplicate-detection contracts."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class DedupDocument(_DedupModel):
    """Text document or chunk prepared for duplicate detection."""

    document_id: str = Field(min_length=1)
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DedupConfig(_DedupModel):
    """Configuration for the three duplicate-detection layers."""

    enable_exact: bool = True
    enable_simhash: bool = True
    enable_embedding: bool = False
    simhash_bits: int = Field(default=64, ge=8, le=256)
    simhash_shingle_size: int = Field(default=4, ge=1, le=12)
    simhash_hamming_threshold: int = Field(default=6, ge=0)
    embedding_similarity_threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    embedding_method: str | None = None


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


class DedupReport(_DedupModel):
    """Duplicate detection result across all enabled layers."""

    document_count: int
    exact_matches: list[DuplicateMatch] = Field(default_factory=list)
    simhash_matches: list[DuplicateMatch] = Field(default_factory=list)
    embedding_matches: list[DuplicateMatch] = Field(default_factory=list)

    @property
    def matches(self) -> list[DuplicateMatch]:
        """Return all matches in layer order."""

        return [*self.exact_matches, *self.simhash_matches, *self.embedding_matches]
