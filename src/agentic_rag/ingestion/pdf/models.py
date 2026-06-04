"""PDF-local parser result models.

These models intentionally stay inside the PDF ingestion package. They describe
parser output before it is mapped into the shared RAG contracts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.ingestion.chunking import ChunkingInput

PdfAssetKind = Literal["image", "table", "chart", "other"]
PdfPipelineName = Literal["ocr", "vlm"]


class _PdfParserModel(BaseModel):
    """Base configuration for PDF-local parser models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PdfAssetRef(_PdfParserModel):
    """File-backed parser asset reference for later post-processing."""

    asset_id: str
    kind: PdfAssetKind
    path: str
    page: int | None = None
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PdfParseResult(_PdfParserModel):
    """Normalized output from one PDF Markdown parser adapter."""

    parser: str
    source_path: str
    markdown: str
    assets: list[PdfAssetRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PdfChunkingInput(ChunkingInput):
    """Input passed from PDF parser output into a PDF-local chunker."""

    markdown: str
    parser: str
    source_path: str
    source_type: str | None = "pdf"
    native_document: Any | None = None


class PdfParserCapabilities(_PdfParserModel):
    """Feature flags that make parser comparison explicit."""

    supports_markdown: bool = True
    supports_assets: bool = False
    supports_page_metadata: bool = False
    supports_tables: bool = False
    supports_images: bool = False


class PdfPipelineCapabilities(_PdfParserModel):
    """Feature flags for one parser pipeline strategy."""

    pipeline: PdfPipelineName
    strategy: str
    supports_markdown: bool = True
    supports_assets: bool = False
    supports_page_metadata: bool = False
    supports_tables: bool = False
    supports_images: bool = False
    requires_network: bool = False
    requires_credentials: bool = False
