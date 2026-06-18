"""Pydantic contracts returned by LangGraph agent nodes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.core.contracts import Answer, SearchResult


class _AgentNodeOutput(BaseModel):
    """Strict immutable base for partial AgentState updates."""
    model_config = ConfigDict(frozen=True, extra="forbid")


class PreprocessNodeOutput(_AgentNodeOutput):
    rewritten_question: str
    queries_tried: list[str]
    pending_queries: list[str] | None = None
    trace: list[dict[str, Any]]
    detected_language: str = "vi"
    # Canonical entities for the retrieval pre-filter. Kept separate from the
    # clarification node's ``detected_entities`` (VinFast model names, lowercase).
    filter_entities: list[str] = Field(default_factory=list)
    # Per-query map: {query: [canonical, ...]}. Decomposed queries each get their
    # own focused filter; single queries produce a one-entry map.
    filter_entities_map: dict[str, list[str]] = Field(default_factory=dict)
    boost_query_type: str = "unknown"


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
    rewritten_question: str | None = None
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


class ClarifyQuestionNodeOutput(_AgentNodeOutput):
    needs_clarification: bool
    detected_entities: list[str]
    detected_intents: list[str]
    clarification_question: str | None = None
    clarification_reason: str | None = None
    pending_clarification: dict[str, str] | None = None
    # Only set when needs_clarification=True; None means "leave state's answer untouched"
    answer: Answer | None = None
    trace: list[dict[str, Any]]
