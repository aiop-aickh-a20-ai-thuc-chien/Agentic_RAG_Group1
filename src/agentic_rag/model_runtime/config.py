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


def resolve_llm_profile(role: ModelRole) -> LLMProfileConfig:
    """Resolve one role-aware LLM profile without importing provider libraries."""

    load_local_env()
    role_prefix = f"{role.upper()}_LLM"
    provider = _env_value(f"{role_prefix}_PROVIDER", fallback_name="LLM_PROVIDER")
    provider = (provider or "none").lower()
    model = _env_value(f"{role_prefix}_MODEL", fallback_name="LLM_MODEL")
    api_base = _env_value(f"{role_prefix}_API_BASE", fallback_name="LLM_API_BASE")
    api_key = _env_value(f"{role_prefix}_API_KEY", fallback_name="LLM_API_KEY")
    timeout_seconds = _positive_float(
        f"{role_prefix}_TIMEOUT_SECONDS",
        fallback_name="LLM_TIMEOUT_SECONDS",
        default=DEFAULT_TIMEOUT_SECONDS,
    )

    if provider == "none":
        model = None
    elif not model:
        raise ModelRuntimeConfigurationError(
            f"{role_prefix}_MODEL or LLM_MODEL is required when {role_prefix}_PROVIDER "
            f"or LLM_PROVIDER is {provider!r}."
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
    provider = (_env_value("EMBEDDING_PROVIDER") or "huggingface").lower()
    if provider == "local_openai":
        raise ModelRuntimeConfigurationError(
            "EMBEDDING_PROVIDER=local_openai is no longer supported. "
            "Use EMBEDDING_PROVIDER=local for OpenAI-compatible local embedding endpoints."
        )
    model = _env_value("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
    if provider != "huggingface" and not model:
        raise ModelRuntimeConfigurationError(
            "EMBEDDING_MODEL is required when EMBEDDING_PROVIDER is not 'huggingface'."
        )

    return EmbeddingConfig(
        provider=provider,
        model=model,
        api_base=_env_value("EMBEDDING_API_BASE"),
        api_key=_env_value("EMBEDDING_API_KEY"),
        expected_dimensions=_optional_positive_int("EMBEDDING_DIMENSIONS"),
        timeout_seconds=_positive_float(
            "EMBEDDING_TIMEOUT_SECONDS",
            default=DEFAULT_TIMEOUT_SECONDS,
        ),
        device=_optional_device("EMBEDDING_DEVICE"),
    )


def resolve_reranker_config() -> RerankerConfig:
    """Resolve reranker configuration without importing model libraries."""

    load_local_env()
    provider = (_env_value("RERANK_PROVIDER") or "score").lower()
    model = _env_value("RERANK_MODEL")
    if provider == "score":
        model = None
    elif provider == "sentence_transformers":
        model = model or DEFAULT_RERANKER_MODEL
    elif not model:
        raise ModelRuntimeConfigurationError(
            "RERANK_MODEL is required when RERANK_PROVIDER is not 'score' or "
            "'sentence_transformers'."
        )

    return RerankerConfig(
        provider=provider,
        model=model,
        api_base=_env_value("RERANK_API_BASE"),
        api_key=_env_value("RERANK_API_KEY"),
        timeout_seconds=_positive_float(
            "RERANK_TIMEOUT_SECONDS",
            default=DEFAULT_TIMEOUT_SECONDS,
        ),
        device=_optional_device("RERANK_DEVICE"),
        preload=_bool_env("RERANK_PRELOAD"),
    )


def validate_model_runtime_config() -> None:
    """Validate all model-runtime profiles without contacting providers."""

    for role in _MODEL_ROLES:
        resolve_llm_profile(role)
    resolve_embedding_config()
    resolve_reranker_config()


def _env_value(name: str, *, fallback_name: str | None = None) -> str | None:
    raw_value = os.getenv(name)
    if (raw_value is None or not raw_value.strip()) and fallback_name is not None:
        raw_value = os.getenv(fallback_name)
    if raw_value is None:
        return None
    value = raw_value.strip()
    return value or None


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
