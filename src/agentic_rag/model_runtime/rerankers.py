"""Reranker adapters and local preload helpers."""

from __future__ import annotations

import contextlib
import importlib
from collections.abc import Callable, Iterable
from functools import lru_cache
from typing import Any, Protocol, cast

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import RerankInput, RerankOutput, SearchResult
from agentic_rag.model_runtime.config import RerankerConfig
from agentic_rag.model_runtime.errors import (
    ModelInvocationError,
    ModelRuntimeConfigurationError,
)
from agentic_rag.retrieval.thresholds import deduplicate_by_best_rank


class _CrossEncoderModel(Protocol):
    def predict(self, sentences: list[tuple[str, str]]) -> object:
        """Return relevance scores for query/document pairs."""


class ScoreReranker(BaseModel):
    """Deterministic score-based fallback reranker."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    def rerank(self, request: RerankInput) -> RerankOutput:
        """Sort deduplicated candidates by score and reassign rerank ranks."""

        results = _score_based_rerank(request.candidates, top_k=request.top_k)
        return RerankOutput(
            results=results,
            metadata={
                "configured_provider": "score",
                "used_provider": "score",
                "method": "score_based_sort",
            },
        )


class SentenceTransformersReranker(BaseModel):
    """Local cross-encoder reranker backed by sentence-transformers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    config: RerankerConfig
    device: str | None = None

    def rerank(self, request: RerankInput) -> RerankOutput:
        """Score `(query, document)` pairs and map scores back to candidates."""

        if request.top_k == 0 or not request.candidates:
            return RerankOutput(
                results=[],
                metadata=self._metadata(),
            )
        try:
            model = _load_cross_encoder(self.config.model_name, self.device)
        except (ModelRuntimeConfigurationError, ModelInvocationError):
            raise
        except Exception as exc:
            raise ModelInvocationError(f"Local reranker load failed: {exc}") from exc
        pairs = [(request.query, candidate.chunk.text) for candidate in request.candidates]
        try:
            scores = _coerce_scores(model.predict(pairs))
        except Exception as exc:
            raise ModelInvocationError(f"Local reranker invocation failed: {exc}") from exc
        if len(scores) != len(request.candidates):
            raise ModelInvocationError("Local reranker returned an unexpected number of scores.")
        return RerankOutput(
            results=_rank_by_scores(request.candidates, scores, top_k=request.top_k),
            metadata=self._metadata(),
        )

    def _metadata(self) -> dict[str, object]:
        return {
            "configured_provider": self.config.provider,
            "used_provider": "sentence_transformers",
            "model": self.config.model_name,
            "device": self.device or "auto",
            "library": "sentence-transformers",
        }


class LiteLLMReranker(BaseModel):
    """API reranker backed by LiteLLM."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    config: RerankerConfig

    def rerank(self, request: RerankInput) -> RerankOutput:
        """Call LiteLLM rerank and map result indices to candidates."""

        if request.top_k == 0 or not request.candidates:
            return RerankOutput(results=[], metadata=self._metadata())
        try:
            litellm = importlib.import_module("litellm")
            response = litellm.rerank(**self._rerank_kwargs(request))
            indexed_scores = _extract_litellm_rerank_results(
                response,
                candidate_count=len(request.candidates),
            )
        except ModelInvocationError:
            raise
        except Exception as exc:
            raise ModelInvocationError(f"Reranker invocation failed: {exc}") from exc

        results = [
            SearchResult(
                chunk=request.candidates[index].chunk,
                score=score,
                rank=rank,
                retriever="rerank",
            )
            for rank, (index, score) in enumerate(indexed_scores[: request.top_k], start=1)
        ]
        return RerankOutput(results=results, metadata=self._metadata())

    def _rerank_kwargs(self, request: RerankInput) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "model": self._model_name(),
            "query": request.query,
            "documents": [candidate.chunk.text for candidate in request.candidates],
            "top_n": request.top_k,
            "timeout": self.config.timeout_seconds,
        }
        if self.config.api_base is not None:
            kwargs["api_base"] = self.config.api_base
        if self.config.api_key is not None:
            kwargs["api_key"] = self.config.api_key
        if self.config.provider == "local":
            kwargs["custom_llm_provider"] = "hosted_vllm"
        return kwargs

    def _model_name(self) -> str:
        model_name = self.config.model_name
        if self.config.provider == "local":
            return model_name
        prefix = f"{self.config.provider}/"
        if model_name.startswith(prefix):
            return model_name
        return f"{prefix}{model_name}"

    def _metadata(self) -> dict[str, object]:
        return {
            "configured_provider": self.config.provider,
            "used_provider": self.config.provider,
            "model": self._model_name(),
            "library": "litellm",
        }


def preload_local_reranker(config: RerankerConfig) -> dict[str, object]:
    """Preload a local sentence-transformers reranker when configured."""

    metadata: dict[str, object] = {
        "preload": config.preload,
        "configured_provider": config.provider,
    }
    if not config.preload:
        metadata["status"] = "disabled"
        return metadata
    if config.provider != "sentence_transformers":
        metadata["status"] = "skipped"
        metadata["reason"] = "provider_not_sentence_transformers"
        return metadata
    metadata["model"] = config.model_name
    metadata["device"] = config.device or "auto"
    metadata["library"] = "sentence-transformers"
    try:
        _load_cross_encoder(config.model_name, config.device)
    except (ModelRuntimeConfigurationError, ModelInvocationError, Exception) as exc:
        metadata["status"] = "failed"
        metadata["fallback_provider"] = "score"
        metadata["fallback_reason"] = f"{type(exc).__name__}: {exc}"
        return metadata
    metadata["status"] = "loaded"
    metadata["used_provider"] = "sentence_transformers"
    return metadata


def _score_based_rerank(candidates: list[SearchResult], *, top_k: int) -> list[SearchResult]:
    unique_candidates = list(deduplicate_by_best_rank(candidates).values())
    ranked_candidates = sorted(
        unique_candidates,
        key=lambda candidate: (
            -candidate.score,
            candidate.rank,
            candidate.chunk.chunk_id,
        ),
    )
    return [
        SearchResult(
            chunk=candidate.chunk,
            score=candidate.score,
            rank=rank,
            retriever="rerank",
        )
        for rank, candidate in enumerate(ranked_candidates[:top_k], start=1)
    ]


def _rank_by_scores(
    candidates: list[SearchResult],
    scores: list[float],
    *,
    top_k: int,
) -> list[SearchResult]:
    scored_candidates = sorted(
        zip(candidates, scores, strict=True),
        key=lambda item: (
            -item[1],
            item[0].rank,
            item[0].chunk.chunk_id,
        ),
    )
    return [
        SearchResult(
            chunk=candidate.chunk,
            score=score,
            rank=rank,
            retriever="rerank",
        )
        for rank, (candidate, score) in enumerate(scored_candidates[:top_k], start=1)
    ]


def _preimport_sklearn_before_torch() -> None:
    """Nạp scikit-learn TRƯỚC khi torch/sentence-transformers load.

    Trên Windows, nếu torch nạp trước rồi sentence-transformers mới kéo
    scikit-learn vào sau, xảy ra xung đột DLL native → access violation
    (exit 0xC0000005) crash cả tiến trình. Nạp sklearn sớm để cố định thứ tự.
    Đây là chokepoint torch đầu tiên của server (embedding dùng API, không nạp torch).
    """
    # sklearn đi kèm sentence-transformers — nếu chưa có thì import dưới sẽ báo lỗi rõ.
    with contextlib.suppress(ImportError):
        importlib.import_module("sklearn")


@lru_cache(maxsize=8)
def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _resolve_device(
    device: str | None, *, cuda_available: Callable[[], bool] = _cuda_available
) -> str | None:
    """Downgrade a requested CUDA device to CPU when CUDA is unavailable.

    Honors any non-CUDA device as-is. A machine with CPU-only torch (or no GPU)
    would otherwise raise "Torch not compiled with CUDA enabled"; falling back to
    CPU keeps the reranker working (slower) instead of failing every request.
    """
    if not device or not str(device).lower().startswith("cuda"):
        return device
    if cuda_available():
        return device
    import warnings

    warnings.warn(
        f"RERANK_DEVICE={device!r} requested but CUDA is unavailable; using CPU.",
        stacklevel=2,
    )
    return "cpu"


def _load_cross_encoder(model_name: str, device: str | None) -> _CrossEncoderModel:
    _preimport_sklearn_before_torch()
    try:
        sentence_transformers = importlib.import_module("sentence_transformers")
    except ImportError as exc:
        raise ModelRuntimeConfigurationError(
            "Local rerankers require sentence-transformers. Run `uv sync --extra local-models`."
        ) from exc
    cross_encoder = sentence_transformers.CrossEncoder
    try:
        return cast(_CrossEncoderModel, cross_encoder(model_name, device=_resolve_device(device)))
    except Exception as exc:
        raise ModelInvocationError(f"Local reranker load failed: {exc}") from exc


def _coerce_scores(raw_scores: object) -> list[float]:
    if hasattr(raw_scores, "tolist"):
        raw_scores = raw_scores.tolist()
    if not isinstance(raw_scores, Iterable) or isinstance(raw_scores, str | bytes):
        raise ValueError("Reranker scores must be an iterable of numbers.")
    return [float(score) for score in raw_scores]


def _extract_litellm_rerank_results(
    response: object,
    *,
    candidate_count: int,
) -> list[tuple[int, float]]:
    raw_results = _get(response, "results")
    if not isinstance(raw_results, list):
        raise ModelInvocationError("Reranker response must contain a results list.")

    seen_indices: set[int] = set()
    indexed_scores: list[tuple[int, float]] = []
    for raw_result in raw_results:
        raw_index = _get(raw_result, "index")
        raw_score = _get(raw_result, "relevance_score")
        if raw_score is None:
            raw_score = _get(raw_result, "score")
        if not isinstance(raw_index, int):
            raise ModelInvocationError("Reranker result index must be an integer.")
        if raw_index < 0 or raw_index >= candidate_count:
            raise ModelInvocationError("Reranker result index is out of range.")
        if raw_index in seen_indices:
            raise ModelInvocationError("Reranker returned duplicate result indices.")
        if raw_score is None:
            raise ModelInvocationError("Reranker result is missing a relevance score.")
        seen_indices.add(raw_index)
        indexed_scores.append((raw_index, float(raw_score)))
    return indexed_scores


def _get(value: object, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
