"""Shared chunker protocols and default chunker implementations."""

from __future__ import annotations

from typing import Protocol

from agentic_rag.ingestion.chunking.models import ChunkCandidate, ChunkingInput
from agentic_rag.ingestion.chunking.splitters import chunk_markdown


class Chunker(Protocol):
    """Strategy interface for splitting normalized parser output."""

    chunker_name: str
    requires_native_document: bool

    def chunk(self, chunking_input: ChunkingInput) -> list[ChunkCandidate]:
        """Split normalized parser output into chunk candidates."""


class TextChunkingStrategy(Protocol):
    """Strategy that splits normalized Markdown/text into chunk strings."""

    @property
    def provider(self) -> str:
        """Provider name used by the strategy."""

    @property
    def model(self) -> str:
        """Model name used by the strategy."""

    def split(self, chunking_input: ChunkingInput) -> list[str]:
        """Return chunk strings for the provided text."""


class DeterministicMarkdownChunker:
    """Default deterministic section-aware character chunker."""

    chunker_name = "deterministic"
    requires_native_document = False

    def chunk(self, chunking_input: ChunkingInput) -> list[ChunkCandidate]:
        """Split normalized Markdown with the shared deterministic implementation."""

        return chunk_markdown(chunking_input.markdown)
