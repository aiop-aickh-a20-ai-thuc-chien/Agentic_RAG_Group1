"""Multi-strategy URL ingestion integration boundary."""

from agentic_rag.ingestion.integration.url.config import UrlIntegrationConfig
from agentic_rag.ingestion.integration.url.models import (
    UrlAcquisitionResult,
    UrlConflictCandidate,
    UrlEvidenceFact,
    UrlEvidenceRef,
    UrlIntegrationInput,
    UrlIntegrationResult,
    UrlStrategyCapabilities,
    UrlStrategyOutput,
    UrlStrategyTrace,
    UrlStructuredSection,
    UrlValidatedPayload,
)
from agentic_rag.ingestion.integration.url.pipeline import (
    UrlIntegrationAdapters,
    integrate_url,
)
from agentic_rag.ingestion.integration.url.registry import (
    supported_url_integration_strategies,
    url_strategy_capabilities,
)

__all__ = [
    "UrlAcquisitionResult",
    "UrlConflictCandidate",
    "UrlEvidenceFact",
    "UrlEvidenceRef",
    "UrlIntegrationAdapters",
    "UrlIntegrationConfig",
    "UrlIntegrationInput",
    "UrlIntegrationResult",
    "UrlStrategyCapabilities",
    "UrlStrategyOutput",
    "UrlStrategyTrace",
    "UrlStructuredSection",
    "UrlValidatedPayload",
    "integrate_url",
    "supported_url_integration_strategies",
    "url_strategy_capabilities",
]

