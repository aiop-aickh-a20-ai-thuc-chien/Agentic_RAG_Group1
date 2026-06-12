"""Agent state shared across all LangGraph nodes."""

from __future__ import annotations

import operator
from typing import Annotated, Any, NotRequired

from typing_extensions import TypedDict

from agentic_rag.core.contracts import Answer, SearchResult


class AgentState(TypedDict):
    question: str
    rewritten_question: str
    history: list[dict[str, str]]
    pending_queries: list[str]
    fused_results: Annotated[list[SearchResult], operator.add]
    relevant_docs: list[SearchResult]
    pinned_docs: Annotated[list[SearchResult], operator.add]
    missing_entities: list[str]
    rejected_chunk_ids: Annotated[list[str], operator.add]
    queries_tried: Annotated[list[str], operator.add]
    step_count: int
    retrieval_exhausted: bool
    document_ids: NotRequired[list[str] | None]
    exclude_dedup_layers: NotRequired[list[str]]
    answer: NotRequired[Answer]
    trace: Annotated[list[dict[str, Any]], operator.add]
    # Clarification node fields
    single_turn: NotRequired[bool]
    needs_clarification: NotRequired[bool]
    clarification_question: NotRequired[str | None]
    clarification_reason: NotRequired[str | None]
    detected_entities: NotRequired[list[str]]
    detected_intents: NotRequired[list[str]]
    pending_clarification: NotRequired[dict[str, str] | None]
    # Language detection — set once in preprocess, read by all downstream nodes
    detected_language: NotRequired[str]
