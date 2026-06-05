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
    chunker = resolve_markdown_chunker("deterministic")

    chunks = chunker.chunk(_chunking_input("# Warranty\nPin duoc bao hanh 8 nam."))

    assert isinstance(chunker, DeterministicMarkdownChunker)
    assert chunker.requires_native_document is False
    assert len(chunks) == 1
    assert chunks[0].section == "Warranty"
    assert chunks[0].text == "Pin duoc bao hanh 8 nam."


def test_default_chunker_is_deterministic() -> None:
    chunker = resolve_markdown_chunker(None)

    assert isinstance(chunker, DeterministicMarkdownChunker)
    assert chunker.requires_native_document is False


def test_supported_markdown_chunkers_lists_default_docling_aliases() -> None:
    assert supported_markdown_chunkers() == (
        "deterministic",
        "docling-hybrid",
        "docling-page-aware",
    )


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
    assert chunks[0].metadata == {
        "section_path": ["Warranty", "Battery"],
        "raw_text": "raw chunk",
    }


def test_docling_hybrid_chunker_handles_missing_headings() -> None:
    class HeadinglessHybridChunker(FakeHybridChunker):
        def chunk(self, native_document: object) -> list[FakeDoclingChunk]:
            self.seen_document = native_document
            return [FakeDoclingChunk("body only", headings=None)]

        def contextualize(self, chunk: FakeDoclingChunk) -> str:
            return chunk.text

    fake_hybrid = HeadinglessHybridChunker()
    chunker = DoclingHybridChunker(hybrid_chunker_factory=lambda: fake_hybrid)

    chunks = chunker.chunk(_chunking_input("", native_document=object()))

    assert chunks[0].section is None
    assert chunks[0].metadata == {
        "section_path": [],
        "raw_text": "body only",
    }


def test_markdown_chunker_definition_is_pydantic_model() -> None:
    assert issubclass(MarkdownChunkerDefinition, BaseModel)


def test_resolve_markdown_chunker_rejects_unknown_chunker() -> None:
    with pytest.raises(ValueError, match="Unsupported Markdown chunker"):
        resolve_markdown_chunker("semantic")
