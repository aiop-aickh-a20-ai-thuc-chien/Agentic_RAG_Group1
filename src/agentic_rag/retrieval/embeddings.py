"""Dense embedding provider resolution and vector validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_OPENAI_EMBEDDING_DIMENSIONS = 1536
DEFAULT_HF_EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

EmbeddingProvider = Literal["openai", "local_openai", "huggingface"]


class EmbeddingConfigurationError(ValueError):
    """Raised when the selected embedding provider cannot be configured."""


@dataclass(frozen=True)
class EmbeddingConfig:
    """Resolved embedding provider configuration."""

    requested_provider: str
    resolved_provider: EmbeddingProvider
    model: str
    expected_dimensions: int | None
    base_url: str | None = None
    api_key: str | None = field(default=None, repr=False)
    fallback_reason: str | None = None


@dataclass(frozen=True)
class EmbeddingProfile:
    """Identity and vector size of one embedding space."""

    provider: EmbeddingProvider
    model: str
    dimensions: int


def resolve_embedding_config() -> EmbeddingConfig:
    """Resolve the configured embedding provider without making network calls."""

    requested = os.getenv("DENSE_EMBEDDING_PROVIDER", "auto").strip().lower() or "auto"
    expected_dimensions = _optional_positive_int("DENSE_EMBEDDING_DIMENSIONS")

    if requested == "auto":
        if os.getenv("OPENAI_API_KEY", "").strip():
            return _openai_config(
                requested_provider=requested,
                expected_dimensions=expected_dimensions,
            )
        return _local_openai_config(
            requested_provider=requested,
            expected_dimensions=expected_dimensions,
            fallback_reason="openai_api_key_missing",
        )
    if requested == "openai":
        return _openai_config(
            requested_provider=requested,
            expected_dimensions=expected_dimensions,
        )
    if requested == "local_openai":
        return _local_openai_config(
            requested_provider=requested,
            expected_dimensions=expected_dimensions,
        )
    if requested == "huggingface":
        return EmbeddingConfig(
            requested_provider=requested,
            resolved_provider="huggingface",
            model=(
                os.getenv("HF_EMBEDDING_MODEL", DEFAULT_HF_EMBEDDING_MODEL).strip()
                or DEFAULT_HF_EMBEDDING_MODEL
            ),
            expected_dimensions=expected_dimensions,
        )
    raise EmbeddingConfigurationError(
        "Unsupported DENSE_EMBEDDING_PROVIDER. "
        "Expected one of: auto, openai, local_openai, huggingface."
    )


def create_embedding_client(config: EmbeddingConfig) -> Any:
    """Construct the LangChain embedding client for a resolved configuration."""

    if config.resolved_provider == "huggingface":
        from langchain_huggingface.embeddings import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(model_name=config.model)

    from langchain_openai import OpenAIEmbeddings

    if config.resolved_provider == "local_openai":
        return OpenAIEmbeddings(
            model=config.model,
            openai_api_base=config.base_url,
            openai_api_key=config.api_key or "local",
            check_embedding_ctx_length=False,
            tiktoken_enabled=False,
        )

    return OpenAIEmbeddings(
        model=config.model,
        dimensions=config.expected_dimensions,
        openai_api_key=config.api_key,
    )


def validate_embedding_vectors(
    vectors: list[list[float]],
    *,
    config: EmbeddingConfig,
) -> EmbeddingProfile:
    """Validate vector shape and return the active embedding profile."""

    if not vectors:
        raise ValueError("Embedding provider returned no vectors.")
    dimensions = len(vectors[0])
    if dimensions == 0:
        raise ValueError("Embedding provider returned an empty vector.")
    if any(len(vector) != dimensions for vector in vectors):
        raise ValueError("Embedding provider returned inconsistent dimensions.")
    if config.expected_dimensions is not None and dimensions != config.expected_dimensions:
        raise ValueError(
            "Embedding dimension mismatch: "
            f"expected {config.expected_dimensions}, received {dimensions}."
        )
    return EmbeddingProfile(
        provider=config.resolved_provider,
        model=config.model,
        dimensions=dimensions,
    )


def _openai_config(
    *,
    requested_provider: str,
    expected_dimensions: int | None,
) -> EmbeddingConfig:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise EmbeddingConfigurationError(
            "DENSE_EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY."
        )
    dimensions = expected_dimensions
    if dimensions is None:
        dimensions = _positive_int(
            "OPENAI_EMBEDDING_DIMENSIONS",
            DEFAULT_OPENAI_EMBEDDING_DIMENSIONS,
        )
    return EmbeddingConfig(
        requested_provider=requested_provider,
        resolved_provider="openai",
        model=(
            os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_OPENAI_EMBEDDING_MODEL).strip()
            or DEFAULT_OPENAI_EMBEDDING_MODEL
        ),
        expected_dimensions=dimensions,
        api_key=api_key,
    )


def _local_openai_config(
    *,
    requested_provider: str,
    expected_dimensions: int | None,
    fallback_reason: str | None = None,
) -> EmbeddingConfig:
    base_url = os.getenv("LOCAL_EMBEDDING_BASE_URL", "").strip().rstrip("/")
    model = os.getenv("LOCAL_EMBEDDING_MODEL", "").strip()
    if not base_url or not model:
        raise EmbeddingConfigurationError(
            "local_openai requires LOCAL_EMBEDDING_BASE_URL and LOCAL_EMBEDDING_MODEL."
        )
    return EmbeddingConfig(
        requested_provider=requested_provider,
        resolved_provider="local_openai",
        model=model,
        expected_dimensions=expected_dimensions,
        base_url=base_url,
        api_key=os.getenv("LOCAL_EMBEDDING_API_KEY", "").strip() or None,
        fallback_reason=fallback_reason,
    )


def _optional_positive_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return _parse_positive_int(name, raw)


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    return _parse_positive_int(name, raw)


def _parse_positive_int(name: str, raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise EmbeddingConfigurationError(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise EmbeddingConfigurationError(f"{name} must be a positive integer.")
    return value
