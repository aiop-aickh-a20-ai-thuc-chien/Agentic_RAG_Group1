import pytest
from pydantic import BaseModel

from agentic_rag.ingestion.pdf.chunkers import (
    DeterministicMarkdownChunker,
    DoclingHybridChunker,
    DoclingPageAwareChunker,
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


class FakeProvenance:
    def __init__(self, page_no: int) -> None:
        self.page_no = page_no


class FakeTextItem:
    label = "text"

    def __init__(
        self,
        text: str,
        page_no: int | None = None,
        *,
        page_numbers: list[int] | None = None,
        label: str = "text",
    ) -> None:
        self.label = label
        self.text = text
        resolved_pages = page_numbers if page_numbers is not None else [page_no]
        self.prov = [
            FakeProvenance(page_number) for page_number in resolved_pages if page_number is not None
        ]


class FakeTableItem:
    label = "table"

    def __init__(self, markdown: str, page_no: int | None) -> None:
        self._markdown = markdown
        self.prov = [FakeProvenance(page_no)] if page_no is not None else []

    def export_to_markdown(self, doc: object | None = None) -> str:
        return self._markdown


class FakePictureItem:
    label = "picture"

    def __init__(self, page_no: int) -> None:
        self.prov = [FakeProvenance(page_no)]


class FakeDoclingDocument:
    def __init__(self, items: list[object]) -> None:
        self._items = items

    def iterate_items(self, *args: object, **kwargs: object) -> list[tuple[object, int]]:
        return [(item, 0) for item in self._items]


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


def test_docling_page_aware_chunker_requires_native_document() -> None:
    chunker = resolve_markdown_chunker("docling-page-aware")

    assert isinstance(chunker, DoclingPageAwareChunker)
    assert chunker.requires_native_document is True
    with pytest.raises(ValueError, match="requires parser-native"):
        chunker.chunk(_chunking_input("# Warranty\nContent"))


def test_docling_page_aware_chunker_maps_docling_provenance_to_page_metadata() -> None:
    native_document = FakeDoclingDocument(
        [
            FakeTextItem("# Warranty\nPin VF8 duoc bao hanh 8 nam.", page_no=2),
            FakePictureItem(page_no=2),
            FakeTextItem("# Service\nBao duong tai showroom.", page_no=3),
            FakeTableItem("| A | B |\n|---|---|\n| 1 | 2 |", page_no=4),
        ]
    )
    chunker = resolve_markdown_chunker("docling-page-aware")

    chunks = chunker.chunk(_chunking_input("", native_document=native_document))

    assert [chunk.metadata["page"] for chunk in chunks] == [2, 3, 4]
    assert [chunk.metadata["page_range"] for chunk in chunks] == [[2, 2], [3, 3], [4, 4]]
    assert chunks[0].section == "Warranty"
    assert chunks[0].text == "Pin VF8 duoc bao hanh 8 nam."
    assert chunks[1].section == "Service"
    assert chunks[2].text == "| A | B |\n|---|---|\n| 1 | 2 |"


def test_docling_page_aware_chunker_preserves_multi_page_provenance() -> None:
    native_document = FakeDoclingDocument(
        [
            FakeTextItem(
                "# Warranty\nPolicy spans pages.",
                page_numbers=[2, 3],
            )
        ]
    )
    chunker = resolve_markdown_chunker("docling-page-aware")

    chunks = chunker.chunk(_chunking_input("", native_document=native_document))

    assert len(chunks) == 1
    assert chunks[0].metadata["page"] == 2
    assert chunks[0].metadata["pages"] == [2, 3]
    assert chunks[0].metadata["page_range"] == [2, 3]


def test_docling_page_aware_chunker_converts_native_headings_to_markdown() -> None:
    native_document = FakeDoclingDocument(
        [
            FakeTextItem("Warranty", page_no=2, label="title"),
            FakeTextItem("Battery", page_no=2, label="section_header"),
            FakeTextItem("Pin VF8 duoc bao hanh 8 nam.", page_no=2),
        ]
    )
    chunker = resolve_markdown_chunker("docling-page-aware")

    chunks = chunker.chunk(_chunking_input("", native_document=native_document))

    assert len(chunks) == 1
    assert chunks[0].section == "Battery"
    assert chunks[0].text == "Pin VF8 duoc bao hanh 8 nam."
    assert chunks[0].metadata["page"] == 2


def test_docling_page_aware_chunker_keeps_chunks_when_provenance_is_missing() -> None:
    native_document = FakeDoclingDocument([FakeTextItem("# Warranty\nNoi dung.", page_no=None)])
    chunker = resolve_markdown_chunker("docling-page-aware")

    chunks = chunker.chunk(_chunking_input("", native_document=native_document))

    assert len(chunks) == 1
    assert chunks[0].metadata == {"page": None}
    assert chunks[0].text == "Noi dung."


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
