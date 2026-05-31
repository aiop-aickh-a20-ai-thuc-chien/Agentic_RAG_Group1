"""Evidence provider selection for API and UI workflows."""

from __future__ import annotations

import os
from typing import Literal

from agentic_rag.core.contracts import SearchResult
from agentic_rag.generation.answering import format_evidence_context
from agentic_rag.integrations.ragflow.client import RAGFlowClient
from agentic_rag.integrations.ragflow.config import RAGFlowConfig
from agentic_rag.integrations.ragflow.providers import RAGFlowEvidenceProvider
from agentic_rag.testing.fixtures import sample_search_results

EvidenceProviderName = Literal["mock", "request", "ragflow"]


def configured_evidence_provider_name() -> EvidenceProviderName:
    """Return the configured evidence provider name."""

    raw = os.getenv("EVIDENCE_PROVIDER", "mock").strip().lower()
    if raw == "request":
        return "request"
    if raw == "ragflow":
        return "ragflow"
    return "mock"


def evidence_for_question(
    *,
    question: str,
    evidence_context: str | None = None,
    evidence_chunks: list[SearchResult] | None = None,
    provider: EvidenceProviderName | None = None,
    document_ids: list[str] | None = None,
    use_mock_evidence: bool = True,
) -> tuple[list[SearchResult], str]:
    """Resolve evidence chunks/context for a generation request."""

    selected_provider = provider or configured_evidence_provider_name()
    if evidence_chunks is not None:
        chunks = evidence_chunks
    elif selected_provider == "ragflow":
        chunks = ragflow_provider_from_env().retrieve(
            question=question,
            document_ids=document_ids,
        )
    elif use_mock_evidence and selected_provider == "mock":
        chunks = sample_search_results()
    else:
        chunks = []

    context = evidence_context if evidence_context is not None else format_evidence_context(chunks)
    return chunks, context


def ragflow_provider_from_env() -> RAGFlowEvidenceProvider:
    """Create the configured RAGFlow evidence provider."""

    config = RAGFlowConfig.from_env()
    return RAGFlowEvidenceProvider(
        RAGFlowClient(config),
        dataset_id=config.dataset_id,
    )
