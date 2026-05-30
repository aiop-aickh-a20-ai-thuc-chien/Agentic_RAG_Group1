"""Evaluation metric boundaries for Recall@k and MRR@k."""

from __future__ import annotations


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int = 5) -> float:
    """Compute Recall@k for retrieval evaluation."""

    raise NotImplementedError("recall_at_k is scaffolded for evaluation reporting.")


def mrr_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int = 5) -> float:
    """Compute MRR@k for retrieval evaluation."""

    raise NotImplementedError("mrr_at_k is scaffolded for evaluation reporting.")
