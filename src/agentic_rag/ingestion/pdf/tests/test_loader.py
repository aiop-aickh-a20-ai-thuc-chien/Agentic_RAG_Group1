from pathlib import Path

import pytest
from pydantic import ValidationError

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.chunking import ChunkingInput
from agentic_rag.ingestion.pdf.chunkers import DeterministicMarkdownChunker
from agentic_rag.ingestion.pdf.chunking import MarkdownChunk
from agentic_rag.ingestion.pdf.loader import (
    LoadedPdfDocument,
    _load_pdf_chunks,
    _load_pdf_with_markdown,
    load_pdf_chunks,
    load_pdf_with_markdown,
)
from agentic_rag.ingestion.pdf.models import PdfParseResult
from agentic_rag.ingestion.pdf.parser import ParsedPdfDocument


class FakeParser:
    parser_name = "fake-parser"

    def __init__(self, markdown: str) -> None:
        self.markdown = markdown
        self.seen_path: Path | None = None
        self.parse_calls = 0
        self.parse_to_document_calls = 0

    def parse(self, path: Path) -> PdfParseResult:
        self.seen_path = path
        self.parse_calls += 1
        return PdfParseResult(
            parser=self.parser_name,
            source_path=str(path),
            markdown=self.markdown,
        )

    def parse_to_markdown(self, path: Path) -> str:
        self.seen_path = path
        return self.markdown

    def parse_to_document(self, path: Path) -> ParsedPdfDocument:
        self.seen_path = path
        self.parse_to_document_calls += 1
        return ParsedPdfDocument(markdown=self.markdown, document={"doc": path.name})


class FakeChunker:
    chunker_name = "fake-chunker"
    requires_native_document = False

    def __init__(self) -> None:
        self.seen_markdown: str | None = None
        self.seen_input: ChunkingInput | None = None

    def chunk(self, chunking_input: ChunkingInput) -> list[MarkdownChunk]:
        self.seen_input = chunking_input
        self.seen_markdown = chunking_input.markdown
        return [
            MarkdownChunk(
                section="Forced",
                text="Forced chunk text.",
                metadata={
                    "section_path": ["Forced"],
                    "raw_text": "Raw forced chunk text.",
                },
            )
        ]


class FakeNativeChunker:
    chunker_name = "fake-native-chunker"
    requires_native_document = True

    def __init__(self) -> None:
        self.seen_native_document: object | None = None

    def chunk(self, chunking_input: ChunkingInput) -> list[MarkdownChunk]:
        self.seen_native_document = chunking_input.native_document
        return [MarkdownChunk(section="Native", text="Native chunk text.")]


class FakeOfflineDoclingHybridChunker:
    chunker_name = "docling-hybrid"
    requires_native_document = True

    def chunk(self, chunking_input: ChunkingInput) -> list[MarkdownChunk]:
        raise OSError(
            "We couldn't connect to 'https://huggingface.co' and couldn't find "
            "the requested files in the cached files. local_files_only=True"
        )


def test_loaded_pdf_document_defaults_parser_and_chunker() -> None:
    loaded = LoadedPdfDocument(markdown="# Intro", chunks=[])

    assert loaded.parser == "docling"
    assert loaded.pipeline == "ocr"
    assert loaded.strategy == "docling"
    assert loaded.chunker == "deterministic"


def test_loaded_pdf_document_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        LoadedPdfDocument.model_validate(
            {
                "markdown": "# Intro",
                "chunks": [],
                "unexpected": True,
            }
        )


def test_load_pdf_chunks_maps_markdown_to_shared_chunks(tmp_path: Path) -> None:
    pdf_path = tmp_path / "VinFast Warranty.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    parser = FakeParser("# Warranty\nPin duoc bao hanh 8 nam.\n\n## Battery\nDieu kien ap dung.")

    chunks = _load_pdf_chunks(pdf_path, parser, chunker=DeterministicMarkdownChunker())

    assert all(isinstance(chunk, Chunk) for chunk in chunks)
    assert [chunk.chunk_id for chunk in chunks] == [
        "pdf_vinfast_warranty_c0001",
        "pdf_vinfast_warranty_c0002",
    ]
    assert chunks[0].text == "Pin duoc bao hanh 8 nam."
    updated_date = chunks[0].metadata.get("updated_date")
    assert isinstance(updated_date, str)
    assert updated_date
    expected_metadata = {
        "chunk_id": "pdf_vinfast_warranty_c0001",
        "source": str(pdf_path),
        "source_type": "pdf",
        "file_name": "VinFast Warranty.pdf",
        "page": None,
        "page_number": None,
        "section": "Warranty",
        "heading": "Warranty",
        "breadcrumb": ["Warranty"],
        "parser": "fake-parser",
        "chunking_method": "deterministic",
        "chunk_index": 1,
        "token_count": 6,
        "updated_date_source": "ingestion_start",
    }
    assert {k: v for k, v in chunks[0].metadata.items() if k != "updated_date"} == (
        expected_metadata
    )
    assert chunks[1].metadata["section"] == "Battery"
    assert parser.seen_path == pdf_path
    assert parser.parse_calls == 1
    assert parser.parse_to_document_calls == 0


def test_load_pdf_with_markdown_uses_supplied_chunker(tmp_path: Path) -> None:
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    parser = FakeParser("# Intro\nOriginal markdown.")
    chunker = FakeChunker()

    loaded = _load_pdf_with_markdown(pdf_path, parser, chunker=chunker)

    assert loaded.markdown == "# Intro\nOriginal markdown."
    assert loaded.chunks[0].text == "Forced chunk text."
    assert loaded.chunks[0].metadata["section"] == "Forced"
    assert loaded.chunks[0].metadata["heading"] == "Forced"
    assert loaded.chunks[0].metadata["breadcrumb"] == ["Forced"]
    assert loaded.chunks[0].metadata["section_path"] == ["Forced"]
    assert loaded.chunks[0].metadata["raw_text"] == "Raw forced chunk text."
    assert loaded.chunks[0].metadata["chunking_method"] == "fake-chunker"
    assert isinstance(chunker.seen_input, ChunkingInput)
    assert chunker.seen_input.parser == "fake-parser"
    assert chunker.seen_input.source_path == str(pdf_path)
    assert chunker.seen_markdown == "# Intro\nOriginal markdown."
    assert parser.parse_calls == 1
    assert parser.parse_to_document_calls == 0


def test_load_pdf_with_markdown_uses_document_parse_for_native_chunker(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    parser = FakeParser("# Intro\nOriginal markdown.")
    chunker = FakeNativeChunker()

    loaded = _load_pdf_with_markdown(pdf_path, parser, chunker=chunker)

    assert loaded.markdown == "# Intro\nOriginal markdown."
    assert loaded.parser == "fake-parser"
    assert loaded.pipeline == "ocr"
    assert loaded.strategy == "docling"
    assert loaded.chunker == "fake-native-chunker"
    assert loaded.chunks[0].text == "Native chunk text."
    assert loaded.chunks[0].metadata["section"] == "Native"
    assert loaded.chunks[0].metadata["chunking_method"] == "fake-native-chunker"
    assert chunker.seen_native_document == {"doc": "source.pdf"}
    assert parser.parse_calls == 0
    assert parser.parse_to_document_calls == 1


def test_load_pdf_with_markdown_falls_back_when_docling_hybrid_tokenizer_is_offline(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    parser = FakeParser("# Warranty\nPin duoc bao hanh 8 nam.")

    loaded = _load_pdf_with_markdown(
        pdf_path,
        parser,
        chunker=FakeOfflineDoclingHybridChunker(),
    )

    assert loaded.chunker == "deterministic"
    assert loaded.requested_chunker == "docling-hybrid"
    assert loaded.chunking_fallback_reason is not None
    assert "docling-hybrid unavailable" in loaded.chunking_fallback_reason
    assert loaded.chunks[0].text == "Pin duoc bao hanh 8 nam."
    assert loaded.chunks[0].metadata["chunking_method"] == "deterministic"
    assert parser.parse_calls == 0
    assert parser.parse_to_document_calls == 1


def test_load_pdf_with_markdown_returns_markdown_and_chunks(tmp_path: Path) -> None:
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    parser = FakeParser("# Intro\nNoi dung.")

    loaded = _load_pdf_with_markdown(pdf_path, parser, chunker=DeterministicMarkdownChunker())

    assert loaded.markdown == "# Intro\nNoi dung."
    assert len(loaded.chunks) == 1
    assert loaded.chunks[0].text == "Noi dung."
    assert parser.seen_path == pdf_path


def test_load_pdf_chunks_returns_empty_list_for_empty_markdown(tmp_path: Path) -> None:
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    assert (
        _load_pdf_chunks(pdf_path, FakeParser(" \n\n"), chunker=DeterministicMarkdownChunker())
        == []
    )


def test_load_pdf_with_markdown_accepts_resolved_pipeline_strategy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        "agentic_rag.ingestion.pdf.loader.resolve_pdf_pipeline",
        lambda pipeline_name, strategy_name: type(
            "Resolved",
            (),
            {
                "pipeline_name": pipeline_name,
                "strategy_name": strategy_name,
                "parser": FakeParser("# Intro\nNoi dung."),
            },
        )(),
    )

    loaded = load_pdf_with_markdown(
        str(pdf_path),
        pipeline_name="ocr",
        strategy_name="docling",
        chunker_name="deterministic",
    )

    assert loaded.parser == "fake-parser"
    assert loaded.pipeline == "ocr"
    assert loaded.strategy == "docling"
    assert loaded.chunker == "deterministic"
    assert loaded.chunks[0].text == "Noi dung."


def test_load_pdf_with_markdown_keeps_legacy_parser_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    seen: dict[str, str | None] = {}

    def fake_resolve_pdf_pipeline(
        pipeline_name: str | None,
        strategy_name: str | None,
    ) -> object:
        seen["pipeline_name"] = pipeline_name
        seen["strategy_name"] = strategy_name
        return type(
            "Resolved",
            (),
            {
                "pipeline_name": "ocr",
                "strategy_name": "docling",
                "parser": FakeParser("# Intro\nNoi dung."),
            },
        )()

    monkeypatch.setattr(
        "agentic_rag.ingestion.pdf.loader.resolve_pdf_pipeline",
        fake_resolve_pdf_pipeline,
    )

    loaded = load_pdf_with_markdown(
        str(pdf_path),
        parser_name="docling",
        chunker_name="deterministic",
    )

    assert seen == {"pipeline_name": None, "strategy_name": "docling"}
    assert loaded.pipeline == "ocr"
    assert loaded.strategy == "docling"


def test_load_pdf_chunks_does_not_write_debug_files_next_to_input(tmp_path: Path) -> None:
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    chunks = _load_pdf_chunks(
        pdf_path,
        FakeParser("# Intro\nNoi dung."),
        chunker=DeterministicMarkdownChunker(),
    )

    assert len(chunks) == 1
    assert sorted(path.name for path in tmp_path.iterdir()) == ["source.pdf"]


def test_load_pdf_chunks_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"missing\.pdf"):
        load_pdf_chunks(str(tmp_path / "missing.pdf"))


def test_load_pdf_chunks_rejects_non_pdf_file(tmp_path: Path) -> None:
    text_path = tmp_path / "notes.txt"
    text_path.write_text("not a pdf", encoding="utf-8")

    with pytest.raises(ValueError, match="PDF"):
        load_pdf_chunks(str(text_path))

    with pytest.raises(ValueError, match="PDF"):
        load_pdf_with_markdown(str(text_path))
