"""LangGraph Self-RAG StateGraph with history-aware preprocess."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph

from agentic_rag.agent.nodes import (
    check_answer_node,
    generate_node,
    make_retrieve_node,
    preprocess_node,
    rerank_node,
    route_after_check,
    route_after_rerank,
    route_after_transform,
    transform_query_node,
)
from agentic_rag.agent.state import AgentState
from agentic_rag.core.contracts import Answer, SearchResult
from agentic_rag.core.ports import SourceEvidenceProvider


@dataclass(frozen=True)
class AgentResult:
    """Answer plus full agent trace for observability."""

    answer: Answer
    evidence_chunks: list[SearchResult]
    queries_tried: list[str]
    steps: list[dict[str, Any]]


def build_agent(provider: SourceEvidenceProvider) -> Any:
    retrieve_node = make_retrieve_node(provider)

    graph: StateGraph[AgentState, Any, Any] = StateGraph(AgentState)

    graph.add_node("preprocess", preprocess_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("rerank", rerank_node)
    graph.add_node("transform_query", transform_query_node)
    graph.add_node("generate", generate_node)
    graph.add_node("check_answer", check_answer_node)

    graph.add_edge(START, "preprocess")
    graph.add_edge("preprocess", "retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_conditional_edges(
        "rerank",
        route_after_rerank,
        {"generate": "generate", "transform_query": "transform_query"},
    )
    graph.add_conditional_edges(
        "transform_query",
        route_after_transform,
        {"retrieve": "retrieve", "generate": "generate", "check_answer": "check_answer"},
    )
    graph.add_edge("generate", "check_answer")
    graph.add_conditional_edges(
        "check_answer",
        route_after_check,
        {"end": END, "transform_query": "transform_query"},
    )

    return graph.compile()


def run_agent(
    *,
    provider: SourceEvidenceProvider,
    question: str,
    document_ids: list[str] | None = None,
    history: list[dict[str, str]] | None = None,
) -> AgentResult:
    agent = build_agent(provider)
    initial: AgentState = {
        "question": question,
        "rewritten_question": question,
        "history": history or [],
        "pending_queries": [],
        "fused_results": [],
        "relevant_docs": [],
        "pinned_docs": [],
        "missing_entities": [],
        "rejected_chunk_ids": [],
        "queries_tried": [question],
        "step_count": 0,
        "retrieval_exhausted": False,
        "document_ids": document_ids,
        "trace": [],
    }
    final_state: dict[str, Any] = agent.invoke(initial)

    answer = final_state.get("answer")
    if not isinstance(answer, Answer):
        answer = Answer(
            answer="Mình chưa tìm thấy thông tin này trong tài liệu được cung cấp.",
            status="not_found",
            citations=[],
        )

    return AgentResult(
        answer=answer,
        evidence_chunks=final_state.get("relevant_docs", []),
        queries_tried=final_state.get("queries_tried", [question]),
        steps=final_state.get("trace", []),
    )
