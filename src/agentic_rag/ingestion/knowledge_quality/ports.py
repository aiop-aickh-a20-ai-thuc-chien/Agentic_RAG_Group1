"""Protocol boundary for future knowledge-quality processing."""

from __future__ import annotations

from abc import abstractmethod
from typing import Protocol, runtime_checkable

from agentic_rag.core.contracts import Chunk


@runtime_checkable
class KnowledgeQualityProcessor(Protocol):
    """Optionally process normalized chunks during ingestion."""

    @abstractmethod
    def process(self, chunks: list[Chunk]) -> list[Chunk]:
        """Return chunks after optional knowledge-quality processing."""
        ...
