from typing import Any

import pytest
from pytest import MonkeyPatch

from agentic_rag.retrieval.embeddings import (
    EmbeddingConfigurationError,
    create_embedding_client,
    resolve_embedding_config,
    validate_embedding_vectors,
)


def _clear_embedding_env(monkeypatch: MonkeyPatch) -> None:
    for name in (
        "DENSE_EMBEDDING_PROVIDER",
        "DENSE_EMBEDDING_DIMENSIONS",
        "OPENAI_API_KEY",
        "OPENAI_EMBEDDING_MODEL",
        "OPENAI_EMBEDDING_DIMENSIONS",
        "LOCAL_EMBEDDING_BASE_URL",
        "LOCAL_EMBEDDING_MODEL",
        "LOCAL_EMBEDDING_API_KEY",
        "HF_EMBEDDING_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_auto_embedding_provider_uses_openai_when_key_exists(
    monkeypatch: MonkeyPatch,
) -> None:
    _clear_embedding_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")

    config = resolve_embedding_config()

    assert config.requested_provider == "auto"
    assert config.resolved_provider == "openai"
    assert config.model == "text-embedding-3-small"
    assert config.expected_dimensions == 1536
    assert config.fallback_reason is None


def test_auto_embedding_provider_uses_local_when_openai_key_is_missing(
    monkeypatch: MonkeyPatch,
) -> None:
    _clear_embedding_env(monkeypatch)
    monkeypatch.setenv("LOCAL_EMBEDDING_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B")

    config = resolve_embedding_config()

    assert config.requested_provider == "auto"
    assert config.resolved_provider == "local_openai"
    assert config.model == "Qwen/Qwen3-Embedding-4B"
    assert config.base_url == "http://127.0.0.1:8000/v1"
    assert config.expected_dimensions is None
    assert config.fallback_reason == "openai_api_key_missing"


def test_auto_embedding_provider_requires_local_configuration_without_openai_key(
    monkeypatch: MonkeyPatch,
) -> None:
    _clear_embedding_env(monkeypatch)

    with pytest.raises(
        EmbeddingConfigurationError,
        match="LOCAL_EMBEDDING_BASE_URL and LOCAL_EMBEDDING_MODEL",
    ):
        resolve_embedding_config()


def test_explicit_openai_never_falls_back(monkeypatch: MonkeyPatch) -> None:
    _clear_embedding_env(monkeypatch)
    monkeypatch.setenv("DENSE_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("LOCAL_EMBEDDING_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL", "local-model")

    with pytest.raises(EmbeddingConfigurationError, match="OPENAI_API_KEY"):
        resolve_embedding_config()


def test_explicit_huggingface_remains_available(monkeypatch: MonkeyPatch) -> None:
    _clear_embedding_env(monkeypatch)
    monkeypatch.setenv("DENSE_EMBEDDING_PROVIDER", "huggingface")
    monkeypatch.setenv("HF_EMBEDDING_MODEL", "sentence-transformers/test-model")
    monkeypatch.setenv("DENSE_EMBEDDING_DIMENSIONS", "384")

    config = resolve_embedding_config()

    assert config.requested_provider == "huggingface"
    assert config.resolved_provider == "huggingface"
    assert config.model == "sentence-transformers/test-model"
    assert config.expected_dimensions == 384
    assert config.fallback_reason is None


def test_unknown_embedding_provider_is_rejected(monkeypatch: MonkeyPatch) -> None:
    _clear_embedding_env(monkeypatch)
    monkeypatch.setenv("DENSE_EMBEDDING_PROVIDER", "vllm")

    with pytest.raises(EmbeddingConfigurationError, match="Unsupported"):
        resolve_embedding_config()


def test_openai_client_receives_configured_dimensions(monkeypatch: MonkeyPatch) -> None:
    _clear_embedding_env(monkeypatch)
    monkeypatch.setenv("DENSE_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("OPENAI_EMBEDDING_DIMENSIONS", "1024")
    captured: dict[str, Any] = {}

    class FakeOpenAIEmbeddings:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeOpenAIEmbeddings)

    create_embedding_client(resolve_embedding_config())

    assert captured["model"] == "text-embedding-3-small"
    assert captured["dimensions"] == 1024
    assert captured["openai_api_key"] == "openai-secret"
    assert "openai_api_base" not in captured


def test_local_client_uses_openai_compatible_endpoint_without_dimensions(
    monkeypatch: MonkeyPatch,
) -> None:
    _clear_embedding_env(monkeypatch)
    monkeypatch.setenv("DENSE_EMBEDDING_PROVIDER", "local_openai")
    monkeypatch.setenv("DENSE_EMBEDDING_DIMENSIONS", "2560")
    monkeypatch.setenv("LOCAL_EMBEDDING_BASE_URL", "http://127.0.0.1:30000/v1")
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B")
    monkeypatch.setenv("LOCAL_EMBEDDING_API_KEY", "local-secret")
    captured: dict[str, Any] = {}

    class FakeOpenAIEmbeddings:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeOpenAIEmbeddings)

    create_embedding_client(resolve_embedding_config())

    assert captured["openai_api_base"] == "http://127.0.0.1:30000/v1"
    assert captured["model"] == "Qwen/Qwen3-Embedding-4B"
    assert captured["openai_api_key"] == "local-secret"
    assert captured["check_embedding_ctx_length"] is False
    assert captured["tiktoken_enabled"] is False
    assert "dimensions" not in captured


def test_vector_validation_infers_native_dimensions(monkeypatch: MonkeyPatch) -> None:
    _clear_embedding_env(monkeypatch)
    monkeypatch.setenv("DENSE_EMBEDDING_PROVIDER", "local_openai")
    monkeypatch.setenv("LOCAL_EMBEDDING_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL", "local-model")
    config = resolve_embedding_config()

    profile = validate_embedding_vectors([[0.1, 0.2], [0.3, 0.4]], config=config)

    assert profile.provider == "local_openai"
    assert profile.model == "local-model"
    assert profile.dimensions == 2


@pytest.mark.parametrize(
    ("vectors", "message"),
    [
        ([], "no vectors"),
        ([[]], "empty vector"),
        ([[0.1, 0.2], [0.3]], "inconsistent dimensions"),
    ],
)
def test_vector_validation_rejects_malformed_vectors(
    monkeypatch: MonkeyPatch,
    vectors: list[list[float]],
    message: str,
) -> None:
    _clear_embedding_env(monkeypatch)
    monkeypatch.setenv("DENSE_EMBEDDING_PROVIDER", "local_openai")
    monkeypatch.setenv("LOCAL_EMBEDDING_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL", "local-model")

    with pytest.raises(ValueError, match=message):
        validate_embedding_vectors(vectors, config=resolve_embedding_config())


def test_vector_validation_rejects_expected_dimension_mismatch(
    monkeypatch: MonkeyPatch,
) -> None:
    _clear_embedding_env(monkeypatch)
    monkeypatch.setenv("DENSE_EMBEDDING_PROVIDER", "local_openai")
    monkeypatch.setenv("DENSE_EMBEDDING_DIMENSIONS", "3")
    monkeypatch.setenv("LOCAL_EMBEDDING_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL", "local-model")

    with pytest.raises(ValueError, match="expected 3, received 2"):
        validate_embedding_vectors(
            [[0.1, 0.2]],
            config=resolve_embedding_config(),
        )
