"""PDF ingestion and chunking boundary."""

from __future__ import annotations

import re
from pathlib import Path

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.pdf.chunking import chunk_markdown
from agentic_rag.ingestion.pdf.parser import DoclingMarkdownParser, PdfMarkdownParser


def load_pdf_chunks(path: str) -> list[Chunk]:
    """Load and chunk a PDF file into shared Chunk objects."""

    pdf_path = Path(path)
    return _load_pdf_chunks(pdf_path, DoclingMarkdownParser())


def _load_pdf_chunks(path: Path, parser: PdfMarkdownParser) -> list[Chunk]:
    _validate_pdf_path(path)
    markdown = parser.parse_to_markdown(path)
    return _chunks_from_markdown(path, markdown)


def _validate_pdf_path(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"PDF file does not exist: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file path, got: {path}")


def _chunks_from_markdown(path: Path, markdown: str) -> list[Chunk]:
    markdown_chunks = chunk_markdown(markdown)
    safe_file_stem = _safe_chunk_id_part(path.stem)

    chunks: list[Chunk] = []
    for index, markdown_chunk in enumerate(markdown_chunks, start=1):
        chunks.append(
            Chunk(
                chunk_id=f"pdf_{safe_file_stem}_c{index:04d}",
                text=markdown_chunk.text,
                metadata={
                    "source": str(path),
                    "source_type": "pdf",
                    "file_name": path.name,
                    "page": None,
                    "section": markdown_chunk.section,
                    "parser": "docling",
                    "chunk_index": index,
                },
            )
        )
    return chunks


def _safe_chunk_id_part(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "document"
