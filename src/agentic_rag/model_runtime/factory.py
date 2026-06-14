"""Factories for configured model-runtime clients."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Final

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import ModelRole
from agentic_rag.core.ports import EmbeddingClient, LLMClient, Reranker
from agentic_rag.model_runtime.config import (
    EmbeddingConfig,
    LLMProfileConfig,
    RerankerConfig,
    resolve_embedding_config,
    resolve_explicit_llm_profile,
    resolve_llm_profile,
    resolve_reranker_config,
)
from agentic_rag.model_runtime.embeddings import (
    HuggingFaceEmbeddingClient,
    LiteLLMEmbeddingClient,
)
from agentic_rag.model_runtime.llm import LiteLLMClient
from agentic_rag.model_runtime.rerankers import (
    LiteLLMReranker,
    ListwiseLLMReranker,
    ScoreReranker,
    SentenceTransformersReranker,
    preload_local_reranker,
)

LOGGER = logging.getLogger(__name__)
_MODEL_ROLES: Final[tuple[ModelRole, ...]] = (
    "query_rewrite",
    "query_transform",
    "generation",
    "ingestion",
    "evaluation",
)


class ModelRuntimeConfig(BaseModel):
    """Aggregate model-runtime configuration validated at startup."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    llm_profiles: tuple[LLMProfileConfig, ...]
    embedding: EmbeddingConfig
    reranker: RerankerConfig


@lru_cache(maxsize=len(_MODEL_ROLES))
def get_llm_client(role: ModelRole) -> LLMClient | None:
    """Return the configured LLM client for a role, or None for provider=none."""

    profile = resolve_llm_profile(role)
    if profile.provider == "none":
        return None
    return LiteLLMClient(config=profile)


@lru_cache(maxsize=len(_MODEL_ROLES))
def get_explicit_llm_client(role: ModelRole) -> LLMClient | None:
    """Return a client configured only by role-prefixed environment variables."""

    profile = resolve_explicit_llm_profile(role)
    if profile.provider == "none":
        return None
    return LiteLLMClient(config=profile)


@lru_cache(maxsize=1)
def get_embedding_client() -> EmbeddingClient:
    """Return the configured embedding client."""

    config = resolve_embedding_config()
    if config.provider == "sentence_transformers":
        return HuggingFaceEmbeddingClient(config=config, device=config.device)
    return LiteLLMEmbeddingClient(config=config)


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    """Return the configured reranker."""

    config = resolve_reranker_config()
    if config.provider == "score":
        return ScoreReranker()
    if config.provider == "sentence_transformers":
        return SentenceTransformersReranker(config=config, device=config.device)
    if config.provider == "listwise_llm":
        return ListwiseLLMReranker(config=config)
    return LiteLLMReranker(config=config)


def validate_model_runtime_config() -> ModelRuntimeConfig:
    """Validate every model-runtime profile without contacting providers."""

    return ModelRuntimeConfig(
        llm_profiles=tuple(resolve_llm_profile(role) for role in _MODEL_ROLES),
        embedding=resolve_embedding_config(),
        reranker=resolve_reranker_config(),
    )


def preload_configured_models() -> dict[str, object]:
    """Validate runtime config and preload enabled local models."""

    config = validate_model_runtime_config()
    _log_runtime_config(config)
    return {
        "llm_profiles": [
            {
                "role": profile.role,
                "provider": profile.provider,
                "model": profile.model,
            }
            for profile in config.llm_profiles
        ],
        "embedding": {
            "provider": config.embedding.provider,
            "model": config.embedding.model,
        },
        "reranker": preload_local_reranker(config.reranker),
    }


def clear_model_runtime_caches() -> None:
    """Clear cached configured clients for tests and config reloads."""

    get_llm_client.cache_clear()
    get_explicit_llm_client.cache_clear()
    get_embedding_client.cache_clear()
    get_reranker.cache_clear()


def _log_runtime_config(config: ModelRuntimeConfig) -> None:
    LOGGER.info(
        "Model runtime config: llm=%s embedding=%s/%s reranker=%s/%s",
        [
            {
                "role": profile.role,
                "provider": profile.provider,
                "model": profile.model,
            }
            for profile in config.llm_profiles
        ],
        config.embedding.provider,
        config.embedding.model,
        config.reranker.provider,
        config.reranker.model,
    )
