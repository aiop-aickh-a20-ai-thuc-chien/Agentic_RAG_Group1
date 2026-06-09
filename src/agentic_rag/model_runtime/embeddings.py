"""Embedding adapters for LiteLLM and local sentence-transformers models."""

from __future__ import annotations

import importlib
from collections.abc import Iterable
from functools import lru_cache
from typing import Any, Protocol, cast

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import EmbeddingInput, EmbeddingOutput
from agentic_rag.core.ports import EmbeddingClient
from agentic_rag.model_runtime.config import EmbeddingConfig
from agentic_rag.model_runtime.errors import (
    ModelInvocationError,
    ModelRuntimeConfigurationError,
)


class _SentenceTransformerModel(Protocol):
    def encode(self, texts: list[str], **kwargs: object) -> object:
        """Encode texts into dense vectors."""


class LiteLLMEmbeddingClient(BaseModel):
    """Embedding client backed by LiteLLM."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    config: EmbeddingConfig

    def embed(self, request: EmbeddingInput) -> EmbeddingOutput:
        """Return normalized embeddings for the input texts."""

        try:
            litellm = importlib.import_module("litellm")
            response = litellm.embedding(**self._embedding_kwargs(request))
        except Exception as exc:
            raise ModelInvocationError(f"Embedding invocation failed: {exc}") from exc

        vectors = _extract_litellm_vectors(response)
        return validate_embedding_output(
            vectors,
            config=self.config,
            input_count=len(request.texts),
            model_name=self._model_name(),
        )

    def _embedding_kwargs(self, request: EmbeddingInput) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "model": self._model_name(),
            "input": request.texts,
            "timeout": self.config.timeout_seconds,
        }
        if self.config.api_base is not None:
            kwargs["api_base"] = self.config.api_base
        if self.config.api_key is not None:
            kwargs["api_key"] = self.config.api_key
        if self.config.expected_dimensions is not None:
            kwargs["dimensions"] = self.config.expected_dimensions
        return kwargs

    def _model_name(self) -> str:
        provider = "openai" if self.config.provider == "local" else self.config.provider
        prefix = f"{provider}/"
        if self.config.model.startswith(prefix):
            return self.config.model
        return f"{prefix}{self.config.model}"


class HuggingFaceEmbeddingClient(BaseModel):
    """Embedding client backed by local sentence-transformers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    config: EmbeddingConfig
    device: str | None = None

    def embed(self, request: EmbeddingInput) -> EmbeddingOutput:
        """Return normalized embeddings from a cached local model."""

        model = _load_sentence_transformer(self.config.model, self.device)
        try:
            raw_vectors = model.encode(
                request.texts,
                convert_to_numpy=False,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise ModelInvocationError(f"Local embedding invocation failed: {exc}") from exc

        return validate_embedding_output(
            _coerce_vectors(raw_vectors),
            config=self.config,
            input_count=len(request.texts),
            model_name=self.config.model,
        )


class EmbeddingCompatibilityAdapter(BaseModel):
    """LangChain-style compatibility wrapper around the typed embedding client."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    client: EmbeddingClient

    def embed_query(self, text: str) -> list[float]:
        """Return one plain vector for vector-store query APIs."""

        return self.client.embed(EmbeddingInput(texts=[text])).vectors[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return plain vectors for vector-store document APIs."""

        return self.client.embed(EmbeddingInput(texts=texts)).vectors


def validate_embedding_output(
    vectors: list[list[float]],
    *,
    config: EmbeddingConfig,
    input_count: int,
    model_name: str,
) -> EmbeddingOutput:
    """Validate provider vectors and return the normalized embedding output."""

    if not vectors:
        raise ValueError("Embedding provider returned no vectors.")
    if len(vectors) != input_count:
        raise ValueError(
            f"Embedding provider returned {len(vectors)} vectors for {input_count} inputs."
        )
    dimensions = len(vectors[0])
    if dimensions == 0:
        raise ValueError("Embedding provider returned an empty vector.")
    if any(len(vector) != dimensions for vector in vectors):
        raise ValueError("Embedding provider returned inconsistent dimensions.")
    if config.expected_dimensions is not None and dimensions != config.expected_dimensions:
        raise ValueError(
            "Embedding dimension mismatch: "
            f"expected {config.expected_dimensions}, received {dimensions}."
        )
    return EmbeddingOutput(
        vectors=vectors,
        provider=config.provider,
        model=model_name,
        dimensions=dimensions,
    )


@lru_cache(maxsize=8)
def _load_sentence_transformer(
    model_name: str,
    device: str | None,
) -> _SentenceTransformerModel:
    try:
        sentence_transformers = importlib.import_module("sentence_transformers")
    except ImportError as exc:
        raise ModelRuntimeConfigurationError(
            "Local embedding models require sentence-transformers. "
            "Run `uv sync --extra local-models`."
        ) from exc
    sentence_transformer = sentence_transformers.SentenceTransformer
    return cast(_SentenceTransformerModel, sentence_transformer(model_name, device=device))


def _extract_litellm_vectors(response: object) -> list[list[float]]:
    data = _get(response, "data")
    if not isinstance(data, list):
        raise ValueError("Embedding provider response must contain a data list.")
    vectors: list[list[float]] = []
    for item in data:
        vectors.append(_coerce_vector(_get(item, "embedding")))
    return vectors


def _coerce_vectors(raw_vectors: object) -> list[list[float]]:
    if hasattr(raw_vectors, "tolist"):
        raw_vectors = raw_vectors.tolist()
    if not isinstance(raw_vectors, Iterable) or isinstance(raw_vectors, str | bytes):
        raise ValueError("Embedding vectors must be an iterable of vectors.")
    return [_coerce_vector(vector) for vector in raw_vectors]


def _coerce_vector(raw_vector: object) -> list[float]:
    if hasattr(raw_vector, "tolist"):
        raw_vector = raw_vector.tolist()
    if not isinstance(raw_vector, Iterable) or isinstance(raw_vector, str | bytes):
        raise ValueError("Embedding vector must be an iterable of numbers.")
    return [float(value) for value in raw_vector]


def _get(value: object, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
