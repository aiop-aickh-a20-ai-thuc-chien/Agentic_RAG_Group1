import pytest
from pydantic import BaseModel

from agentic_rag.ingestion.pdf.parser import DoclingMarkdownParser
from agentic_rag.ingestion.pdf.registry import (
    PdfParserDefinition,
    parser_capabilities,
    resolve_pdf_parser,
    supported_pdf_parsers,
)


def test_resolve_pdf_parser_returns_docling_by_default() -> None:
    resolved = resolve_pdf_parser(None)

    assert isinstance(resolved, DoclingMarkdownParser)
    assert resolved.parser_name == "docling"


def test_supported_pdf_parsers_lists_registered_names() -> None:
    assert supported_pdf_parsers() == ("docling",)


def test_pdf_parser_definition_is_pydantic_model() -> None:
    assert issubclass(PdfParserDefinition, BaseModel)


def test_parser_capabilities_describe_docling_outputs() -> None:
    capabilities = parser_capabilities("docling")

    assert capabilities.supports_markdown is True
    assert capabilities.supports_assets is True
    assert capabilities.supports_tables is True
    assert capabilities.supports_images is True


def test_resolve_pdf_parser_rejects_unknown_parser() -> None:
    with pytest.raises(ValueError, match="Unsupported PDF parser"):
        resolve_pdf_parser("unknown")
