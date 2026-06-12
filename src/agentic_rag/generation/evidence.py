"""Evidence provider selection for API and UI workflows."""

from __future__ import annotations

import os
from typing import Literal

from agentic_rag.core.contracts import (
    EvidenceResolutionInput,
    EvidenceResolutionOutput,
    RetrievalInput,
)
from agentic_rag.core.ports import SourceEvidenceProvider
from agentic_rag.integrations.local_pdf.providers import LocalPdfEvidenceProvider
from agentic_rag.integrations.ragflow.client import RAGFlowClient
from agentic_rag.integrations.ragflow.config import RAGFlowConfig
from agentic_rag.integrations.ragflow.providers import RAGFlowEvidenceProvider
from agentic_rag.retrieval.fusion import build_evidence_context
from agentic_rag.testing.fixtures import sample_search_results

EvidenceProviderName = Literal["mock", "request", "ragflow", "local_pdf"]


def configured_evidence_provider_name() -> EvidenceProviderName:
    """Return the active evidence provider from the EVIDENCE_PROVIDER env var.

    Recognised values: ``ragflow``, ``local_pdf``, ``request``.
    Anything else (including unset) falls back to ``mock`` - suitable for
    local development only.  Production deployments must set this variable.
    """

    raw = os.getenv("EVIDENCE_PROVIDER", "mock").strip().lower()
    if raw == "request":
        return "request"
    if raw == "ragflow":
        return "ragflow"
    if raw == "local_pdf":
        return "local_pdf"
    return "mock"


def evidence_for_question(
    request: EvidenceResolutionInput,
) -> EvidenceResolutionOutput:
    """Resolve evidence chunks and context for a generation request.

    Priority: explicit ``evidence_chunks`` > real provider retrieval >
    mock fixture data (only when ``use_mock_evidence=True``) > empty.
    Returns an empty evidence list when no source is available, which
    causes the generator to produce a ``not_found`` answer rather than
    hallucinating.
    """

    selected_provider = request.provider or configured_evidence_provider_name()
    if request.evidence_chunks is not None:
        chunks = request.evidence_chunks
    elif selected_provider in {"ragflow", "local_pdf"}:
        chunks = (
            source_provider_from_env()
            .retrieve(
                RetrievalInput(
                    question=request.question,
                    document_ids=request.document_ids,
                    exclude_dedup_layers=request.exclude_dedup_layers,
                )
            )
            .results
        )
    elif request.use_mock_evidence and selected_provider == "mock":
        chunks = sample_search_results()
    else:
        chunks = []

    context = (
        request.evidence_context
        if request.evidence_context is not None
        else build_evidence_context(chunks)
    )
    return EvidenceResolutionOutput(chunks=chunks, context=context)


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
