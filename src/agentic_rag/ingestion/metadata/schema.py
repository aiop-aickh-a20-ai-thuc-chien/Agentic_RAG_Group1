from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field


class ChunkMetadata(BaseModel):
    """
    Flat metadata schema for a single chunk.

    Extraction stages:
    [P] = Parser / rule-based (before chunking)
    [L] = LLM-based (after chunking)
    [S] = Storage layer (stamped at write time)

    Qdrant indexes:
    [IDX] = payload index created for fast filtering
    """

    model_config = ConfigDict(frozen=False, extra="allow")

    # Identity [P]
    chunk_id: str | None = None
    document_id: str | None = None
    chunk_index: int | None = None
    token_count: int | None = None

    # Source [P]
    source: str | None = None
    source_type: str | None = None
    url: str | None = None
    file_name: str | None = None

    # Document [P] (document_type & language are refined by LLM Extract [L])
    title: str | None = None
    document_type: str | None = None
    product_model: list[str] = Field(default_factory=list)
    language: str | None = None

    # Structural [P]
    page_number: int | None = None
    section: str | None = None
    section_level: int | None = None
    section_path: list[str] = Field(default_factory=list)
    heading: str | None = None
    breadcrumb: list[str] = Field(default_factory=list)

    # Temporal
    created_date: str | None = None  # [P]
    created_date_source: str | None = None  # [P]
    updated_date: str | None = None  # [P]
    updated_date_source: str | None = None  # [P]
    ingested_at: str | None = None  # [S]
    ingestion_at: str | None = None  # [S]

    # Derived [P] (deterministic hash, not LLM)
    content_hash: str | None = None
    dedupe_hash: str | None = None

    # Semantic [L] - produced by the LLM Extract stage; see
    # LLMExtractedMetadata in agentic_rag.ingestion.metadata.extract.
    summary: str | None = None
    topic_tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    entities_canonical: list[str] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    quality_score: float | None = None

    def __getitem__(self, key: str) -> Any:
        if key in type(self).model_fields:
            return getattr(self, key)
        if self.__pydantic_extra__ and key in self.__pydantic_extra__:
            return self.__pydantic_extra__[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key in type(self).model_fields:
            setattr(self, key, value)
        else:
            extra = self.__pydantic_extra__
            if extra is None:
                extra = {}
                object.__setattr__(self, "__pydantic_extra__", extra)
            extra[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        return (key in type(self).model_fields) or bool(
            self.__pydantic_extra__ and key in self.__pydantic_extra__
        )

    def keys(self) -> Iterator[str]:
        fields = set(type(self).model_fields.keys())
        if self.__pydantic_extra__:
            fields.update(self.__pydantic_extra__.keys())
        return iter(fields)

    def items(self) -> Iterator[tuple[str, Any]]:
        for key in self.keys():
            yield key, self[key]

    def values(self) -> Iterator[Any]:
        for key in self.keys():
            yield self[key]

    def update(self, other: Mapping[str, Any]) -> None:
        for key, value in other.items():
            self[key] = value


QDRANT_INDEX_FIELDS: tuple[str, ...] = (
    "document_id",
    "source_type",
    "document_type",
    "product_model",
    "language",
    "metadata.entities_canonical",
    "metadata.metadata_prefilter_exclude",
    "metadata.deduplication.primary_layer",
)

REQUIRED_METADATA_FIELDS: tuple[str, ...] = ("source_type", "updated_date")

# TODO [metadata/schema – source_type semantics]:
# `source_type` describes *content provenance* (who published it), not *ingestion
# modality* (how it arrived). The values "pdf", "url", and "text" were added
# experimentally but do not represent provenance categories and may mislead
# retrieval filters. If you need to track ingestion modality separately, add a
# distinct field (e.g. `ingestion_modality: Literal["pdf", "url", "text"]`) to
# `ChunkMetadata` and remove pdf/url/text from this set.
# Reference: src/agentic_rag/ingestion/metadata/schema.py (SOURCE_TYPE_VALUES)
#
# TODO [GraphRAG – source_type → graph node label]:
# When building a knowledge graph from ingested chunks, each `source_type` value
# should be mapped to a named graph node label so that retrieval can traverse
# provenance edges (e.g. Chunk → SourceNode[official] → DomainNode[vinfastauto.com]).
# Design the mapping here before the graph layer is introduced so that the
# node label vocabulary is stable from ingestion day 1.
# Reference: GraphRAG integration plan (to be created)
SOURCE_TYPE_VALUES = frozenset(
    {
        "community",
        "internal",
        "news",
        "official",
        "partner",
        "unknown",
        "pdf",
        "url",
        "text",
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
