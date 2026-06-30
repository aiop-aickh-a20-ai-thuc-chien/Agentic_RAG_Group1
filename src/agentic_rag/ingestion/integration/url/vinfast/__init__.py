"""VinFast-specific resilient extraction and RAG preparation helpers."""

from agentic_rag.ingestion.integration.url.vinfast.adapter import PlaywrightSessionAdapter
from agentic_rag.ingestion.integration.url.vinfast.chunking import product_chunks
from agentic_rag.ingestion.integration.url.vinfast.models import (
    ProductType,
    VinFastProduct,
)
from agentic_rag.ingestion.integration.url.vinfast.pipeline import (
    ExtractionStage,
    VinFastExtractionPipeline,
    retry_async,
)
from agentic_rag.ingestion.integration.url.vinfast.storage import (
    ChangeStore,
    FailedUrlLog,
    content_hash,
    upsert_changed_chunks,
)
from agentic_rag.ingestion.integration.url.vinfast.structured import (
    extract_screenshot_with_instructor,
    parse_text_with_instructor,
)

__all__ = [
    "ChangeStore",
    "ExtractionStage",
    "FailedUrlLog",
    "PlaywrightSessionAdapter",
    "ProductType",
    "VinFastExtractionPipeline",
    "VinFastProduct",
    "content_hash",
    "extract_screenshot_with_instructor",
    "parse_text_with_instructor",
    "product_chunks",
    "retry_async",
    "upsert_changed_chunks",
]
