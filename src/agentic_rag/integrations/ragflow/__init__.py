"""RAGFlow adapter helpers for baseline and fallback workflows."""

from agentic_rag.integrations.ragflow.adapters import (
    answer_from_ragflow_payload,
    chunk_from_ragflow_payload,
    citations_from_search_results,
    search_result_from_ragflow_hit,
)
from agentic_rag.integrations.ragflow.client import RAGFlowClient, RAGFlowClientError
from agentic_rag.integrations.ragflow.config import (
    RAGFlowConfig,
    RAGFlowConfigurationError,
)
from agentic_rag.integrations.ragflow.providers import (
    RAGFlowEvidenceProvider,
    RAGFlowUploadedDocument,
)

__all__ = [
    "RAGFlowClient",
    "RAGFlowClientError",
    "RAGFlowConfig",
    "RAGFlowConfigurationError",
    "RAGFlowEvidenceProvider",
    "RAGFlowUploadedDocument",
    "answer_from_ragflow_payload",
    "chunk_from_ragflow_payload",
    "citations_from_search_results",
    "search_result_from_ragflow_hit",
]
