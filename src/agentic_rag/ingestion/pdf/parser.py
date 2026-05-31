"""PDF parser adapters for ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, cast

from pydantic import BaseModel, ConfigDict

DocumentConverter: Any | None = None


class ParsedPdfDocument(BaseModel):
    """Markdown plus the parser-native document object for artifact extraction."""

    model_config = ConfigDict(frozen=True)

    markdown: str
    document: Any


class PdfMarkdownParser(Protocol):
    """Parser interface that hides concrete PDF parser dependencies."""

    def parse_to_markdown(self, path: Path) -> str:
        """Convert a local PDF file into Markdown text."""


class PdfDocumentParser(Protocol):
    """Parser interface for callers that need parser-native document structure."""

    def parse_to_document(self, path: Path) -> ParsedPdfDocument:
        """Convert a local PDF file into Markdown and a parser-native document."""


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

    def parse_to_document(self, path: Path) -> ParsedPdfDocument:
        """Convert a PDF file into Markdown and a Docling document."""

        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import PdfFormatOption

            converter_class = _get_document_converter()
            converter = converter_class(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=PdfPipelineOptions(
                            generate_page_images=True,
                            generate_picture_images=True,
                        )
                    )
                }
            )
            result = converter.convert(path)
            markdown = cast(str, result.document.export_to_markdown())
            return ParsedPdfDocument(markdown=markdown, document=result.document)
        except Exception as exc:
            raise RuntimeError(f"Failed to parse PDF with Docling: {path}") from exc


def _get_document_converter() -> Any:
    global DocumentConverter
    if DocumentConverter is None:
        from docling.document_converter import DocumentConverter as docling_document_converter

        DocumentConverter = docling_document_converter
    return DocumentConverter
