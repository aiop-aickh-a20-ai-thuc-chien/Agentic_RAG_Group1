from __future__ import annotations

import sys
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pytest import MonkeyPatch

from agentic_rag.model_runtime.embeddings import (
    HuggingFaceEmbeddingClient,
    LiteLLMEmbeddingClient,
)
from agentic_rag.model_runtime.errors import ModelRuntimeConfigurationError
from agentic_rag.model_runtime.factory import (
    ModelRuntimeConfig,
    clear_model_runtime_caches,
    get_embedding_client,
    get_llm_client,
    get_reranker,
    preload_configured_models,
    validate_model_runtime_config,
)
from agentic_rag.model_runtime.llm import LiteLLMClient
from agentic_rag.model_runtime.rerankers import (
    LiteLLMReranker,
    ScoreReranker,
    SentenceTransformersReranker,
)

_ENV_NAMES = (
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_API_BASE",
    "LLM_API_KEY",
    "GENERATION_LLM_PROVIDER",
    "GENERATION_LLM_MODEL",
    "QUERY_REWRITE_LLM_PROVIDER",
    "QUERY_REWRITE_LLM_MODEL",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "EMBEDDING_API_BASE",
    "EMBEDDING_API_KEY",
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_TIMEOUT_SECONDS",
    "EMBEDDING_DEVICE",
    "RERANK_PROVIDER",
    "RERANK_MODEL",
    "RERANK_API_BASE",
    "RERANK_API_KEY",
    "RERANK_TIMEOUT_SECONDS",
    "RERANK_DEVICE",
    "RERANK_PRELOAD",
)


@pytest.fixture(autouse=True)
def _clean_runtime(monkeypatch: MonkeyPatch) -> Iterator[None]:
    clear_model_runtime_caches()
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("agentic_rag.model_runtime.config.load_local_env", lambda: None)
    yield
    clear_model_runtime_caches()


def test_get_llm_client_returns_none_only_for_disabled_provider() -> None:
    assert get_llm_client("generation") is None


def test_get_llm_client_uses_role_aware_profile(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("QUERY_REWRITE_LLM_MODEL", "gpt-4o")

    client = get_llm_client("query_rewrite")

    assert isinstance(client, LiteLLMClient)
    assert client.config.provider == "openai"
    assert client.config.model == "gpt-4o"


def test_factories_choose_reserved_local_and_litellm_adapters(
    monkeypatch: MonkeyPatch,
) -> None:
    assert isinstance(get_embedding_client(), HuggingFaceEmbeddingClient)
    assert isinstance(get_reranker(), ScoreReranker)

    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("RERANK_PROVIDER", "cohere")
    monkeypatch.setenv("RERANK_MODEL", "rerank-v3.5")
    clear_model_runtime_caches()

    assert isinstance(get_embedding_client(), LiteLLMEmbeddingClient)
    assert isinstance(get_reranker(), LiteLLMReranker)

    monkeypatch.setenv("RERANK_PROVIDER", "sentence_transformers")
    monkeypatch.delenv("RERANK_MODEL", raising=False)
    clear_model_runtime_caches()
    assert isinstance(get_reranker(), SentenceTransformersReranker)


def test_sentence_transformers_embedding_factory_passes_configured_device(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("EMBEDDING_DEVICE", "cuda")
    clear_model_runtime_caches()

    client = get_embedding_client()

    assert isinstance(client, HuggingFaceEmbeddingClient)
    assert client.device == "cuda"


def test_factories_cache_configured_clients(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")

    assert get_llm_client("generation") is get_llm_client("generation")
    assert get_embedding_client() is get_embedding_client()
    assert get_reranker() is get_reranker()


def test_validate_model_runtime_config_returns_all_profiles(monkeypatch: MonkeyPatch) -> None:
    config = validate_model_runtime_config()

    assert isinstance(config, ModelRuntimeConfig)
    assert {profile.role for profile in config.llm_profiles} == {
        "query_rewrite",
        "query_transform",
        "generation",
        "ingestion",
        "evaluation",
    }
    assert config.embedding.provider == "sentence_transformers"
    assert config.reranker.provider == "score"

    monkeypatch.setenv("GENERATION_LLM_PROVIDER", "openai")
    with pytest.raises(ModelRuntimeConfigurationError, match="GENERATION_LLM_MODEL"):
        validate_model_runtime_config()


def test_preload_configured_models_only_loads_local_reranker(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeCrossEncoder:
        def __init__(self, model_name: str, device: str | None = None) -> None:
            calls.append(model_name)

    monkeypatch.setenv("RERANK_PROVIDER", "cohere")
    monkeypatch.setenv("RERANK_MODEL", "rerank-v3.5")
    monkeypatch.setenv("RERANK_PRELOAD", "true")
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(CrossEncoder=FakeCrossEncoder),
    )
    skipped = cast(dict[str, object], preload_configured_models()["reranker"])
    assert skipped["status"] == "disabled"
    assert calls == []

    monkeypatch.setenv("RERANK_PROVIDER", "sentence_transformers")
    monkeypatch.delenv("RERANK_MODEL", raising=False)
    clear_model_runtime_caches()
    result = preload_configured_models()

    loaded = cast(dict[str, object], result["reranker"])
    assert loaded["status"] == "loaded"
    assert calls == ["BAAI/bge-reranker-v2-m3"]


def test_api_startup_uses_model_runtime_preload(monkeypatch: MonkeyPatch) -> None:
    import agentic_rag.api as api_module

    seen: dict[str, Any] = {}

    def fake_preload() -> dict[str, object]:
        seen["called"] = True
        return {"reranker": {"status": "loaded", "model": "test-reranker"}}

    monkeypatch.setattr(api_module, "preload_configured_models", fake_preload)

    api_module._preload_configured_models()

    assert seen["called"] is True
