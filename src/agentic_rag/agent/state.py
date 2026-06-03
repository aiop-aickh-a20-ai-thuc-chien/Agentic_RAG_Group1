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
    queries_tried: Annotated[list[str], operator.add]
    step_count: int
    retrieval_exhausted: bool
    document_ids: NotRequired[list[str] | None]
    answer: NotRequired[Answer]
    trace: Annotated[list[dict[str, Any]], operator.add]
