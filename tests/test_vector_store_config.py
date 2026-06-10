from __future__ import annotations

import importlib
import warnings
from types import ModuleType

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

_VECTOR_STORE_ENV_NAMES = (
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
)


def _config_module() -> ModuleType:
    try:
        return importlib.import_module("agentic_rag.retrieval.config")
    except ModuleNotFoundError as exc:
        pytest.fail(f"vector-store configuration module is missing: {exc}")


def _clear_vector_store_env(monkeypatch: MonkeyPatch, module: ModuleType) -> None:
    for name in _VECTOR_STORE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(module, "load_local_env", lambda: None)


def test_defaults_to_keyless_turbovec(monkeypatch: MonkeyPatch) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)

    config = module.resolve_vector_store_config()

    assert config.provider == "turbovec"
    assert config.collection == "agentic_rag_chunks"
    assert config.url is None
    assert config.api_key is None


@pytest.mark.parametrize(
    ("name", "value", "expected_provider"),
    [
        ("DENSE_PGVECTOR_CONNECTION", "postgresql://db.example/rag", "pgvector"),
        ("QDRANT_URL", "https://qdrant.example.test", "qdrant"),
    ],
)
def test_legacy_connection_field_infers_provider(
    monkeypatch: MonkeyPatch,
    name: str,
    value: str,
    expected_provider: str,
) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv(name, value)

    with pytest.warns(FutureWarning, match=name):
        config = module.resolve_vector_store_config()

    assert config.provider == expected_provider
    assert config.url is not None
    assert config.url.get_secret_value() == value


@pytest.mark.parametrize(
    ("provider", "name", "value"),
    [
        ("pgvector", "DENSE_PGVECTOR_COLLECTION", "legacy_chunks"),
        ("qdrant", "QDRANT_API_KEY", "legacy-secret"),
        ("qdrant", "QDRANT_COLLECTION", "legacy_chunks"),
    ],
)
def test_related_legacy_field_infers_provider_and_requires_connection(
    monkeypatch: MonkeyPatch,
    provider: str,
    name: str,
    value: str,
) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv(name, value)

    with (
        pytest.warns(FutureWarning, match=name),
        pytest.raises(
            module.VectorStoreConfigurationError,
            match=f"VECTOR_STORE_URL is required when VECTOR_STORE_PROVIDER={provider}",
        ),
    ):
        module.resolve_vector_store_config()


def test_ambiguous_legacy_backend_signals_fail(monkeypatch: MonkeyPatch) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("DENSE_PGVECTOR_CONNECTION", "postgresql://db.example/rag")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")

    with pytest.raises(module.VectorStoreConfigurationError, match="conflict"):
        module.resolve_vector_store_config()


def test_resolver_loads_local_environment(monkeypatch: MonkeyPatch) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    calls: list[None] = []
    monkeypatch.setattr(module, "load_local_env", lambda: calls.append(None))

    module.resolve_vector_store_config()

    assert calls == [None]


def test_config_is_strict_frozen_and_hides_api_key() -> None:
    module = _config_module()
    config = module.VectorStoreConfig(
        provider="qdrant",
        collection="chunks",
        url="https://qdrant.example.test",
        api_key="top-secret",
    )

    assert "top-secret" not in repr(config)
    assert config.api_key.get_secret_value() == "top-secret"

    with pytest.raises(ValidationError):
        module.VectorStoreConfig.model_validate(
            {
                "provider": "turbovec",
                "collection": "chunks",
                "unexpected": True,
            }
        )

    with pytest.raises(ValidationError):
        config.provider = "turbovec"


def test_config_hides_url_credentials_in_representations() -> None:
    module = _config_module()
    raw_url = "postgresql://user:top-secret@db.example/rag"
    config = module.VectorStoreConfig(
        provider="pgvector",
        collection="chunks",
        url=raw_url,
    )

    assert config.url is not None
    assert config.url.get_secret_value() == raw_url
    assert "top-secret" not in repr(config)
    assert "top-secret" not in str(config.model_dump())
    assert "top-secret" not in config.model_dump_json()
    assert config.model_dump_json() == (
        '{"provider":"pgvector","collection":"chunks","url":"**********","api_key":null}'
    )


@pytest.mark.parametrize("provider", ["TURBOVEC", "postgres", "postgresql", "unknown"])
def test_canonical_provider_accepts_only_exact_supported_names(
    monkeypatch: MonkeyPatch,
    provider: str,
) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", provider)

    with pytest.raises(module.VectorStoreConfigurationError, match="VECTOR_STORE_PROVIDER"):
        module.resolve_vector_store_config()


def test_blank_canonical_values_are_unset(monkeypatch: MonkeyPatch) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "  ")
    monkeypatch.setenv("VECTOR_STORE_URL", " ")
    monkeypatch.setenv("VECTOR_STORE_API_KEY", "\t")
    monkeypatch.setenv("VECTOR_STORE_COLLECTION", "")

    config = module.resolve_vector_store_config()

    assert config.provider == "turbovec"
    assert config.collection == "agentic_rag_chunks"
    assert config.url is None
    assert config.api_key is None


@pytest.mark.parametrize("url", ["postgresql://db.example/rag", "postgres://db.example/rag"])
def test_pgvector_accepts_postgresql_compatible_url(
    monkeypatch: MonkeyPatch,
    url: str,
) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "pgvector")
    monkeypatch.setenv("VECTOR_STORE_URL", url)
    monkeypatch.setenv("VECTOR_STORE_COLLECTION", "custom_chunks")

    config = module.resolve_vector_store_config()

    assert config.provider == "pgvector"
    assert config.url is not None
    assert config.url.get_secret_value() == url
    assert config.collection == "custom_chunks"


def test_pgvector_uses_unified_default_collection(monkeypatch: MonkeyPatch) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "pgvector")
    monkeypatch.setenv("VECTOR_STORE_URL", "postgresql://db.example/rag")

    config = module.resolve_vector_store_config()

    assert config.provider == "pgvector"
    assert config.collection == "agentic_rag_chunks"


def test_pgvector_requires_url(monkeypatch: MonkeyPatch) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "pgvector")

    with pytest.raises(module.VectorStoreConfigurationError, match="VECTOR_STORE_URL"):
        module.resolve_vector_store_config()


@pytest.mark.parametrize("url", ["https://db.example/rag", "sqlite:///rag.db", "not-a-url"])
def test_pgvector_rejects_non_postgresql_url(
    monkeypatch: MonkeyPatch,
    url: str,
) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "pgvector")
    monkeypatch.setenv("VECTOR_STORE_URL", url)

    with pytest.raises(module.VectorStoreConfigurationError, match="PostgreSQL"):
        module.resolve_vector_store_config()


def test_pgvector_normalizes_url_parser_failure(monkeypatch: MonkeyPatch) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "pgvector")
    monkeypatch.setenv("VECTOR_STORE_URL", "postgresql://[::1")

    with pytest.raises(
        module.VectorStoreConfigurationError,
        match="VECTOR_STORE_URL is invalid for pgvector",
    ):
        module.resolve_vector_store_config()


def test_pgvector_rejects_api_key(monkeypatch: MonkeyPatch) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "pgvector")
    monkeypatch.setenv("VECTOR_STORE_URL", "postgresql://db.example/rag")
    monkeypatch.setenv("VECTOR_STORE_API_KEY", "unexpected")

    with pytest.raises(module.VectorStoreConfigurationError, match="VECTOR_STORE_API_KEY"):
        module.resolve_vector_store_config()


@pytest.mark.parametrize("url", ["https://qdrant.example.test", "http://localhost:6333"])
def test_qdrant_accepts_http_url_and_optional_api_key(
    monkeypatch: MonkeyPatch,
    url: str,
) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", url)
    monkeypatch.setenv("VECTOR_STORE_API_KEY", "secret")

    config = module.resolve_vector_store_config()

    assert config.provider == "qdrant"
    assert config.url is not None
    assert config.url.get_secret_value() == url
    assert config.api_key.get_secret_value() == "secret"


def test_qdrant_accepts_http_url_without_api_key(monkeypatch: MonkeyPatch) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")

    config = module.resolve_vector_store_config()

    assert config.provider == "qdrant"
    assert config.url is not None
    assert config.url.get_secret_value() == "https://qdrant.example.test"
    assert config.api_key is None


def test_qdrant_requires_url(monkeypatch: MonkeyPatch) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")

    with pytest.raises(module.VectorStoreConfigurationError, match="VECTOR_STORE_URL"):
        module.resolve_vector_store_config()


@pytest.mark.parametrize("url", ["postgresql://db.example/rag", "grpc://qdrant:6334", "qdrant"])
def test_qdrant_rejects_non_http_url(monkeypatch: MonkeyPatch, url: str) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", url)

    with pytest.raises(module.VectorStoreConfigurationError, match=r"HTTP\(S\)"):
        module.resolve_vector_store_config()


def test_qdrant_normalizes_url_parser_failure(monkeypatch: MonkeyPatch) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "http://[::1")

    with pytest.raises(
        module.VectorStoreConfigurationError,
        match="VECTOR_STORE_URL is invalid for qdrant",
    ):
        module.resolve_vector_store_config()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("VECTOR_STORE_URL", "https://unexpected.example.test"),
        ("VECTOR_STORE_API_KEY", "unexpected"),
    ],
)
def test_turbovec_rejects_remote_connection_fields(
    monkeypatch: MonkeyPatch,
    name: str,
    value: str,
) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv(name, value)

    with pytest.raises(module.VectorStoreConfigurationError, match=name):
        module.resolve_vector_store_config()


@pytest.mark.parametrize("legacy_provider", ["pgvector", "postgres", "postgresql"])
def test_legacy_pgvector_provider_aliases_normalize_and_warn(
    monkeypatch: MonkeyPatch,
    legacy_provider: str,
) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("DENSE_VECTOR_STORE", legacy_provider)
    monkeypatch.setenv("DENSE_PGVECTOR_CONNECTION", "postgresql://db.example/rag")
    monkeypatch.setenv("DENSE_PGVECTOR_COLLECTION", "legacy_chunks")

    with pytest.warns(FutureWarning) as warnings:
        config = module.resolve_vector_store_config()

    assert config.provider == "pgvector"
    assert config.url is not None
    assert config.url.get_secret_value() == "postgresql://db.example/rag"
    assert config.collection == "legacy_chunks"
    assert {warning.filename for warning in warnings} == {__file__}


def test_legacy_qdrant_configuration_warns_and_resolves(
    monkeypatch: MonkeyPatch,
) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("QDRANT_API_KEY", "legacy-secret")
    monkeypatch.setenv("QDRANT_COLLECTION", "legacy_chunks")

    with pytest.warns(FutureWarning):
        config = module.resolve_vector_store_config()

    assert config.provider == "qdrant"
    assert config.url is not None
    assert config.url.get_secret_value() == "https://qdrant.example.test"
    assert config.api_key.get_secret_value() == "legacy-secret"
    assert config.collection == "legacy_chunks"


def test_matching_canonical_and_relevant_legacy_values_do_not_warn(
    monkeypatch: MonkeyPatch,
) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "pgvector")
    monkeypatch.setenv("VECTOR_STORE_URL", " postgresql://db.example/rag ")
    monkeypatch.setenv("VECTOR_STORE_COLLECTION", " chunks ")
    monkeypatch.setenv("DENSE_VECTOR_STORE", "postgres")
    monkeypatch.setenv("DENSE_PGVECTOR_CONNECTION", "postgresql://db.example/rag")
    monkeypatch.setenv("DENSE_PGVECTOR_COLLECTION", "chunks")

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        config = module.resolve_vector_store_config()

    assert config.provider == "pgvector"
    assert config.url is not None
    assert config.url.get_secret_value() == "postgresql://db.example/rag"
    assert config.collection == "chunks"
    assert not caught_warnings


@pytest.mark.parametrize(
    ("canonical_name", "canonical_value", "legacy_name", "legacy_value"),
    [
        ("VECTOR_STORE_PROVIDER", "qdrant", "DENSE_VECTOR_STORE", "pgvector"),
        (
            "VECTOR_STORE_URL",
            "https://one.example.test",
            "QDRANT_URL",
            "https://two.example.test",
        ),
        ("VECTOR_STORE_API_KEY", "one", "QDRANT_API_KEY", "two"),
        ("VECTOR_STORE_COLLECTION", "one", "QDRANT_COLLECTION", "two"),
    ],
)
def test_conflicting_canonical_and_relevant_legacy_values_fail(
    monkeypatch: MonkeyPatch,
    canonical_name: str,
    canonical_value: str,
    legacy_name: str,
    legacy_value: str,
) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://one.example.test")
    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://one.example.test")
    monkeypatch.setenv(canonical_name, canonical_value)
    monkeypatch.setenv(legacy_name, legacy_value)

    with pytest.raises(module.VectorStoreConfigurationError, match="conflict"):
        module.resolve_vector_store_config()


def test_unrelated_legacy_backend_values_are_ignored(monkeypatch: MonkeyPatch) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "pgvector")
    monkeypatch.setenv("VECTOR_STORE_URL", "postgresql://db.example/rag")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("QDRANT_API_KEY", "unused")
    monkeypatch.setenv("QDRANT_COLLECTION", "unused")

    config = module.resolve_vector_store_config()

    assert config.provider == "pgvector"
    assert config.url is not None
    assert config.url.get_secret_value() == "postgresql://db.example/rag"
    assert config.api_key is None
    assert config.collection == "agentic_rag_chunks"


def test_blank_legacy_values_are_unset_without_warning(monkeypatch: MonkeyPatch) -> None:
    module = _config_module()
    _clear_vector_store_env(monkeypatch, module)
    monkeypatch.setenv("DENSE_VECTOR_STORE", " ")
    monkeypatch.setenv("DENSE_PGVECTOR_CONNECTION", "")
    monkeypatch.setenv("QDRANT_URL", "\t")

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        config = module.resolve_vector_store_config()

    assert config.provider == "turbovec"
    assert not caught_warnings
