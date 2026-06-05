"""PDF ingestion package."""

from .artifacts import (
    PdfElementArtifact,
    PdfIngestionArtifactManifest,
    PdfMultimodalArtifactManifest,
    save_loaded_pdf_ingestion_artifacts,
    save_pdf_ingestion_artifacts,
    save_pdf_multimodal_artifacts,
)
from .chunkers import (
    DeterministicMarkdownChunker,
    DoclingHybridChunker,
    DoclingPageAwareChunker,
    MarkdownChunker,
    resolve_markdown_chunker,
    supported_markdown_chunkers,
)
from .config import PdfIngestionConfig
from .loader import (
    LoadedPdfDocument,
    load_pdf_chunks,
    load_pdf_with_markdown,
)
from .models import (
    PdfAssetRef,
    PdfChunkingInput,
    PdfParserCapabilities,
    PdfParseResult,
    PdfPipelineCapabilities,
)
from .pipelines import (
    DEFAULT_PDF_PIPELINE,
    DEFAULT_PDF_STRATEGY,
    PdfParserPipelineDefinition,
    ResolvedPdfParserPipeline,
    pipeline_capabilities,
    resolve_pdf_pipeline,
    supported_pdf_pipelines,
    supported_pdf_strategies,
)
from .registry import (
    parser_capabilities,
    resolve_pdf_parser,
    supported_pdf_parsers,
)

__all__ = [
    "DEFAULT_PDF_PIPELINE",
    "DEFAULT_PDF_STRATEGY",
    "DeterministicMarkdownChunker",
    "DoclingHybridChunker",
    "DoclingPageAwareChunker",
    "LoadedPdfDocument",
    "MarkdownChunker",
    "PdfAssetRef",
    "PdfChunkingInput",
    "PdfElementArtifact",
    "PdfIngestionArtifactManifest",
    "PdfIngestionConfig",
    "PdfMultimodalArtifactManifest",
    "PdfParseResult",
    "PdfParserCapabilities",
    "PdfParserPipelineDefinition",
    "PdfPipelineCapabilities",
    "ResolvedPdfParserPipeline",
    "load_pdf_chunks",
    "load_pdf_with_markdown",
    "parser_capabilities",
    "pipeline_capabilities",
    "resolve_markdown_chunker",
    "resolve_pdf_parser",
    "resolve_pdf_pipeline",
    "save_loaded_pdf_ingestion_artifacts",
    "save_pdf_ingestion_artifacts",
    "save_pdf_multimodal_artifacts",
    "supported_markdown_chunkers",
    "supported_pdf_parsers",
    "supported_pdf_pipelines",
    "supported_pdf_strategies",
]
