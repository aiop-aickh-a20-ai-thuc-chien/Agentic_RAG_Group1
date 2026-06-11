"""Layer 3: embedding-similarity duplicate detection."""

from __future__ import annotations

import math
import os
from collections.abc import Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import EmbeddingInput
from agentic_rag.core.ports import EmbeddingClient
from agentic_rag.ingestion.dedup_detect.models import DedupDocument, DuplicateMatch
from agentic_rag.model_runtime.config import (
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingConfig,
)
from agentic_rag.model_runtime.embeddings import (
    HuggingFaceEmbeddingClient,
    LiteLLMEmbeddingClient,
)
from agentic_rag.runtime_env import load_local_env

EmbeddingVectorMap = Mapping[str, Sequence[float]]
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
DEDUP_OPENAI_MODEL_ENV = "DEDUP_DETECT_OPENAI_EMBEDDING_MODEL"
DEDUP_OPENAI_API_KEY_ENV = "DEDUP_DETECT_OPENAI_API_KEY"
DEDUP_OPENAI_API_BASE_ENV = "DEDUP_DETECT_OPENAI_API_BASE"
DEDUP_SENTENCE_TRANSFORMER_MODEL_ENV = "DEDUP_DETECT_SENTENCE_TRANSFORMER_MODEL"
DEDUP_SENTENCE_TRANSFORMER_DEVICE_ENV = "DEDUP_DETECT_SENTENCE_TRANSFORMER_DEVICE"


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
) -> dict[str, list[float]]:
    """Embed documents with the shared project embedding client contract."""

    output = client.embed(EmbeddingInput(texts=[document.text for document in documents]))
    return {document.document_id: output.vectors[index] for index, document in enumerate(documents)}


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


def openai_first_embedding_candidates(
    *,
    openai_model: str | None = None,
    openai_api_base: str | None = None,
    openai_api_key: str | None = None,
    sentence_transformer_model: str | None = None,
    sentence_transformer_device: str | None = None,
    timeout_seconds: float = 60.0,
) -> list[EmbeddingFallbackCandidate]:
    """Build Layer 3 candidates: OpenAI first, local sentence-transformers second."""

    load_local_env()
    candidates: list[EmbeddingFallbackCandidate] = []

    resolved_openai_model = (
        openai_model
        or _env_value(DEDUP_OPENAI_MODEL_ENV)
        or _configured_api_embedding_model()
        or DEFAULT_OPENAI_EMBEDDING_MODEL
    )
    resolved_openai_api_key = (
        openai_api_key
        or _env_value(DEDUP_OPENAI_API_KEY_ENV)
        or _env_value("OPENAI_API_KEY")
        or _env_value("EMBEDDING_API_KEY")
    )
    resolved_openai_api_base = (
        openai_api_base
        or _env_value(DEDUP_OPENAI_API_BASE_ENV)
        or _env_value("OPENAI_API_BASE")
        or _api_embedding_base_from_env()
    )
    if resolved_openai_api_key or resolved_openai_api_base:
        candidates.append(
            EmbeddingFallbackCandidate(
                name=f"openai:{resolved_openai_model}",
                provider="openai",
                model=resolved_openai_model,
                client=LiteLLMEmbeddingClient(
                    config=EmbeddingConfig(
                        provider="openai",
                        model=resolved_openai_model,
                        api_base=resolved_openai_api_base,
                        api_key=resolved_openai_api_key,
                        expected_dimensions=_optional_positive_int(
                            "DEDUP_DETECT_OPENAI_EMBEDDING_DIMENSIONS"
                        )
                        or _optional_positive_int("EMBEDDING_DIMENSIONS"),
                        timeout_seconds=timeout_seconds,
                    )
                ),
            )
        )

    resolved_sentence_transformer_model = (
        sentence_transformer_model
        or _env_value(DEDUP_SENTENCE_TRANSFORMER_MODEL_ENV)
        or _configured_sentence_transformer_model()
        or DEFAULT_EMBEDDING_MODEL
    )
    resolved_sentence_transformer_device = _optional_device(
        sentence_transformer_device
        or _env_value(DEDUP_SENTENCE_TRANSFORMER_DEVICE_ENV)
        or _env_value("EMBEDDING_DEVICE")
    )
    candidates.append(
        EmbeddingFallbackCandidate(
            name=f"sentence_transformers:{resolved_sentence_transformer_model}",
            provider="sentence_transformers",
            model=resolved_sentence_transformer_model,
            client=HuggingFaceEmbeddingClient(
                config=EmbeddingConfig(
                    provider="sentence_transformers",
                    model=resolved_sentence_transformer_model,
                    timeout_seconds=timeout_seconds,
                    device=resolved_sentence_transformer_device,
                ),
                device=resolved_sentence_transformer_device,
            ),
        )
    )
    return candidates


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
                        "provider": provider,
                        "model": model,
                        "fallback_attempts": [dict(attempt) for attempt in fallback_attempts],
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


def _env_value(name: str) -> str | None:
    raw_value = os.getenv(name)
    if raw_value is None:
        return None
    value = raw_value.strip()
    return value or None


def _configured_api_embedding_model() -> str | None:
    provider = (_env_value("EMBEDDING_PROVIDER") or "").lower()
    if provider and provider != "sentence_transformers":
        return _env_value("EMBEDDING_MODEL")
    return _env_value("OPENAI_EMBEDDING_MODEL")


def _api_embedding_base_from_env() -> str | None:
    provider = (_env_value("EMBEDDING_PROVIDER") or "").lower()
    if provider and provider != "sentence_transformers":
        return _env_value("EMBEDDING_API_BASE")
    return None


def _configured_sentence_transformer_model() -> str | None:
    provider = (_env_value("EMBEDDING_PROVIDER") or "sentence_transformers").lower()
    if provider == "sentence_transformers":
        return _env_value("EMBEDDING_MODEL")
    return None


def _optional_device(value: str | None) -> str | None:
    if value is None or value.lower() == "auto":
        return None
    return value


def _optional_positive_int(name: str) -> int | None:
    value = _env_value(name)
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None
