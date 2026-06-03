"""Evaluation metric boundaries for Recall@k and MRR@k."""

from __future__ import annotations


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int = 5) -> float:
    """Compute Recall@k for retrieval evaluation."""

    if not relevant_ids:
        return 0.0
    
    top_k = set(retrieved_ids[:k])
    if top_k.intersection(relevant_ids):
        return 1.0
    return 0.0


def mrr_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int = 5) -> float:
    """Compute MRR@k for retrieval evaluation."""

    if not relevant_ids:
        return 0.0
        
    top_k = ranked_ids[:k]
    for i, chunk_id in enumerate(top_k, start=1):
        if chunk_id in relevant_ids:
            return 1.0 / i
            
    return 0.0
