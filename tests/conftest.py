"""Shared test configuration and fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _test_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate tests from .env settings that affect pipeline behavior."""
    for name in (
        "VECTOR_STORE_PROVIDER",
        "VECTOR_STORE_URL",
        "VECTOR_STORE_API_KEY",
        "VECTOR_STORE_COLLECTION",
        "DENSE_VECTOR_STORE",
        "DENSE_PGVECTOR_CONNECTION",
        "DENSE_PGVECTOR_COLLECTION",
        "QDRANT_URL",
        "QDRANT_API_KEY",
        "QDRANT_COLLECTION",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AGENT_MODE", "false")
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "turbovec")
    monkeypatch.setattr("agentic_rag.retrieval.config.load_local_env", lambda: None)
    monkeypatch.setenv("LANGSMITH_TRACE_MODE", "custom")
    monkeypatch.setenv("LOCAL_SOURCE_STORE", "jsonl")
