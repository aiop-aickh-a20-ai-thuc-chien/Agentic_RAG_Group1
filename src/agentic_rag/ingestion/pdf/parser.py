"""PDF parser adapters for ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, cast

DocumentConverter: Any | None = None


class PdfMarkdownParser(Protocol):
    """Parser interface that hides concrete PDF parser dependencies."""

    def parse_to_markdown(self, path: Path) -> str:
        """Convert a local PDF file into Markdown text."""


class DoclingMarkdownParser:
    """Docling-backed baseline parser for local PDF files."""

    def parse_to_markdown(self, path: Path) -> str:
        """Convert a PDF file into Markdown using Docling."""

        try:
            converter_class = _get_document_converter()
            result = converter_class().convert(path)
            return cast(str, result.document.export_to_markdown())
        except Exception as exc:
            raise RuntimeError(f"Failed to parse PDF with Docling: {path}") from exc


def _get_document_converter() -> Any:
    global DocumentConverter
    if DocumentConverter is None:
        from docling.document_converter import DocumentConverter as docling_document_converter

        DocumentConverter = docling_document_converter
    return DocumentConverter
