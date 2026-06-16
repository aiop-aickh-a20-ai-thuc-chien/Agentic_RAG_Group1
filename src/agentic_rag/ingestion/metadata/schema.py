from __future__ import annotations

from typing import TypedDict


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
    source: str
    source_type: str
    url: str | None
    file_name: str | None

    # Document [P]
    title: str | None
    document_type: str
    product_model: list[str]
    language: str

    # Structural [P]
    page_number: int | None
    section: str | None
    section_level: int | None
    section_path: list[str]
    heading: str | None
    breadcrumb: list[str]

    # Temporal
    created_date: str | None  # [P]
    updated_date: str | None  # [P]
    ingested_at: str  # [S]
    ingestion_at: str  # [S]

    # Semantic [L]
    content_hash: str
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

SOURCE_TYPE_VALUES = frozenset(
    {
        "official",
        "internal",
        "partner",
        "news",
        "community",
        "unknown",
    }
)

DOCUMENT_TYPE_VALUES = frozenset(
    {
        "manual",
        "faq",
        "spec_sheet",
        "policy",
        "article",
        "unknown",
    }
)

LANGUAGE_VALUES = frozenset({"vi", "en", "unknown"})
