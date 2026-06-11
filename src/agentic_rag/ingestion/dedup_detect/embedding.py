"""Layer 3: embedding-similarity duplicate detection."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence

from agentic_rag.core.contracts import EmbeddingInput
from agentic_rag.core.ports import EmbeddingClient
from agentic_rag.ingestion.dedup_detect.models import DedupDocument, DuplicateMatch

EmbeddingVectorMap = Mapping[str, Sequence[float]]


def embedding_vectors_from_client(
    documents: Sequence[DedupDocument],
    client: EmbeddingClient,
) -> dict[str, list[float]]:
    """Embed documents with the shared project embedding client contract."""

    output = client.embed(EmbeddingInput(texts=[document.text for document in documents]))
    return {document.document_id: output.vectors[index] for index, document in enumerate(documents)}


def find_embedding_duplicates(
    documents: Iterable[DedupDocument],
    *,
    vectors: EmbeddingVectorMap,
    similarity_threshold: float = 0.92,
    method: str | None = None,
    exclude_pairs: set[tuple[str, str]] | None = None,
) -> list[DuplicateMatch]:
    """Find semantically similar documents using cosine over supplied embeddings."""

    if not 0.0 <= similarity_threshold <= 1.0:
        raise ValueError("similarity_threshold must be between 0 and 1.")

    excluded = exclude_pairs or set()
    indexed = [(document, vectors.get(document.document_id)) for document in documents]
    matches: list[DuplicateMatch] = []
    for left_index, (left, left_vector) in enumerate(indexed):
        if left_vector is None:
            continue
        for right, right_vector in indexed[left_index + 1 :]:
            if right_vector is None:
                continue
            pair = _pair_key(left.document_id, right.document_id)
            if pair in excluded:
                continue
            similarity = cosine_similarity(left_vector, right_vector)
            if similarity < similarity_threshold:
                continue
            matches.append(
                DuplicateMatch(
                    layer="embedding_similarity",
                    document_id=left.document_id,
                    duplicate_document_id=right.document_id,
                    score=round(similarity, 6),
                    reason="embedding cosine similarity above threshold",
                    metadata={
                        "similarity_threshold": similarity_threshold,
                        "method": method,
                    },
                )
            )
    return matches


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Return cosine similarity between two vectors."""

    if len(left) != len(right):
        raise ValueError("Embedding vectors must have the same dimensions.")
    if not left:
        raise ValueError("Embedding vectors must not be empty.")

    dot = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)
