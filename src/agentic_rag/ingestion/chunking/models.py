"""Shared models for ingestion chunking."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _IngestionChunkingModel(BaseModel):
    """Base configuration for shared ingestion chunking models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class MarkdownSection(_IngestionChunkingModel):
    """A Markdown section associated with the nearest heading."""

    title: str | None
    level: int = 0
    path: tuple[str, ...] = ()
    text: str


class ChunkCandidate(_IngestionChunkingModel):
    """A chunk of Markdown/text ready to map into a shared Chunk contract."""

    section: str | None
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    section_level: int = 0
    section_path: tuple[str, ...] = ()
    chunk_token_count: int | None = None
    semantic_unit: str | None = None


MarkdownChunk = ChunkCandidate


class ChunkingInput(_IngestionChunkingModel):
    """Normalized parser output passed into ingestion chunkers."""

    markdown: str
    source_type: str | None = None
    parser: str | None = None
    source_path: str | None = None
    native_document: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
