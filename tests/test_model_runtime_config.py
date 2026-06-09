from __future__ import annotations

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from agentic_rag.core.contracts import ModelRole
from agentic_rag.model_runtime.config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RERANKER_MODEL,
    EmbeddingConfig,
    LLMProfileConfig,
    RerankerConfig,
    resolve_embedding_config,
    resolve_llm_profile,
    resolve_reranker_config,
    validate_model_runtime_config,
)
from agentic_rag.model_runtime.errors import ModelRuntimeConfigurationError

_MODEL_RUNTIME_ENV_NAMES = (
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_API_BASE",
    "LLM_API_KEY",
    "LLM_TIMEOUT_SECONDS",
    "QUERY_REWRITE_LLM_PROVIDER",
    "QUERY_REWRITE_LLM_MODEL",
    "QUERY_REWRITE_LLM_API_BASE",
    "QUERY_REWRITE_LLM_API_KEY",
    "QUERY_REWRITE_LLM_TIMEOUT_SECONDS",
    "QUERY_TRANSFORM_LLM_PROVIDER",
    "QUERY_TRANSFORM_LLM_MODEL",
    "QUERY_TRANSFORM_LLM_API_BASE",
    "QUERY_TRANSFORM_LLM_API_KEY",
    "QUERY_TRANSFORM_LLM_TIMEOUT_SECONDS",
    "GENERATION_LLM_PROVIDER",
    "GENERATION_LLM_MODEL",
    "GENERATION_LLM_API_BASE",
    "GENERATION_LLM_API_KEY",
    "GENERATION_LLM_TIMEOUT_SECONDS",
    "INGESTION_LLM_PROVIDER",
    "INGESTION_LLM_MODEL",
    "INGESTION_LLM_API_BASE",
    "INGESTION_LLM_API_KEY",
    "INGESTION_LLM_TIMEOUT_SECONDS",
    "EVALUATION_LLM_PROVIDER",
    "EVALUATION_LLM_MODEL",
    "EVALUATION_LLM_API_BASE",
    "EVALUATION_LLM_API_KEY",
    "EVALUATION_LLM_TIMEOUT_SECONDS",
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
    "OPENAI_MODEL",
    "OLLAMA_MODEL",
    "OLLAMA_BASE_URL",
    "GENERATION_MODEL",
    "DENSE_EMBEDDING_PROVIDER",
    "OPENAI_EMBEDDING_MODEL",
    "LOCAL_EMBEDDING_BASE_URL",
    "LOCAL_EMBEDDING_MODEL",
    "LOCAL_EMBEDDING_API_KEY",
    "HF_EMBEDDING_MODEL",
    "DENSE_EMBEDDING_DIMENSIONS",
    "OPENAI_EMBEDDING_DIMENSIONS",
    "RERANK_CROSS_ENCODER_MODEL",
)


def _clear_model_runtime_env(monkeypatch: MonkeyPatch) -> None:
    for name in _MODEL_RUNTIME_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("agentic_rag.model_runtime.config.load_local_env", lambda: None)


def test_global_llm_defaults_to_disabled_profile(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)

    profile = resolve_llm_profile("generation")

    assert profile.role == "generation"
    assert profile.provider == "none"
    assert profile.model is None
    assert profile.api_base is None
    assert profile.api_key is None
    assert profile.timeout_seconds == 60.0


def test_llm_role_inherits_fields_individually(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_API_BASE", "https://example.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "secret")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("QUERY_REWRITE_LLM_MODEL", "gpt-4o")

    profile = resolve_llm_profile("query_rewrite")

    assert profile.provider == "openai"
    assert profile.model == "gpt-4o"
    assert profile.api_base == "https://example.test/v1"
    assert profile.api_key == "secret"
    assert profile.timeout_seconds == 15.0


def test_blank_llm_role_overrides_inherit_global_profile(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_API_BASE", "https://example.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "secret")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "22")
    monkeypatch.setenv("GENERATION_LLM_PROVIDER", "")
    monkeypatch.setenv("GENERATION_LLM_MODEL", "")
    monkeypatch.setenv("GENERATION_LLM_API_BASE", "")
    monkeypatch.setenv("GENERATION_LLM_API_KEY", "")
    monkeypatch.setenv("GENERATION_LLM_TIMEOUT_SECONDS", "")

    profile = resolve_llm_profile("generation")

    assert profile.provider == "openai"
    assert profile.model == "gpt-4o-mini"
    assert profile.api_base == "https://example.test/v1"
    assert profile.api_key == "secret"
    assert profile.timeout_seconds == 22.0


def test_llm_role_can_override_only_provider(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-5")
    monkeypatch.setenv("GENERATION_LLM_PROVIDER", "anthropic")

    profile = resolve_llm_profile("generation")

    assert profile.provider == "anthropic"
    assert profile.model == "claude-sonnet-4-5"


def test_enabled_litellm_provider_requires_model(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    with pytest.raises(ModelRuntimeConfigurationError, match="LLM_MODEL"):
        resolve_llm_profile("generation")


def test_sentence_transformers_embedding_defaults(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)

    config = resolve_embedding_config()

    assert config.provider == "sentence_transformers"
    assert config.model == DEFAULT_EMBEDDING_MODEL
    assert config.expected_dimensions is None
    assert config.timeout_seconds == 60.0


def test_embedding_positive_dimensions_and_timeout(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1536")
    monkeypatch.setenv("EMBEDDING_TIMEOUT_SECONDS", "30")

    config = resolve_embedding_config()

    assert config.expected_dimensions == 1536
    assert config.timeout_seconds == 30.0

    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "0")
    with pytest.raises(ModelRuntimeConfigurationError, match="EMBEDDING_DIMENSIONS"):
        resolve_embedding_config()


def test_local_embedding_provider_is_supported(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_MODEL", "local-embedding-model")
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://127.0.0.1:8000/v1")

    config = resolve_embedding_config()

    assert config.provider == "local"
    assert config.model == "local-embedding-model"
    assert config.api_base == "http://127.0.0.1:8000/v1"


@pytest.mark.parametrize("provider", ["huggingface", "local_openai"])
def test_legacy_embedding_provider_values_fail_with_migration_message(
    monkeypatch: MonkeyPatch,
    provider: str,
) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("EMBEDDING_PROVIDER", provider)

    with pytest.raises(ModelRuntimeConfigurationError, match=r"sentence_transformers|local"):
        resolve_embedding_config()


@pytest.mark.parametrize(
    ("role", "missing_name"),
    [("generation", "GENERATION_LLM_API_BASE")],
)
def test_local_llm_requires_api_base(
    monkeypatch: MonkeyPatch,
    role: ModelRole,
    missing_name: str,
) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LLM_MODEL", "local-chat-model")

    with pytest.raises(ModelRuntimeConfigurationError, match=missing_name):
        resolve_llm_profile(role)


def test_local_embedding_requires_model_and_api_base(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")

    with pytest.raises(ModelRuntimeConfigurationError, match="EMBEDDING_MODEL"):
        resolve_embedding_config()

    monkeypatch.setenv("EMBEDDING_MODEL", "local-embedding-model")
    with pytest.raises(ModelRuntimeConfigurationError, match="EMBEDDING_API_BASE"):
        resolve_embedding_config()


def test_local_reranker_requires_model_and_api_base(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("RERANK_PROVIDER", "local")

    with pytest.raises(ModelRuntimeConfigurationError, match="RERANK_MODEL"):
        resolve_reranker_config()

    monkeypatch.setenv("RERANK_MODEL", "local-reranker")
    with pytest.raises(ModelRuntimeConfigurationError, match="RERANK_API_BASE"):
        resolve_reranker_config()


def test_embedding_device_parsing(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("EMBEDDING_DEVICE", "cuda")

    config = resolve_embedding_config()

    assert config.device == "cuda"


def test_embedding_device_auto_and_blank_resolve_to_auto(
    monkeypatch: MonkeyPatch,
) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("EMBEDDING_DEVICE", "auto")
    assert resolve_embedding_config().device is None

    monkeypatch.setenv("EMBEDDING_DEVICE", "")
    assert resolve_embedding_config().device is None


def test_reranker_reserved_defaults(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)

    score = resolve_reranker_config()
    assert score.provider == "score"
    assert score.model is None

    monkeypatch.setenv("RERANK_PROVIDER", "sentence_transformers")
    sentence_transformers = resolve_reranker_config()
    assert sentence_transformers.model == DEFAULT_RERANKER_MODEL
    assert sentence_transformers.device is None


def test_reranker_preload_and_device_parsing(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("RERANK_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("RERANK_DEVICE", "cuda")
    monkeypatch.setenv("RERANK_PRELOAD", "true")

    config = resolve_reranker_config()

    assert config.device == "cuda"
    assert config.preload is True


def test_configs_are_strict_frozen_and_hide_secrets() -> None:
    profile = LLMProfileConfig(
        role="generation",
        provider="openai",
        model="gpt-4o-mini",
        api_key="secret",
    )
    embedding = EmbeddingConfig(provider="openai", model="text-embedding-3-small", api_key="secret")
    reranker = RerankerConfig(provider="cohere", model="rerank-v3.5", api_key="secret")

    assert "secret" not in repr(profile)
    assert "secret" not in repr(embedding)
    assert "secret" not in repr(reranker)

    with pytest.raises(ValidationError):
        LLMProfileConfig.model_validate(
            {
                "role": "generation",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "unexpected": True,
            }
        )

    field_name = "provider"
    with pytest.raises(ValidationError):
        setattr(profile, field_name, "changed")


def test_legacy_model_environment_variables_have_no_effect(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "legacy-openai")
    monkeypatch.setenv("OLLAMA_MODEL", "legacy-ollama")
    monkeypatch.setenv("GENERATION_MODEL", "legacy-generation")
    monkeypatch.setenv("DENSE_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("HF_EMBEDDING_MODEL", "legacy-hf")
    monkeypatch.setenv("RERANK_CROSS_ENCODER_MODEL", "legacy-reranker")

    assert resolve_llm_profile("generation").provider == "none"
    assert resolve_llm_profile("generation").model is None
    assert resolve_embedding_config().provider == "sentence_transformers"
    assert resolve_embedding_config().model == DEFAULT_EMBEDDING_MODEL
    assert resolve_reranker_config().provider == "score"
    assert resolve_reranker_config().model is None


def test_validate_model_runtime_config_checks_all_profiles(monkeypatch: MonkeyPatch) -> None:
    _clear_model_runtime_env(monkeypatch)
    monkeypatch.setenv("GENERATION_LLM_PROVIDER", "openai")

    with pytest.raises(ModelRuntimeConfigurationError, match="GENERATION_LLM_MODEL"):
        validate_model_runtime_config()
