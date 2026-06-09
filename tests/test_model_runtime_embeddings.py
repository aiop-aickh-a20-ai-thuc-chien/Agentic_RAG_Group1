from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest
from pytest import MonkeyPatch

from agentic_rag.core.contracts import EmbeddingInput
from agentic_rag.model_runtime.config import EmbeddingConfig
from agentic_rag.model_runtime.embeddings import (
    EmbeddingCompatibilityAdapter,
    HuggingFaceEmbeddingClient,
    LiteLLMEmbeddingClient,
    validate_embedding_output,
)
from agentic_rag.model_runtime.errors import ModelRuntimeConfigurationError


def _config(
    *,
    provider: str = "openai",
    model: str = "text-embedding-3-small",
    dimensions: int | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> EmbeddingConfig:
    return EmbeddingConfig(
        provider=provider,
        model=model,
        api_base=api_base,
        api_key=api_key,
        expected_dimensions=dimensions,
        timeout_seconds=9.0,
    )


def test_litellm_embedding_receives_one_batch_and_preserves_order(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_embedding(**kwargs: Any) -> object:
        captured.update(kwargs)
        return {
            "data": [
                {"embedding": [0.1, 0.2]},
                {"embedding": [0.3, 0.4]},
            ]
        }

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(embedding=fake_embedding))
    client = LiteLLMEmbeddingClient(
        config=_config(api_base="https://example.test/v1", api_key="secret")
    )

    output = client.embed(EmbeddingInput(texts=["first", "second"]))

    assert output.vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert output.provider == "openai"
    assert output.model == "openai/text-embedding-3-small"
    assert output.dimensions == 2
    assert captured["model"] == "openai/text-embedding-3-small"
    assert captured["input"] == ["first", "second"]
    assert captured["api_base"] == "https://example.test/v1"
    assert captured["api_key"] == "secret"
    assert captured["timeout"] == 9.0


def test_local_embedding_provider_uses_openai_compatible_litellm_model(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_embedding(**kwargs: Any) -> object:
        captured.update(kwargs)
        return {"data": [{"embedding": [0.1, 0.2]}]}

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(embedding=fake_embedding))
    client = LiteLLMEmbeddingClient(
        config=_config(
            provider="local",
            model="local-embedding-model",
            api_base="http://127.0.0.1:8000/v1",
        )
    )

    output = client.embed(EmbeddingInput(texts=["query"]))

    assert captured["model"] == "openai/local-embedding-model"
    assert captured["api_base"] == "http://127.0.0.1:8000/v1"
    assert output.provider == "local"
    assert output.model == "openai/local-embedding-model"


def test_embedding_validation_rejects_bad_vectors() -> None:
    config = _config(dimensions=3)

    with pytest.raises(ValueError, match="no vectors"):
        validate_embedding_output([], config=config, input_count=1, model_name=config.model)

    with pytest.raises(ValueError, match="inconsistent dimensions"):
        validate_embedding_output(
            [[0.1, 0.2], [0.3]],
            config=config,
            input_count=2,
            model_name=config.model,
        )

    with pytest.raises(ValueError, match="expected 3, received 2"):
        validate_embedding_output(
            [[0.1, 0.2]],
            config=config,
            input_count=1,
            model_name=config.model,
        )


def test_huggingface_embedding_loads_one_cached_model_per_model_device(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[tuple[str, str | None]] = []

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, device: str | None = None) -> None:
            calls.append((model_name, device))

        def encode(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
            assert kwargs["convert_to_numpy"] is False
            return [[float(index), float(index + 1)] for index, _text in enumerate(texts)]

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    config = _config(provider="huggingface", model="sentence-transformers/test")
    first = HuggingFaceEmbeddingClient(config=config, device="cpu")
    second = HuggingFaceEmbeddingClient(config=config, device="cpu")

    assert first.embed(EmbeddingInput(texts=["a"])).vectors == [[0.0, 1.0]]
    assert second.embed(EmbeddingInput(texts=["b"])).vectors == [[0.0, 1.0]]
    assert calls == [("sentence-transformers/test", "cpu")]


def test_huggingface_embedding_reports_missing_local_extra(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "sentence_transformers", raising=False)
    client = HuggingFaceEmbeddingClient(
        config=_config(provider="huggingface", model="sentence-transformers/test")
    )

    with pytest.raises(ModelRuntimeConfigurationError, match="uv sync --extra local-models"):
        client.embed(EmbeddingInput(texts=["text"]))


def test_embedding_compatibility_adapter_returns_plain_vectors(
    monkeypatch: MonkeyPatch,
) -> None:
    def fake_embedding(**kwargs: Any) -> object:
        texts = kwargs["input"]
        return {"data": [{"embedding": [float(index)]} for index, _text in enumerate(texts)]}

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(embedding=fake_embedding))
    adapter = EmbeddingCompatibilityAdapter(client=LiteLLMEmbeddingClient(config=_config()))

    assert adapter.embed_query("query") == [0.0]
    assert adapter.embed_documents(["a", "b"]) == [[0.0], [1.0]]
