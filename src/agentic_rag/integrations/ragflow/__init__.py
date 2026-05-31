"""RAGFlow adapter helpers for baseline and fallback workflows."""

from agentic_rag.integrations.ragflow.adapters import (
    answer_from_ragflow_payload,
    chunk_from_ragflow_payload,
    citations_from_search_results,
    search_result_from_ragflow_hit,
)

__all__ = [
    "answer_from_ragflow_payload",
    "chunk_from_ragflow_payload",
    "citations_from_search_results",
    "search_result_from_ragflow_hit",
]
