from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

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

    # Document [P]
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
    updated_date: str | None = None  # [P]
    ingested_at: str | None = None  # [S]
    ingestion_at: str | None = None  # [S]

    # Semantic [L]
    content_hash: str | None = None
    summary: str | None = None
    topic_tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    quality_score: float | None = None

    def __getitem__(self, key: str) -> Any:
        if key in self.model_fields:
            return getattr(self, key)
        if self.__pydantic_extra__ and key in self.__pydantic_extra__:
            return self.__pydantic_extra__[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self.model_fields:
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
        return (key in self.model_fields) or bool(
            self.__pydantic_extra__ and key in self.__pydantic_extra__
        )

    def keys(self) -> Iterator[str]:
        fields = set(self.model_fields.keys())
        if self.__pydantic_extra__:
            fields.update(self.__pydantic_extra__.keys())
        return iter(fields)

    def items(self) -> Iterator[tuple[str, Any]]:
        for k in self.keys():
            yield k, self[k]

    def values(self) -> Iterator[Any]:
        for k in self.keys():
            yield self[k]

    def update(self, other: Mapping[str, Any]) -> None:
        for k, v in other.items():
            self[k] = v


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
