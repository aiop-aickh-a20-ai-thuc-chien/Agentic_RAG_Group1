"""Layer 3: embedding-similarity duplicate detection."""

from __future__ import annotations

import math
import os
from collections.abc import Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import EmbeddingInput
from agentic_rag.core.ports import EmbeddingClient
from agentic_rag.ingestion.dedup_detect.models import DedupDocument, DuplicateMatch
from agentic_rag.model_runtime.config import resolve_embedding_config
from agentic_rag.model_runtime.factory import get_embedding_client

EmbeddingVectorMap = Mapping[str, Sequence[float]]
DEFAULT_EMBEDDING_BATCH_SIZE = 64


class _EmbeddingModel(BaseModel):
    """Base model for strict embedding fallback contracts."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)


class EmbeddingFallbackCandidate(_EmbeddingModel):
    """One Layer 3 embedding provider candidate."""

    name: str
    client: EmbeddingClient
    provider: str
    model: str


class EmbeddingVectorResult(_EmbeddingModel):
    """Embedding vectors plus provider metadata from fallback resolution."""

    vectors: dict[str, list[float]]
    provider: str
    model: str
    method: str
    fallback_attempts: tuple[dict[str, str], ...] = ()


def embedding_vectors_from_client(
    documents: Sequence[DedupDocument],
    client: EmbeddingClient,
    *,
    batch_size: int | None = None,
) -> dict[str, list[float]]:
    """Embed documents with the shared project embedding client contract."""

    if not documents:
        return {}
    resolved_batch_size = _embedding_batch_size(batch_size)
    vectors: dict[str, list[float]] = {}
    for start in range(0, len(documents), resolved_batch_size):
        batch = documents[start : start + resolved_batch_size]
        output = client.embed(EmbeddingInput(texts=[document.text for document in batch]))
        for document, vector in zip(batch, output.vectors, strict=True):
            vectors[document.document_id] = vector
    return vectors


def embedding_vectors_from_first_available_client(
    documents: Sequence[DedupDocument],
    *,
    candidates: Sequence[EmbeddingFallbackCandidate],
) -> EmbeddingVectorResult:
    """Embed documents with the first available candidate in provider order."""

    if not candidates:
        raise ValueError("At least one embedding fallback candidate is required.")

    attempts: list[dict[str, str]] = []
    for candidate in candidates:
        try:
            vectors = embedding_vectors_from_client(documents, candidate.client)
        except Exception as exc:
            attempts.append(
                {
                    "provider": candidate.provider,
                    "model": candidate.model,
                    "error": str(exc),
                }
            )
            continue
        return EmbeddingVectorResult(
            vectors=vectors,
            provider=candidate.provider,
            model=candidate.model,
            method=candidate.name,
            fallback_attempts=tuple(attempts),
        )

    attempted = ", ".join(f"{attempt['provider']}/{attempt['model']}" for attempt in attempts)
    raise RuntimeError(f"All embedding providers failed for dedup Layer 3: {attempted}")


def configured_embedding_candidates() -> list[EmbeddingFallbackCandidate]:
    """Build Layer 3 candidates from the shared project embedding runtime.

    Dedup detection intentionally does not define provider-specific defaults or
    `DEDUP_*` embedding variables. Configure Layer 3 through `.env.example`'s
    existing `EMBEDDING_*` contract.
    """

    config = resolve_embedding_config()
    return [
        EmbeddingFallbackCandidate(
            name=f"{config.provider}:{config.model}",
            provider=config.provider,
            model=config.model,
            client=get_embedding_client(),
        )
    ]


def _embedding_batch_size(batch_size: int | None) -> int:
    if batch_size is not None:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero.")
        return batch_size
    raw = os.getenv("DEDUP_EMBEDDING_BATCH_SIZE", str(DEFAULT_EMBEDDING_BATCH_SIZE))
    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_EMBEDDING_BATCH_SIZE
    return max(parsed, 1)


def find_embedding_duplicates(
    documents: Iterable[DedupDocument],
    *,
    vectors: EmbeddingVectorMap,
    similarity_threshold: float = 0.92,
    method: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    fallback_attempts: Sequence[Mapping[str, str]] = (),
    exclude_pairs: set[tuple[str, str]] | None = None,
    exclude_chunk_ids: set[str] | None = None,
) -> list[DuplicateMatch]:
    """Find semantically similar documents using cosine over supplied embeddings.

    ``exclude_chunk_ids`` skips documents already caught by earlier layers so
    the three layers form a strict cascade: exact → simhash → embedding.
    """

    if not 0.0 <= similarity_threshold <= 1.0:
        raise ValueError("similarity_threshold must be between 0 and 1.")

    excluded_pairs = exclude_pairs or set()
    excluded_chunks = exclude_chunk_ids or set()
    indexed = [
        (document, vectors.get(document.document_id))
        for document in documents
        if document.document_id not in excluded_chunks
    ]
    meta = {
        "similarity_threshold": similarity_threshold,
        "method": method,
        "provider": provider,
        "model": model,
        "fallback_attempts": [dict(attempt) for attempt in fallback_attempts],
    }
    matches: list[DuplicateMatch] = []
    for left_index, (left, left_vector) in enumerate(indexed):
        if left_vector is None:
            continue
        for right, right_vector in indexed[left_index + 1 :]:
            match = _check_pair(
                left,
                left_vector,
                right,
                right_vector,
                excluded_pairs=excluded_pairs,
                similarity_threshold=similarity_threshold,
                meta=meta,
            )
            if match is not None:
                matches.append(match)
    return matches


def _check_pair(
    left: DedupDocument,
    left_vector: Sequence[float] | None,
    right: DedupDocument,
    right_vector: Sequence[float] | None,
    *,
    excluded_pairs: set[tuple[str, str]],
    similarity_threshold: float,
    meta: Mapping[str, object],
) -> DuplicateMatch | None:
    if right_vector is None:
        return None
    pair = _pair_key(left.document_id, right.document_id)
    if pair in excluded_pairs:
        return None
    similarity = cosine_similarity(left_vector, right_vector)  # type: ignore[arg-type]
    if similarity < similarity_threshold:
        return None
    return DuplicateMatch(
        layer="embedding_similarity",
        document_id=left.document_id,
        duplicate_document_id=right.document_id,
        score=round(similarity, 6),
        reason="embedding cosine similarity above threshold",
        metadata=meta,
    )


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Return cosine similarity between two vectors."""

    if len(left) != len(right):
        raise ValueError("Embedding vectors must have the same dimensions.")
    if not left:
        raise ValueError("Embedding vectors must not be empty.")

    dot = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm < 1e-10 or right_norm < 1e-10:
        return 0.0
    return dot / (left_norm * right_norm)


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)
