"""Entity extraction helpers for URL semantic blocks."""

from agentic_rag.ingestion.url.entities.extractor import (
    UrlEntity,
    entities_summary,
    extract_entities,
    extract_product_specs,
)

__all__ = ["UrlEntity", "entities_summary", "extract_entities", "extract_product_specs"]
