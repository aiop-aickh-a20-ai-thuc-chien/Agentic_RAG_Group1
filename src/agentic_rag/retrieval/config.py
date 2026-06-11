"""Strict vector-store configuration resolved from environment variables."""

from __future__ import annotations

import os
import warnings
from typing import Final, Literal, cast
from urllib.parse import SplitResult, urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from agentic_rag.runtime_env import load_local_env

VectorStoreProvider = Literal["turbovec", "pgvector", "qdrant"]

DEFAULT_VECTOR_STORE_COLLECTION: Final[str] = "agentic_rag_chunks"
_CANONICAL_PROVIDERS: Final[frozenset[str]] = frozenset({"turbovec", "pgvector", "qdrant"})
_LEGACY_PROVIDER_ALIASES: Final[dict[str, VectorStoreProvider]] = {
    "turbovec": "turbovec",
    "pgvector": "pgvector",
    "postgres": "pgvector",
    "postgresql": "pgvector",
    "qdrant": "qdrant",
}
_LEGACY_BACKEND_SIGNALS: Final[dict[VectorStoreProvider, tuple[str, ...]]] = {
    "pgvector": (
        "DENSE_PGVECTOR_CONNECTION",
        "DENSE_PGVECTOR_COLLECTION",
    ),
    "qdrant": (
        "QDRANT_URL",
        "QDRANT_API_KEY",
        "QDRANT_COLLECTION",
    ),
    "turbovec": (),
}


class VectorStoreConfigurationError(ValueError):
    """Raised when vector-store environment variables are inconsistent."""


class VectorStoreConfig(BaseModel):
    """Resolved immutable vector-store configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    provider: VectorStoreProvider = "turbovec"
    collection: str = DEFAULT_VECTOR_STORE_COLLECTION
    url: SecretStr | None = Field(default=None, repr=False)
    api_key: SecretStr | None = Field(default=None, repr=False)


def resolve_vector_store_config() -> VectorStoreConfig:
    """Resolve and validate vector-store configuration from local environment."""

    load_local_env()
    provider = _resolve_provider()
    legacy_url_name, legacy_api_key_name, legacy_collection_name = _legacy_names(provider)
    url = _resolve_value("VECTOR_STORE_URL", legacy_url_name)
    api_key = _resolve_value("VECTOR_STORE_API_KEY", legacy_api_key_name)
    collection = (
        _resolve_value(
            "VECTOR_STORE_COLLECTION",
            legacy_collection_name,
        )
        or DEFAULT_VECTOR_STORE_COLLECTION
    )

    _validate_provider_fields(provider=provider, url=url, api_key=api_key)
    return VectorStoreConfig(
        provider=provider,
        collection=collection,
        url=SecretStr(url) if url is not None else None,
        api_key=SecretStr(api_key) if api_key is not None else None,
    )


def require_qdrant_vector_store_config() -> VectorStoreConfig:
    """Resolve vector-store config and require a configured Qdrant backend."""

    config = resolve_vector_store_config()
    if config.provider != "qdrant" or config.url is None:
        raise VectorStoreConfigurationError(
            "VECTOR_STORE_PROVIDER=qdrant with VECTOR_STORE_URL is required."
        )
    return config


def _resolve_provider() -> VectorStoreProvider:
    canonical = _env_value("VECTOR_STORE_PROVIDER")
    legacy = _env_value("DENSE_VECTOR_STORE")

    if canonical is not None and canonical not in _CANONICAL_PROVIDERS:
        supported = ", ".join(sorted(_CANONICAL_PROVIDERS))
        raise VectorStoreConfigurationError(f"VECTOR_STORE_PROVIDER must be one of: {supported}.")

    normalized_legacy = _normalize_legacy_provider(legacy) if legacy is not None else None
    if canonical is not None and normalized_legacy is not None:
        if canonical != normalized_legacy:
            raise VectorStoreConfigurationError(
                "Configuration conflict: VECTOR_STORE_PROVIDER and "
                "DENSE_VECTOR_STORE select different providers."
            )
        return canonical

    if canonical is not None:
        return cast(VectorStoreProvider, canonical)
    if normalized_legacy is not None:
        _warn_legacy("DENSE_VECTOR_STORE", "VECTOR_STORE_PROVIDER")
        return normalized_legacy
    return _infer_provider_from_legacy_fields()


def _infer_provider_from_legacy_fields() -> VectorStoreProvider:
    signals = {
        provider: tuple(name for name in names if _env_value(name) is not None)
        for provider, names in _LEGACY_BACKEND_SIGNALS.items()
    }
    signaled_providers = [provider for provider, names in signals.items() if names]
    if len(signaled_providers) > 1:
        raise VectorStoreConfigurationError(
            "Configuration conflict: legacy pgvector and Qdrant variables are both set; "
            "set VECTOR_STORE_PROVIDER explicitly."
        )
    if signaled_providers:
        provider = signaled_providers[0]
        _warn_legacy_provider_inference(signals[provider])
        return provider
    return "turbovec"


def _normalize_legacy_provider(value: str) -> VectorStoreProvider:
    normalized = _LEGACY_PROVIDER_ALIASES.get(value.lower())
    if normalized is None:
        supported = ", ".join(sorted(_LEGACY_PROVIDER_ALIASES))
        raise VectorStoreConfigurationError(f"DENSE_VECTOR_STORE must be one of: {supported}.")
    return normalized


def _legacy_names(
    provider: VectorStoreProvider,
) -> tuple[str | None, str | None, str | None]:
    if provider == "pgvector":
        return (
            "DENSE_PGVECTOR_CONNECTION",
            None,
            "DENSE_PGVECTOR_COLLECTION",
        )
    if provider == "qdrant":
        return "QDRANT_URL", "QDRANT_API_KEY", "QDRANT_COLLECTION"
    return None, None, None


def _resolve_value(canonical_name: str, legacy_name: str | None) -> str | None:
    canonical = _env_value(canonical_name)
    legacy = _env_value(legacy_name) if legacy_name is not None else None

    if canonical is not None and legacy is not None:
        if canonical != legacy:
            raise VectorStoreConfigurationError(
                f"Configuration conflict: {canonical_name} and {legacy_name} differ."
            )
        return canonical
    if canonical is not None:
        return canonical
    if legacy is not None:
        assert legacy_name is not None
        _warn_legacy(legacy_name, canonical_name)
        return legacy
    return None


def _validate_provider_fields(
    *,
    provider: VectorStoreProvider,
    url: str | None,
    api_key: str | None,
) -> None:
    if provider == "turbovec":
        if url is not None:
            raise VectorStoreConfigurationError(
                "VECTOR_STORE_URL is not supported when VECTOR_STORE_PROVIDER=turbovec."
            )
        if api_key is not None:
            raise VectorStoreConfigurationError(
                "VECTOR_STORE_API_KEY is not supported when VECTOR_STORE_PROVIDER=turbovec."
            )
        return

    if url is None:
        raise VectorStoreConfigurationError(
            f"VECTOR_STORE_URL is required when VECTOR_STORE_PROVIDER={provider}."
        )

    parsed_url = _parse_url(url, provider)
    scheme = parsed_url.scheme.lower()
    if provider == "pgvector":
        base_scheme = scheme.split("+", 1)[0]
        if base_scheme not in {"postgres", "postgresql"}:
            raise VectorStoreConfigurationError(
                "VECTOR_STORE_URL must be a PostgreSQL-compatible URL for pgvector."
            )
        if api_key is not None:
            raise VectorStoreConfigurationError(
                "VECTOR_STORE_API_KEY is not supported when VECTOR_STORE_PROVIDER=pgvector."
            )
        return

    if parsed_url.scheme.lower() not in {"http", "https"} or not parsed_url.netloc:
        raise VectorStoreConfigurationError("VECTOR_STORE_URL must be an HTTP(S) URL for qdrant.")


def _parse_url(url: str, provider: VectorStoreProvider) -> SplitResult:
    try:
        return urlsplit(url)
    except ValueError as exc:
        raise VectorStoreConfigurationError(f"VECTOR_STORE_URL is invalid for {provider}.") from exc


def _env_value(name: str | None) -> str | None:
    if name is None:
        return None
    raw_value = os.getenv(name)
    if raw_value is None:
        return None
    value = raw_value.strip()
    return value or None


def _warn_legacy(legacy_name: str, canonical_name: str) -> None:
    warnings.warn(
        f"{legacy_name} is deprecated; use {canonical_name} instead.",
        FutureWarning,
        stacklevel=4,
    )


def _warn_legacy_provider_inference(names: tuple[str, ...]) -> None:
    warnings.warn(
        f"{', '.join(names)} implicitly selects a vector-store provider; "
        "set VECTOR_STORE_PROVIDER explicitly.",
        FutureWarning,
        stacklevel=4,
    )
