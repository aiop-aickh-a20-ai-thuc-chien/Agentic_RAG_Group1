"""Shared stack-neutral data contracts for all implementation modules."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AnswerStatus = Literal["answered", "not_found"]
RetrieverName = Literal["bm25", "dense", "hybrid", "rerank"]


class _ContractModel(BaseModel):
    """Base configuration for shared contract models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Chunk(_ContractModel):
    """A normalized document segment produced by ingestion modules."""

    chunk_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResult(_ContractModel):
    """A ranked retrieval result passed between retrieval, fusion, and generation."""

    chunk: Chunk
    score: float
    rank: int
    retriever: RetrieverName | str


class Citation(_ContractModel):
    """A source reference derived from retrieved evidence metadata."""

    source: str
    chunk_id: str
    page: int | None = None
    section: str | None = None
    url: str | None = None


class Answer(_ContractModel):
    """A grounded generation result returned to UI or evaluation layers."""

    answer: str
    status: AnswerStatus
    citations: list[Citation] = Field(default_factory=list)
