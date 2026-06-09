from __future__ import annotations

from collections.abc import Iterator

import pytest
from pytest import MonkeyPatch

from agentic_rag.model_runtime.factory import clear_model_runtime_caches
from agentic_rag.retrieval.search import dense_embedding_metadata


@pytest.fixture(autouse=True)
def _clean_runtime(monkeypatch: MonkeyPatch) -> Iterator[None]:
    clear_model_runtime_caches()
    monkeypatch.setattr("agentic_rag.model_runtime.config.load_local_env", lambda: None)
    yield
    clear_model_runtime_caches()


def test_dense_embedding_metadata_uses_default_huggingface_profile(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "huggingface")
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    metadata = dense_embedding_metadata()

    assert metadata["provider"] == "huggingface"
    assert metadata["requested_provider"] == "huggingface"
    assert metadata["resolved_provider"] == "huggingface"
    assert metadata["fallback_reason"] is None
    assert metadata["library"] == "sentence-transformers"


def test_dense_embedding_metadata_reports_litellm_embedding_profile(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1536")

    metadata = dense_embedding_metadata()

    assert metadata["provider"] == "openai"
    assert metadata["requested_provider"] == "openai"
    assert metadata["resolved_provider"] == "openai"
    assert metadata["expected_dimensions"] == 1536
    assert metadata["library"] == "litellm"
