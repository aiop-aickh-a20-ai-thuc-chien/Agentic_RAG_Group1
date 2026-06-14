"""Strict model-runtime configuration resolved from environment variables."""

from __future__ import annotations

import os
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.core.contracts import ModelRole
from agentic_rag.model_runtime.errors import ModelRuntimeConfigurationError
from agentic_rag.runtime_env import load_local_env

DEFAULT_EMBEDDING_MODEL: Final[str] = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_RERANKER_MODEL: Final[str] = "BAAI/bge-reranker-v2-m3"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0
LOCAL_PROVIDER: Final[str] = "local"
SENTENCE_TRANSFORMERS_PROVIDER: Final[str] = "sentence_transformers"
_MODEL_ROLES: Final[tuple[ModelRole, ...]] = (
    "query_rewrite",
    "query_transform",
    "generation",
    "ingestion",
    "evaluation",
)


class _RuntimeConfigModel(BaseModel):
    """Base configuration for immutable model-runtime config objects."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class LLMProfileConfig(_RuntimeConfigModel):
    """Resolved LLM configuration for one model role."""

    role: ModelRole
    provider: str
    model: str | None
    api_base: str | None = None
    api_key: str | None = Field(default=None, repr=False)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


class EmbeddingConfig(_RuntimeConfigModel):
    """Resolved embedding configuration."""

    provider: str
    model: str
    api_base: str | None = None
    api_key: str | None = Field(default=None, repr=False)
    expected_dimensions: int | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    device: str | None = None


class RerankerConfig(_RuntimeConfigModel):
    """Resolved reranker configuration."""

    provider: str
    model: str | None = None
    api_base: str | None = None
    api_key: str | None = Field(default=None, repr=False)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    device: str | None = None
    preload: bool = False

    @property
    def model_name(self) -> str:
        """Return the configured model name for enabled reranker providers."""

        if not self.model:
            raise ModelRuntimeConfigurationError("Reranker provider requires RERANK_MODEL.")
        return self.model


class SparseConfig(_RuntimeConfigModel):
    """Resolved sparse retrieval configuration."""

    provider: str
    model: str | None = None


class DenseConfig(_RuntimeConfigModel):
    """Resolved dense retrieval configuration."""

    provider: str
    model: str | None = None


def resolve_llm_profile(role: ModelRole) -> LLMProfileConfig:
    """Resolve one role-aware LLM profile without importing provider libraries."""

    return _resolve_llm_profile(role, allow_global_fallback=True)


def resolve_explicit_llm_profile(role: ModelRole) -> LLMProfileConfig:
    """Resolve one role using only its role-prefixed environment variables."""

    return _resolve_llm_profile(role, allow_global_fallback=False)


def _resolve_llm_profile(
    role: ModelRole,
    *,
    allow_global_fallback: bool,
) -> LLMProfileConfig:
    load_local_env()
    role_prefix = f"{role.upper()}_LLM"
    provider = _env_value(
        f"{role_prefix}_PROVIDER",
        fallback_name="LLM_PROVIDER" if allow_global_fallback else None,
    )
    provider = (provider or "none").lower()
    model = _env_value(
        f"{role_prefix}_MODEL",
        fallback_name="LLM_MODEL" if allow_global_fallback else None,
    )
    api_base = _env_value(
        f"{role_prefix}_API_BASE",
        fallback_name="LLM_API_BASE" if allow_global_fallback else None,
    )
    api_key = _env_value(
        f"{role_prefix}_API_KEY",
        fallback_name="LLM_API_KEY" if allow_global_fallback else None,
    )
    timeout_seconds = _positive_float(
        f"{role_prefix}_TIMEOUT_SECONDS",
        fallback_name="LLM_TIMEOUT_SECONDS" if allow_global_fallback else None,
        default=DEFAULT_TIMEOUT_SECONDS,
    )

    if provider == SENTENCE_TRANSFORMERS_PROVIDER:
        raise ModelRuntimeConfigurationError(
            "LLM_PROVIDER=sentence_transformers is not supported. "
            "Use LLM_PROVIDER=local for a hosted local LLM."
        )
    if provider == "none":
        model = None
    elif not model:
        raise ModelRuntimeConfigurationError(
            f"{role_prefix}_MODEL or LLM_MODEL is required when {role_prefix}_PROVIDER "
            f"or LLM_PROVIDER is {provider!r}."
        )
    elif provider == LOCAL_PROVIDER and not api_base:
        raise ModelRuntimeConfigurationError(
            f"{role_prefix}_API_BASE or LLM_API_BASE is required when the resolved "
            "LLM provider is 'local'."
        )

    return LLMProfileConfig(
        role=role,
        provider=provider,
        model=model,
        api_base=api_base,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )


def resolve_embedding_config() -> EmbeddingConfig:
    """Resolve embedding configuration without importing model libraries."""

    load_local_env()
    provider = (_env_value("EMBEDDING_PROVIDER") or SENTENCE_TRANSFORMERS_PROVIDER).lower()
    _reject_legacy_provider(name="EMBEDDING_PROVIDER", provider=provider)
    model = _env_value("EMBEDDING_MODEL")
    api_base = _env_value("EMBEDDING_API_BASE")
    if provider == SENTENCE_TRANSFORMERS_PROVIDER:
        model = model or DEFAULT_EMBEDDING_MODEL
    elif not model:
        raise ModelRuntimeConfigurationError(
            "EMBEDDING_MODEL is required unless EMBEDDING_PROVIDER is 'sentence_transformers'."
        )
    if provider == LOCAL_PROVIDER and not api_base:
        raise ModelRuntimeConfigurationError(
            "EMBEDDING_API_BASE is required when EMBEDDING_PROVIDER is 'local'."
        )

    return EmbeddingConfig(
        provider=provider,
        model=model,
        api_base=api_base,
        api_key=_env_value("EMBEDDING_API_KEY"),
        expected_dimensions=_optional_positive_int("EMBEDDING_DIMENSIONS"),
        timeout_seconds=_positive_float(
            "EMBEDDING_TIMEOUT_SECONDS",
            default=DEFAULT_TIMEOUT_SECONDS,
        ),
        device=(
            _optional_device("EMBEDDING_DEVICE")
            if provider == SENTENCE_TRANSFORMERS_PROVIDER
            else None
        ),
    )


def resolve_reranker_config() -> RerankerConfig:
    """Resolve reranker configuration without importing model libraries."""

    load_local_env()
    provider = (_env_value("RERANK_PROVIDER") or "score").lower()
    model = _env_value("RERANK_MODEL")
    api_base = _env_value("RERANK_API_BASE")
    if provider == "score":
        model = None
    elif provider == SENTENCE_TRANSFORMERS_PROVIDER:
        model = model or DEFAULT_RERANKER_MODEL
    elif provider == "listwise_llm":
        model = model or "castorini/rankzephyr-7b-v1-full"
    elif not model:
        raise ModelRuntimeConfigurationError(
            "RERANK_MODEL is required when RERANK_PROVIDER is not 'score', "
            "'listwise_llm', or 'sentence_transformers'."
        )
    if provider == LOCAL_PROVIDER and not api_base:
        raise ModelRuntimeConfigurationError(
            "RERANK_API_BASE is required when RERANK_PROVIDER is 'local'."
        )

    return RerankerConfig(
        provider=provider,
        model=model,
        api_base=api_base,
        api_key=_env_value("RERANK_API_KEY"),
        timeout_seconds=_positive_float(
            "RERANK_TIMEOUT_SECONDS",
            default=DEFAULT_TIMEOUT_SECONDS,
        ),
        device=(
            _optional_device("RERANK_DEVICE")
            if provider in (SENTENCE_TRANSFORMERS_PROVIDER, "listwise_llm")
            else None
        ),
        preload=(
            _bool_env("RERANK_PRELOAD") if provider == SENTENCE_TRANSFORMERS_PROVIDER else False
        ),
    )


def resolve_sparse_config() -> SparseConfig:
    """Resolve sparse retrieval configuration."""

    load_local_env()
    provider = (_env_value("SPARSE_PROVIDER") or "bm25").lower()
    model = _env_value("SPARSE_MODEL")
    if provider == "neural" and not model:
        model = "BAAI/bge-m3"

    return SparseConfig(
        provider=provider,
        model=model,
    )


def resolve_dense_config() -> DenseConfig:
    """Resolve dense retrieval configuration."""

    load_local_env()
    provider = (_env_value("DENSE_PROVIDER") or "vector_store").lower()
    model = _env_value("DENSE_MODEL")
    if provider == "colbert" and not model:
        model = "BAAI/bge-m3"

    return DenseConfig(
        provider=provider,
        model=model,
    )


def validate_model_runtime_config() -> None:
    """Validate all model-runtime profiles without contacting providers."""

    for role in _MODEL_ROLES:
        resolve_llm_profile(role)
    resolve_embedding_config()
    resolve_reranker_config()
    resolve_sparse_config()
    resolve_dense_config()


def _env_value(name: str, *, fallback_name: str | None = None) -> str | None:
    raw_value = os.getenv(name)
    if (raw_value is None or not raw_value.strip()) and fallback_name is not None:
        raw_value = os.getenv(fallback_name)
    if raw_value is None:
        return None
    value = raw_value.strip()
    return value or None


def _reject_legacy_provider(*, name: str, provider: str) -> None:
    replacements = {
        "huggingface": SENTENCE_TRANSFORMERS_PROVIDER,
        "local_openai": LOCAL_PROVIDER,
    }
    replacement = replacements.get(provider)
    if replacement is not None:
        raise ModelRuntimeConfigurationError(
            f"{name}={provider} is no longer supported. Use {name}={replacement}."
        )


def _positive_float(
    name: str,
    *,
    default: float,
    fallback_name: str | None = None,
) -> float:
    raw_value = os.getenv(name)
    used_name = name
    if (raw_value is None or not raw_value.strip()) and fallback_name is not None:
        raw_value = os.getenv(fallback_name)
        used_name = fallback_name
    if raw_value is None or not raw_value.strip():
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ModelRuntimeConfigurationError(f"{used_name} must be a positive number.") from exc
    if value <= 0:
        raise ModelRuntimeConfigurationError(f"{used_name} must be a positive number.")
    return value


def _optional_positive_int(name: str) -> int | None:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return None
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ModelRuntimeConfigurationError(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise ModelRuntimeConfigurationError(f"{name} must be a positive integer.")
    return value


def _optional_device(name: str) -> str | None:
    value = _env_value(name)
    if value is None or value.lower() == "auto":
        return None
    return value


def _bool_env(name: str) -> bool:
    value = _env_value(name)
    return value is not None and value.lower() in {"1", "true", "yes", "on"}
