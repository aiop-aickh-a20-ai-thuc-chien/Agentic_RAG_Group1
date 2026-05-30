"""Grounded answer generation boundaries."""

from __future__ import annotations

from agentic_rag.core.contracts import Answer, SearchResult


def generate_answer(
    question: str,
    evidence_context: str,
    evidence_chunks: list[SearchResult],
) -> Answer:
    """Generate a grounded answer from retrieved evidence."""

    raise NotImplementedError("generate_answer is scaffolded for grounded answer generation.")


def validate_answer_with_citations(
    answer: str,
    citations: list[dict[str, object]],
    evidence_chunks: list[SearchResult],
) -> bool:
    """Validate that citations refer only to provided evidence chunks."""

    raise NotImplementedError(
        "validate_answer_with_citations is scaffolded for grounded answer generation."
    )
