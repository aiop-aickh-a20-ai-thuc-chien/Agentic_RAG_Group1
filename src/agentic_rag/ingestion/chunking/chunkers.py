"""Shared chunker protocols and default chunker implementations."""

# TODO [guide_2/vinfast_pipeline_todo §6 – Chunking Strategy for RAG]:
# Add a `ProductChunker` that splits each product variant into an independent
# Document before ingestion, then further splits specs by semantic category:
#   - range_charging  → range_km, charging_time, battery capacity
#   - safety          → ADAS, airbag, safety ratings
#   - dimensions      → kích thước, trọng lượng, khoang chứa đồ
#   - interior        → nội thất, màn hình, tiện nghi
#   - pricing         → giá, tùy chọn pin, khuyến mãi
# Each chunk must carry full metadata: model, variant, battery_option, category,
# scraped_at, and a deterministic chunk_id.
# Reference: guide_2/vinfast_pipeline_todo (1).md §6

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

        # TODO [guide_2/vinfast_pipeline_todo §6 – Product variant isolation]:
        # For VinFast product pages, each trim/variant (e.g. VF 9 Eco, VF 9 Plus)
        # should be a separate Document *before* this chunker runs.
        # This chunker currently receives a single merged Markdown string and may
        # mix variant-specific facts (price, range, options) across chunks.
        # Coordinate with the upstream loader to pass pre-split variant texts.
        # Reference: guide_2/vinfast_pipeline_todo (1).md §6
        return chunk_markdown(chunking_input.markdown)
