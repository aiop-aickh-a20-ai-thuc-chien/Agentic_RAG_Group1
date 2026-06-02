import pytest
from pydantic import BaseModel

from agentic_rag.ingestion.pdf.chunkers import (
    DeterministicMarkdownChunker,
    DoclingHybridChunker,
    MarkdownChunkerDefinition,
    resolve_markdown_chunker,
    supported_markdown_chunkers,
)
from agentic_rag.ingestion.pdf.models import PdfChunkingInput


class FakeDoclingChunkMeta:
    def __init__(self, headings: list[str] | None = None) -> None:
        self.headings = headings


class FakeDoclingChunk:
    def __init__(self, text: str, headings: list[str] | None = None) -> None:
        self.text = text
        self.meta = FakeDoclingChunkMeta(headings=headings)


class FakeHybridChunker:
    def __init__(self) -> None:
        self.seen_document: object | None = None

    def chunk(self, native_document: object) -> list[FakeDoclingChunk]:
        self.seen_document = native_document
        return [FakeDoclingChunk("raw chunk", headings=["Warranty", "Battery"])]

    def contextualize(self, chunk: FakeDoclingChunk) -> str:
        return f"context: {chunk.text}"


def _chunking_input(
    markdown: str,
    *,
    native_document: object | None = None,
) -> PdfChunkingInput:
    return PdfChunkingInput(
        markdown=markdown,
        parser="docling",
        source_path="source.pdf",
        native_document=native_document,
    )


def test_default_chunker_wraps_existing_markdown_chunking() -> None:
    chunker = resolve_markdown_chunker(None)

    chunks = chunker.chunk(_chunking_input("# Warranty\nPin duoc bao hanh 8 nam."))

    assert isinstance(chunker, DeterministicMarkdownChunker)
    assert chunker.requires_native_document is False
    assert len(chunks) == 1
    assert chunks[0].section == "Warranty"
    assert chunks[0].text == "Pin duoc bao hanh 8 nam."


def test_supported_markdown_chunkers_lists_default_and_docling_hybrid() -> None:
    assert supported_markdown_chunkers() == ("deterministic", "docling-hybrid")


def test_docling_hybrid_chunker_requires_native_document() -> None:
    chunker = resolve_markdown_chunker("docling-hybrid")

    assert isinstance(chunker, DoclingHybridChunker)
    assert chunker.requires_native_document is True
    with pytest.raises(ValueError, match="requires parser-native"):
        chunker.chunk(_chunking_input("# Warranty\nContent"))


def test_docling_hybrid_chunker_maps_contextualized_text_and_headings() -> None:
    fake_hybrid = FakeHybridChunker()
    native_document = object()
    chunker = DoclingHybridChunker(hybrid_chunker_factory=lambda: fake_hybrid)

    chunks = chunker.chunk(_chunking_input("", native_document=native_document))

    assert fake_hybrid.seen_document is native_document
    assert len(chunks) == 1
    assert chunks[0].text == "context: raw chunk"
    assert chunks[0].section == "Warranty > Battery"


def test_markdown_chunker_definition_is_pydantic_model() -> None:
    assert issubclass(MarkdownChunkerDefinition, BaseModel)


def test_resolve_markdown_chunker_rejects_unknown_chunker() -> None:
    with pytest.raises(ValueError, match="Unsupported Markdown chunker"):
        resolve_markdown_chunker("semantic")
