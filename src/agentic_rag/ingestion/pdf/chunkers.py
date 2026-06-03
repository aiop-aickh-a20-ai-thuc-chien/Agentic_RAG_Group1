"""Markdown chunker strategies for PDF ingestion."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from agentic_rag.ingestion.chunking import (
    ChunkingInput,
    MarkdownChunk,
)
from agentic_rag.ingestion.chunking import (
    DeterministicMarkdownChunker as SharedDeterministicMarkdownChunker,
)

DETERMINISTIC_MARKDOWN_CHUNKER = "deterministic"
DOCLING_HYBRID_CHUNKER = "docling-hybrid"
DEFAULT_MARKDOWN_CHUNKER = DETERMINISTIC_MARKDOWN_CHUNKER


class MarkdownChunker(Protocol):
    """Strategy interface for converting parser Markdown into chunk candidates."""

    chunker_name: str
    requires_native_document: bool

    def chunk(self, chunking_input: ChunkingInput) -> list[MarkdownChunk]:
        """Split Markdown into chunk candidates."""


class DeterministicMarkdownChunker(SharedDeterministicMarkdownChunker):
    """Default deterministic section-aware character chunker."""


class DoclingHybridChunker:
    """Docling-native HybridChunker adapter for parser-native PDF documents."""

    chunker_name = DOCLING_HYBRID_CHUNKER
    requires_native_document = True

    def __init__(self, hybrid_chunker_factory: Callable[[], Any] | None = None) -> None:
        self._hybrid_chunker_factory = hybrid_chunker_factory or _default_hybrid_chunker_factory

    def chunk(self, chunking_input: ChunkingInput) -> list[MarkdownChunk]:
        """Split a Docling document with Docling HybridChunker."""

        if chunking_input.native_document is None:
            raise ValueError("Docling hybrid chunking requires parser-native document output.")

        hybrid_chunker = self._hybrid_chunker_factory()
        chunks: list[MarkdownChunk] = []
        for docling_chunk in hybrid_chunker.chunk(chunking_input.native_document):
            raw_text = str(getattr(docling_chunk, "text", "")).strip()
            section_path = _section_path_from_docling_chunk(docling_chunk)
            text = str(hybrid_chunker.contextualize(docling_chunk)).strip()
            if not text:
                text = raw_text
            if text:
                chunks.append(
                    MarkdownChunk(
                        section=_section_from_section_path(section_path),
                        text=text,
                        metadata={
                            "section_path": section_path,
                            "raw_text": raw_text,
                        },
                    )
                )
        return chunks


class MarkdownChunkerDefinition(BaseModel):
    """Registered Markdown chunker factory."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    name: str
    factory: Callable[[], MarkdownChunker]


_MARKDOWN_CHUNKER_REGISTRY: dict[str, MarkdownChunkerDefinition] = {
    DETERMINISTIC_MARKDOWN_CHUNKER: MarkdownChunkerDefinition(
        name=DETERMINISTIC_MARKDOWN_CHUNKER,
        factory=DeterministicMarkdownChunker,
    ),
    DOCLING_HYBRID_CHUNKER: MarkdownChunkerDefinition(
        name=DOCLING_HYBRID_CHUNKER,
        factory=DoclingHybridChunker,
    ),
}


def resolve_markdown_chunker(chunker_name: str | None = None) -> MarkdownChunker:
    """Resolve a supported Markdown chunker name to a fresh chunker instance."""

    normalized_name = _normalize_chunker_name(chunker_name)
    definition = _MARKDOWN_CHUNKER_REGISTRY.get(normalized_name)
    if definition is None:
        raise ValueError(
            "Unsupported Markdown chunker: "
            f"{chunker_name}. Supported chunkers: {', '.join(supported_markdown_chunkers())}."
        )
    return definition.factory()


def supported_markdown_chunkers() -> tuple[str, ...]:
    """Return registered Markdown chunker names in stable order."""

    return tuple(sorted(_MARKDOWN_CHUNKER_REGISTRY))


def _normalize_chunker_name(chunker_name: str | None) -> str:
    if chunker_name is None:
        return DEFAULT_MARKDOWN_CHUNKER
    return chunker_name.strip().lower().replace("_", "-")


def _default_hybrid_chunker_factory() -> Any:
    from docling_core.transforms.chunker.hybrid_chunker import HybridChunker

    return HybridChunker()


def _section_path_from_docling_chunk(docling_chunk: Any) -> list[str]:
    meta = getattr(docling_chunk, "meta", None)
    headings = getattr(meta, "headings", None)
    if not headings:
        return []
    return [str(heading).strip() for heading in headings if str(heading).strip()]


def _section_from_section_path(section_path: list[str]) -> str | None:
    return " > ".join(section_path) or None
