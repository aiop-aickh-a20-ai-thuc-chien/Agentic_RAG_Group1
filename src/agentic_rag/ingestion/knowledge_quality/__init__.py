"""Knowledge-quality extension interfaces for ingestion."""

from agentic_rag.ingestion.knowledge_quality.detectors import (
    DeterministicKnowledgeQualityProcessor,
    analyze_chunks,
    annotate_chunks_with_quality,
)
from agentic_rag.ingestion.knowledge_quality.ports import KnowledgeQualityProcessor

__all__ = [
    "DeterministicKnowledgeQualityProcessor",
    "KnowledgeQualityProcessor",
    "analyze_chunks",
    "annotate_chunks_with_quality",
]
