"""PDF ingestion package."""

from agentic_rag.ingestion.pdf.artifacts import (
    PdfElementArtifact,
    PdfIngestionArtifactManifest,
    PdfMultimodalArtifactManifest,
    save_loaded_pdf_ingestion_artifacts,
    save_pdf_ingestion_artifacts,
    save_pdf_multimodal_artifacts,
)
from agentic_rag.ingestion.pdf.chunkers import (
    DeterministicMarkdownChunker,
    DoclingHybridChunker,
    DoclingPageAwareChunker,
    MarkdownChunker,
    resolve_markdown_chunker,
    supported_markdown_chunkers,
)
from agentic_rag.ingestion.pdf.config import PdfIngestionConfig
from agentic_rag.ingestion.pdf.loader import (
    LoadedPdfDocument,
    load_pdf_chunks,
    load_pdf_with_markdown,
)
from agentic_rag.ingestion.pdf.models import (
    PdfAssetRef,
    PdfChunkingInput,
    PdfParserCapabilities,
    PdfParseResult,
    PdfPipelineCapabilities,
)
from agentic_rag.ingestion.pdf.pipelines import (
    DEFAULT_PDF_PIPELINE,
    DEFAULT_PDF_STRATEGY,
    PdfParserPipelineDefinition,
    ResolvedPdfParserPipeline,
    pipeline_capabilities,
    resolve_pdf_pipeline,
    supported_pdf_pipelines,
    supported_pdf_strategies,
)
from agentic_rag.ingestion.pdf.registry import (
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
