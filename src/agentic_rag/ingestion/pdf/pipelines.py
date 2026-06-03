"""PDF parser pipeline registry for OCR and VLM strategies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from agentic_rag.ingestion.pdf.models import PdfPipelineCapabilities, PdfPipelineName
from agentic_rag.ingestion.pdf.parser import DoclingMarkdownParser, PdfMarkdownParser

DEFAULT_PDF_PIPELINE: PdfPipelineName = "ocr"
DEFAULT_PDF_STRATEGY = "docling"


class ResolvedPdfParserPipeline(BaseModel):
    """Concrete parser pipeline selected for one ingestion run."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    pipeline_name: PdfPipelineName
    strategy_name: str
    parser: Any
    capabilities: PdfPipelineCapabilities


class PdfParserPipelineDefinition(BaseModel):
    """Registered parser strategy inside one pipeline family."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    pipeline_name: PdfPipelineName
    strategy_name: str
    factory: Callable[[], PdfMarkdownParser]
    capabilities: PdfPipelineCapabilities


_PIPELINE_REGISTRY: dict[PdfPipelineName, dict[str, PdfParserPipelineDefinition]] = {
    "ocr": {
        "docling": PdfParserPipelineDefinition(
            pipeline_name="ocr",
            strategy_name="docling",
            factory=DoclingMarkdownParser,
            capabilities=PdfPipelineCapabilities(
                pipeline="ocr",
                strategy="docling",
                supports_markdown=True,
                supports_assets=True,
                supports_page_metadata=False,
                supports_tables=True,
                supports_images=True,
                requires_network=False,
                requires_credentials=False,
            ),
        )
    },
    "vlm": {
        "mineru": PdfParserPipelineDefinition(
            pipeline_name="vlm",
            strategy_name="mineru",
            factory=lambda: _missing_mineru_parser(),
            capabilities=PdfPipelineCapabilities(
                pipeline="vlm",
                strategy="mineru",
                supports_markdown=True,
                supports_assets=True,
                supports_page_metadata=True,
                supports_tables=True,
                supports_images=True,
                requires_network=False,
                requires_credentials=False,
            ),
        )
    },
}


def resolve_pdf_pipeline(
    pipeline_name: str | None = None,
    strategy_name: str | None = None,
) -> ResolvedPdfParserPipeline:
    """Resolve a parser pipeline and strategy to a fresh parser adapter."""

    definition = _pipeline_definition(pipeline_name, strategy_name)
    return ResolvedPdfParserPipeline(
        pipeline_name=definition.pipeline_name,
        strategy_name=definition.strategy_name,
        parser=definition.factory(),
        capabilities=definition.capabilities,
    )


def supported_pdf_pipelines() -> tuple[str, ...]:
    """Return supported parser pipeline names."""

    return tuple(sorted(_PIPELINE_REGISTRY))


def supported_pdf_strategies(pipeline_name: str | None = None) -> tuple[str, ...]:
    """Return supported strategy names for one parser pipeline."""

    normalized_pipeline = _normalize_pipeline_name(pipeline_name)
    strategies = _PIPELINE_REGISTRY.get(normalized_pipeline)
    if strategies is None:
        raise ValueError(
            "Unsupported PDF parser pipeline: "
            f"{pipeline_name}. Supported pipelines: {', '.join(supported_pdf_pipelines())}."
        )
    return tuple(sorted(strategies))


def pipeline_capabilities(
    pipeline_name: str | None = None,
    strategy_name: str | None = None,
) -> PdfPipelineCapabilities:
    """Return capability metadata for one registered parser pipeline strategy."""

    return _pipeline_definition(pipeline_name, strategy_name).capabilities


def _pipeline_definition(
    pipeline_name: str | None,
    strategy_name: str | None,
) -> PdfParserPipelineDefinition:
    normalized_pipeline = _normalize_pipeline_name(pipeline_name)
    strategies = _PIPELINE_REGISTRY.get(normalized_pipeline)
    if strategies is None:
        raise ValueError(
            "Unsupported PDF parser pipeline: "
            f"{pipeline_name}. Supported pipelines: {', '.join(supported_pdf_pipelines())}."
        )

    normalized_strategy = _normalize_strategy_name(strategy_name)
    definition = strategies.get(normalized_strategy)
    if definition is None:
        raise ValueError(
            "Unsupported PDF parser strategy: "
            f"{strategy_name}. Supported strategies for {normalized_pipeline}: "
            f"{', '.join(supported_pdf_strategies(normalized_pipeline))}."
        )
    return definition


def _normalize_pipeline_name(pipeline_name: str | None) -> PdfPipelineName:
    if pipeline_name is None:
        return DEFAULT_PDF_PIPELINE
    return pipeline_name.strip().lower().replace("_", "-")  # type: ignore[return-value]


def _normalize_strategy_name(strategy_name: str | None) -> str:
    if strategy_name is None:
        return DEFAULT_PDF_STRATEGY
    return strategy_name.strip().lower().replace("_", "-")


def _missing_mineru_parser() -> PdfMarkdownParser:
    raise RuntimeError(
        "PDF parser strategy 'vlm/mineru' is registered but not installed or configured. "
        "Install and wire MinerU in a dedicated integration step before selecting it."
    )
