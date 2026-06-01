"""Evidence provider selection for API and UI workflows."""

from __future__ import annotations

import os
from typing import Literal

from agentic_rag.core.contracts import SearchResult
from agentic_rag.core.ports import SourceEvidenceProvider
from agentic_rag.integrations.local_pdf.providers import LocalPdfEvidenceProvider
from agentic_rag.integrations.ragflow.client import RAGFlowClient
from agentic_rag.integrations.ragflow.config import RAGFlowConfig
from agentic_rag.integrations.ragflow.providers import RAGFlowEvidenceProvider
from agentic_rag.retrieval.fusion import build_evidence_context
from agentic_rag.testing.fixtures import sample_search_results

EvidenceProviderName = Literal["mock", "request", "ragflow", "local_pdf"]


def configured_evidence_provider_name() -> EvidenceProviderName:
    """Return the configured evidence provider name."""

    raw = os.getenv("EVIDENCE_PROVIDER", "mock").strip().lower()
    if raw == "request":
        return "request"
    if raw == "ragflow":
        return "ragflow"
    if raw == "local_pdf":
        return "local_pdf"
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
    elif selected_provider in {"ragflow", "local_pdf"}:
        chunks = source_provider_from_env().retrieve(
            question=question,
            document_ids=document_ids,
        )
    elif use_mock_evidence and selected_provider == "mock":
        chunks = sample_search_results()
    else:
        chunks = []

    context = evidence_context if evidence_context is not None else build_evidence_context(chunks)
    return chunks, context


def source_provider_from_env() -> SourceEvidenceProvider:
    """Create the configured source/evidence provider."""

    provider = configured_evidence_provider_name()
    if provider == "local_pdf":
        return LocalPdfEvidenceProvider.from_env()
    return ragflow_provider_from_env()


def ragflow_provider_from_env() -> RAGFlowEvidenceProvider:
    """Create the configured RAGFlow evidence provider."""

    config = RAGFlowConfig.from_env()
    return RAGFlowEvidenceProvider(
        RAGFlowClient(config),
        dataset_id=config.dataset_id,
    )
