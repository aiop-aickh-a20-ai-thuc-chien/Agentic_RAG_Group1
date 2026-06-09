"""Pydantic contracts returned by LangGraph agent nodes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import Answer, SearchResult


class _AgentNodeOutput(BaseModel):
    """Strict immutable base for partial AgentState updates."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PreprocessNodeOutput(_AgentNodeOutput):
    rewritten_question: str
    queries_tried: list[str]
    pending_queries: list[str] | None = None
    trace: list[dict[str, Any]]


class RetrieveNodeOutput(_AgentNodeOutput):
    fused_results: list[SearchResult]
    queries_tried: list[str]
    pending_queries: list[str]
    step_count: int
    retrieval_exhausted: bool
    trace: list[dict[str, Any]]


class RerankNodeOutput(_AgentNodeOutput):
    relevant_docs: list[SearchResult]
    pinned_docs: list[SearchResult]
    missing_entities: list[str]
    rejected_chunk_ids: list[str]
    trace: list[dict[str, Any]]


class TransformQueryNodeOutput(_AgentNodeOutput):
    queries_tried: list[str] | None = None
    pending_queries: list[str] | None = None
    relevant_docs: list[SearchResult] | None = None
    retrieval_exhausted: bool
    trace: list[dict[str, Any]]


class GenerateNodeOutput(_AgentNodeOutput):
    answer: Answer
    relevant_docs: list[SearchResult]
    trace: list[dict[str, Any]]


class CheckAnswerNodeOutput(_AgentNodeOutput):
    trace: list[dict[str, Any]]
