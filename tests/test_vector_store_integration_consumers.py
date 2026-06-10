from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from pytest import MonkeyPatch

from agentic_rag.eval_review import (
    _all_qdrant_payloads,
    _qdrant_cache,
    _qdrant_cache_identity,
    get_doc_chunks,
)
from agentic_rag.retrieval.config import (
    VectorStoreConfigurationError,
    require_qdrant_vector_store_config,
)


def test_eval_review_qdrant_uses_canonical_config_without_api_key(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeQdrantClient:
        def __init__(self, *, url: str, api_key: str | None = None) -> None:
            seen["url"] = url
            seen["api_key"] = api_key

        def scroll(self, **kwargs: Any) -> tuple[list[object], None]:
            seen["scroll"] = kwargs
            return (
                [
                    SimpleNamespace(
                        payload={
                            "storage_chunk_id": "url_abc_section_c0001",
                            "text": "Pin VF8",
                            "section": "Warranty",
                            "url": "https://example.test",
                        }
                    )
                ],
                None,
            )

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setenv("VECTOR_STORE_COLLECTION", "canonical_chunks")
    monkeypatch.setattr("qdrant_client.QdrantClient", FakeQdrantClient)

    result = get_doc_chunks("url_abc_section_c0001")

    assert seen["url"] == "https://qdrant.example.test"
    assert seen["api_key"] is None
    assert seen["scroll"]["collection_name"] == "canonical_chunks"
    assert result["found"] is True
    assert result["chunks"][0]["chunk_id"] == "url_abc_section_c0001"


def test_eval_review_qdrant_error_detail_is_sanitized(monkeypatch: MonkeyPatch) -> None:
    class FakeQdrantClient:
        def __init__(self, *, url: str, api_key: str | None = None) -> None:
            pass

        def scroll(self, **kwargs: Any) -> tuple[list[object], None]:
            raise RuntimeError("credential=secret-token")

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setenv("VECTOR_STORE_API_KEY", "secret-token")
    monkeypatch.setattr("qdrant_client.QdrantClient", FakeQdrantClient)

    with pytest.raises(HTTPException) as raised:
        get_doc_chunks("url_abc_section_c0001")

    assert raised.value.status_code == 503
    assert raised.value.detail == "Qdrant query failed."


@pytest.mark.parametrize(
    ("provider", "url"),
    [
        ("qdrant", "http://[::1"),
        ("pgvector", "postgresql://[::1"),
    ],
)
def test_eval_review_malformed_vector_url_returns_sanitized_503(
    monkeypatch: MonkeyPatch,
    provider: str,
    url: str,
) -> None:
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", provider)
    monkeypatch.setenv("VECTOR_STORE_URL", url)

    with pytest.raises(HTTPException) as raised:
        get_doc_chunks("url_abc_section_c0001")

    assert raised.value.status_code == 503
    assert raised.value.detail == f"VECTOR_STORE_URL is invalid for {provider}."
    assert url not in raised.value.detail


def test_eval_review_pgvector_uses_canonical_config(monkeypatch: MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, query: str, params: tuple[str, str]) -> None:
            seen["query"] = query
            seen["params"] = params

        def fetchall(self) -> list[tuple[str, dict[str, str]]]:
            return [("Pin VF8", {"chunk_id": "url_abc_section_c0001"})]

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def cursor(self) -> FakeCursor:
            return FakeCursor()

    def fake_connect(db_url: str) -> FakeConnection:
        seen["db_url"] = db_url
        return FakeConnection()

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "pgvector")
    monkeypatch.setenv("VECTOR_STORE_URL", "postgresql+psycopg://db.example/rag")
    monkeypatch.setenv("VECTOR_STORE_COLLECTION", "pg_chunks")
    monkeypatch.setattr("psycopg.connect", fake_connect)

    result = get_doc_chunks("url_abc_section_c0001")

    assert seen["db_url"] == "postgresql://db.example/rag"
    assert seen["params"] == ("pg_chunks", "url_abc_")
    assert result["found"] is True
    assert result["chunks"][0]["chunk_id"] == "url_abc_section_c0001"


def test_eval_review_pgvector_error_detail_is_sanitized(monkeypatch: MonkeyPatch) -> None:
    def fake_connect(db_url: str) -> object:
        raise RuntimeError("password=secret")

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "pgvector")
    monkeypatch.setenv("VECTOR_STORE_URL", "postgresql://user:secret@db.example/rag")
    monkeypatch.setattr("psycopg.connect", fake_connect)

    with pytest.raises(HTTPException) as raised:
        get_doc_chunks("url_abc_section_c0001")

    assert raised.value.status_code == 503
    assert raised.value.detail == "pgvector query failed."


def test_eval_review_rejects_turbovec_doc_chunk_lookup(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "turbovec")

    with pytest.raises(HTTPException) as raised:
        get_doc_chunks("url_abc_section_c0001")

    assert raised.value.status_code == 503
    assert "VECTOR_STORE_PROVIDER" in str(raised.value.detail)


def test_eval_review_qdrant_payload_cache_is_keyed_by_url_and_collection() -> None:
    class FakeQdrantClient:
        def __init__(self, marker: str) -> None:
            self.marker = marker
            self.calls = 0

        def scroll(self, **kwargs: Any) -> tuple[list[object], None]:
            self.calls += 1
            return ([SimpleNamespace(payload={"marker": self.marker})], None)

    _qdrant_cache.update({"at": 0.0, "key": None, "payloads": []})
    first_client = FakeQdrantClient("first")
    second_client = FakeQdrantClient("second")

    first = _all_qdrant_payloads(
        first_client,
        "chunks",
        cache_key=("https://qdrant-one.example", "chunks"),
    )
    second = _all_qdrant_payloads(
        second_client,
        "chunks",
        cache_key=("https://qdrant-two.example", "chunks"),
    )

    assert first == [{"marker": "first"}]
    assert second == [{"marker": "second"}]
    assert first_client.calls == 1
    assert second_client.calls == 1


def test_eval_review_qdrant_cache_identity_does_not_retain_url_credentials() -> None:
    raw_url = "https://user:secret-token@qdrant.example.test"

    cache_key = _qdrant_cache_identity(raw_url, "chunks")

    assert cache_key[1] == "chunks"
    assert raw_url not in str(cache_key)
    assert "secret-token" not in str(cache_key)


def test_qdrant_script_config_uses_canonical_values_with_optional_api_key(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setenv("VECTOR_STORE_COLLECTION", "script_chunks")
    monkeypatch.delenv("VECTOR_STORE_API_KEY", raising=False)

    config = require_qdrant_vector_store_config()

    assert config.url is not None
    assert config.url.get_secret_value() == "https://qdrant.example.test"
    assert config.api_key is None
    assert config.collection == "script_chunks"


def test_qdrant_script_config_uses_canonical_api_key(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setenv("VECTOR_STORE_API_KEY", "secret")
    monkeypatch.setenv("VECTOR_STORE_COLLECTION", "script_chunks")

    config = require_qdrant_vector_store_config()

    assert config.api_key is not None
    assert config.api_key.get_secret_value() == "secret"


def test_qdrant_script_config_rejects_non_qdrant_provider(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "turbovec")

    with pytest.raises(VectorStoreConfigurationError, match="VECTOR_STORE_PROVIDER=qdrant"):
        require_qdrant_vector_store_config()
