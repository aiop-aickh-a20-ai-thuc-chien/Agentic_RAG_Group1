"""Knowledge-quality extension interfaces for ingestion."""

from agentic_rag.ingestion.knowledge_quality.detectors import (
    DeterministicKnowledgeQualityProcessor,
    analyze_chunks,
    annotate_chunks_with_quality,
)
from agentic_rag.ingestion.knowledge_quality.ports import KnowledgeQualityProcessor
from agentic_rag.ingestion.knowledge_quality.registry import (
    AVAILABLE_KNOWLEDGE_QUALITY_METHODS,
    MODEL_BACKED_KNOWLEDGE_QUALITY_METHODS,
    KnowledgeQualityConfigurationError,
    KnowledgeQualityInvocationError,
    UnknownKnowledgeQualityMethodError,
    parse_knowledge_quality_methods,
)

__all__ = [
    "AVAILABLE_KNOWLEDGE_QUALITY_METHODS",
    "MODEL_BACKED_KNOWLEDGE_QUALITY_METHODS",
    "DeterministicKnowledgeQualityProcessor",
    "KnowledgeQualityConfigurationError",
    "KnowledgeQualityInvocationError",
    "KnowledgeQualityProcessor",
    "UnknownKnowledgeQualityMethodError",
    "analyze_chunks",
    "annotate_chunks_with_quality",
    "parse_knowledge_quality_methods",
]
