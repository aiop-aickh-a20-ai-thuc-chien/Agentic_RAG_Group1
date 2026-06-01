from pathlib import Path

import pytest

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.pdf.loader import _load_pdf_chunks, load_pdf_chunks


class FakeParser:
    def __init__(self, markdown: str) -> None:
        self.markdown = markdown
        self.seen_path: Path | None = None

    def parse_to_markdown(self, path: Path) -> str:
        self.seen_path = path
        return self.markdown


def test_load_pdf_chunks_maps_markdown_to_shared_chunks(tmp_path: Path) -> None:
    pdf_path = tmp_path / "VinFast Warranty.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    parser = FakeParser("# Warranty\nPin duoc bao hanh 8 nam.\n\n## Battery\nDieu kien ap dung.")

    chunks = _load_pdf_chunks(pdf_path, parser)

    assert all(isinstance(chunk, Chunk) for chunk in chunks)
    assert [chunk.chunk_id for chunk in chunks] == [
        "pdf_vinfast_warranty_c0001",
        "pdf_vinfast_warranty_c0002",
    ]
    assert chunks[0].text == "Pin duoc bao hanh 8 nam."
    assert chunks[0].metadata == {
        "source": str(pdf_path),
        "source_type": "pdf",
        "file_name": "VinFast Warranty.pdf",
        "page": None,
        "section": "Warranty",
        "parser": "docling",
        "chunk_index": 1,
    }
    assert chunks[1].metadata["section"] == "Battery"
    assert parser.seen_path == pdf_path


def test_load_pdf_chunks_returns_empty_list_for_empty_markdown(tmp_path: Path) -> None:
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    assert _load_pdf_chunks(pdf_path, FakeParser(" \n\n")) == []


def test_load_pdf_chunks_does_not_write_debug_files_next_to_input(tmp_path: Path) -> None:
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    chunks = _load_pdf_chunks(pdf_path, FakeParser("# Intro\nNoi dung."))

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
