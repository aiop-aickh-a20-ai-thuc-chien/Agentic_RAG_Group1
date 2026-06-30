"""Built-in and injectable URL integration adapters."""

from agentic_rag.ingestion.integration.url.adapters.base import (
    AcquisitionAdapter,
    ExtractionAdapter,
)
from agentic_rag.ingestion.integration.url.adapters.crawlee import (
    acquire_supplied_html,
    acquire_with_crawlee,
)
from agentic_rag.ingestion.integration.url.adapters.docling import extract_with_docling
from agentic_rag.ingestion.integration.url.adapters.dom import extract_dom
from agentic_rag.ingestion.integration.url.adapters.playwright import extract_interactions
from agentic_rag.ingestion.integration.url.adapters.vlm import (
    VlmRegionAdapter,
    configured_ingestion_vlm_client,
)

__all__ = [
    "AcquisitionAdapter",
    "ExtractionAdapter",
    "VlmRegionAdapter",
    "acquire_supplied_html",
    "acquire_with_crawlee",
    "configured_ingestion_vlm_client",
    "extract_dom",
    "extract_interactions",
    "extract_with_docling",
]
