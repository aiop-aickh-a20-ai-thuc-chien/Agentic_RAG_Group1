from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NotRequired, Required, TypedDict
from urllib.parse import urlparse


class ChunkMetadata(TypedDict, total=False):
    """
    Flat metadata schema for a single chunk.

    Extraction stages:
    [P] = Parser / rule-based (before chunking)
    [L] = LLM-based (after chunking)
    [S] = Storage layer (stamped at write time)

    Qdrant indexes:
    [IDX] = payload index created for fast filtering
    """

    # Identity [P]
    chunk_id: str
    document_id: str
    chunk_index: int
    token_count: int

    # Source [P]
    source_type: Required[str]
    source: NotRequired[str]
    url: NotRequired[str | None]
    file_name: NotRequired[str | None]

    # Document [P]
    document_type: NotRequired[str | None]
    product_model: NotRequired[list[str] | str | None]
    language: NotRequired[str | None]

    # Structural [P]
    page_number: int | None
    section: str | None
    heading: str | None
    breadcrumb: list[str]

    # Temporal
    created_date: NotRequired[str | None]  # [P]
    created_date_source: NotRequired[str | None]  # [P]
    updated_date: Required[str]  # [P]
    updated_date_source: NotRequired[str | None]  # [P]
    ingested_at: str  # [S]

    # Semantic [L]
    summary: str | None
    topic_tags: list[str]
    keywords: list[str]
    entities: list[str]
    quality_score: float | None


QDRANT_INDEX_FIELDS: tuple[str, ...] = (
    "document_id",
    "source_type",
    "document_type",
    "product_model",
    "language",
    "topic_tags",
    "metadata.deduplication.primary_layer",
)

REQUIRED_METADATA_FIELDS: tuple[str, ...] = ("source_type", "updated_date")

SOURCE_TYPE_VALUES = frozenset(
    {
        "community",
        "internal",
        "news",
        "official",
        "partner",
        "unknown",
    }
)

SOURCE_CATEGORY_VALUES = SOURCE_TYPE_VALUES

DOCUMENT_TYPE_VALUES = frozenset(
    {
        "article",
        "booking_flow",
        "comparison_table_page",
        "dynamic_application",
        "faq",
        "faq_page",
        "generic",
        "homepage_product_listing",
        "interactive_application",
        "manual",
        "policy",
        "policy_page",
        "product_detail",
        "product_listing",
        "product_page",
        "spec_sheet",
        "unknown",
        "vehicle_configurator",
        "vehicle_or_product_page",
    }
)

LANGUAGE_VALUES = frozenset({"vi", "en", "unknown"})

OFFICIAL_SOURCE_DOMAINS = frozenset(
    {
        "shop.vinfastauto.com",
        "vinfastauto.com",
        "vinfast.vn",
        "www.vinfastauto.com",
        "www.vinfast.vn",
    }
)

NEWS_SOURCE_MARKERS = frozenset({"news", "tin-tuc", "blog"})


def infer_source_type(source: str | None) -> str:
    """Infer shared source category from a URL/path without guessing too much."""

    if not source:
        return "unknown"
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        domain = parsed.netloc.casefold()
        if domain in OFFICIAL_SOURCE_DOMAINS:
            return "official"
        source_text = f"{domain}/{parsed.path}".casefold()
        if any(marker in source_text for marker in NEWS_SOURCE_MARKERS):
            return "news"
        return "unknown"
    return "internal"


def missing_required_metadata(metadata: Mapping[str, Any]) -> tuple[str, ...]:
    """Return required shared metadata keys that are absent or blank."""

    missing: list[str] = []
    for field in REQUIRED_METADATA_FIELDS:
        value = metadata.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return tuple(missing)


def has_required_metadata(metadata: Mapping[str, Any]) -> bool:
    """Return whether metadata satisfies the shared ingestion minimum."""

    return not missing_required_metadata(metadata)


def require_metadata(metadata: Mapping[str, Any]) -> None:
    """Raise when metadata does not satisfy the shared ingestion minimum."""

    missing = missing_required_metadata(metadata)
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Chunk metadata missing required field(s): {joined}")
