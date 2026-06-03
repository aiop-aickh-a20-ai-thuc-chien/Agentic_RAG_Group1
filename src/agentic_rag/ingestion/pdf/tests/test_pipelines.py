import pytest
from pydantic import BaseModel

from agentic_rag.ingestion.pdf.parser import DoclingMarkdownParser
from agentic_rag.ingestion.pdf.pipelines import (
    PdfParserPipelineDefinition,
    pipeline_capabilities,
    resolve_pdf_pipeline,
    supported_pdf_pipelines,
    supported_pdf_strategies,
)


def test_resolve_pdf_pipeline_defaults_to_ocr_docling() -> None:
    resolved = resolve_pdf_pipeline(None, None)

    assert resolved.pipeline_name == "ocr"
    assert resolved.strategy_name == "docling"
    assert isinstance(resolved.parser, DoclingMarkdownParser)


def test_supported_pdf_pipelines_and_strategies_are_stable() -> None:
    assert supported_pdf_pipelines() == ("ocr", "vlm")
    assert supported_pdf_strategies("ocr") == ("docling",)
    assert supported_pdf_strategies("vlm") == ("mineru",)


def test_pipeline_definition_is_pydantic_model() -> None:
    assert issubclass(PdfParserPipelineDefinition, BaseModel)


def test_pipeline_capabilities_describe_docling_strategy() -> None:
    capabilities = pipeline_capabilities("ocr", "docling")

    assert capabilities.pipeline == "ocr"
    assert capabilities.strategy == "docling"
    assert capabilities.supports_markdown is True
    assert capabilities.supports_assets is True
    assert capabilities.requires_network is False


def test_pipeline_capabilities_do_not_instantiate_unavailable_strategy() -> None:
    capabilities = pipeline_capabilities("vlm", "mineru")

    assert capabilities.pipeline == "vlm"
    assert capabilities.strategy == "mineru"
    assert capabilities.supports_page_metadata is True


def test_resolve_pdf_pipeline_rejects_unknown_pipeline() -> None:
    with pytest.raises(ValueError, match="Unsupported PDF parser pipeline"):
        resolve_pdf_pipeline("unknown", "docling")


def test_resolve_pdf_pipeline_rejects_unknown_strategy() -> None:
    with pytest.raises(ValueError, match="Unsupported PDF parser strategy"):
        resolve_pdf_pipeline("ocr", "mineru")


def test_resolve_pdf_pipeline_mineru_seam_fails_clearly() -> None:
    with pytest.raises(RuntimeError, match="vlm/mineru"):
        resolve_pdf_pipeline("vlm", "mineru")
