import pytest
from pydantic import ValidationError

from agentic_rag.ingestion.pdf.models import (
    PdfAssetRef,
    PdfChunkingInput,
    PdfParserCapabilities,
    PdfParseResult,
)


def test_parse_result_keeps_markdown_assets_warnings_and_metadata() -> None:
    asset = PdfAssetRef(
        asset_id="pdf_doc_table_0001",
        kind="table",
        path="artifacts/doc/run/assets/tables/pdf_doc_table_0001.md",
        page=2,
        text="| A | B |",
        metadata={"source_ref": "#/tables/1"},
    )

    result = PdfParseResult(
        parser="docling",
        source_path="source.pdf",
        markdown="# Title\nContent",
        assets=[asset],
        warnings=["table image unavailable"],
        metadata={"elapsed_ms": 123},
    )

    assert result.parser == "docling"
    assert result.assets == [asset]
    assert result.warnings == ["table image unavailable"]
    assert result.metadata["elapsed_ms"] == 123


def test_parse_result_rejects_extra_top_level_fields() -> None:
    with pytest.raises(ValidationError):
        PdfParseResult.model_validate(
            {
                "parser": "docling",
                "source_path": "source.pdf",
                "markdown": "# Title\nContent",
                "unexpected": True,
            }
        )


def test_parser_capabilities_describe_optional_outputs() -> None:
    capabilities = PdfParserCapabilities(
        supports_markdown=True,
        supports_assets=True,
        supports_page_metadata=False,
        supports_tables=True,
        supports_images=True,
    )

    assert capabilities.supports_markdown is True
    assert capabilities.supports_assets is True
    assert capabilities.supports_page_metadata is False
    assert capabilities.supports_tables is True
    assert capabilities.supports_images is True


def test_pdf_chunking_input_can_carry_native_parser_document() -> None:
    native_document = object()

    chunking_input = PdfChunkingInput(
        markdown="# Warranty\nContent",
        parser="docling",
        source_path="source.pdf",
        native_document=native_document,
    )

    assert chunking_input.markdown == "# Warranty\nContent"
    assert chunking_input.parser == "docling"
    assert chunking_input.source_path == "source.pdf"
    assert chunking_input.native_document is native_document
