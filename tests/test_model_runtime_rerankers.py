from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest
from pytest import MonkeyPatch

from agentic_rag.core.contracts import Chunk, RerankInput, SearchResult
from agentic_rag.model_runtime.config import RerankerConfig
from agentic_rag.model_runtime.errors import (
    ModelInvocationError,
    ModelRuntimeConfigurationError,
)
from agentic_rag.model_runtime.rerankers import (
    ListwiseLLMReranker,
    LiteLLMReranker,
    ScoreReranker,
    SentenceTransformersReranker,
    preload_local_reranker,
)


def _chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(chunk_id=chunk_id, text=text, metadata={"source": "doc.pdf"})


def _result(chunk_id: str, score: float, rank: int, text: str | None = None) -> SearchResult:
    return SearchResult(
        chunk=_chunk(chunk_id, text or chunk_id),
        score=score,
        rank=rank,
        retriever="hybrid",
    )


def _request(candidates: list[SearchResult], top_k: int = 5) -> RerankInput:
    return RerankInput(query="warranty question", candidates=candidates, top_k=top_k)


def _config(
    *,
    provider: str = "cohere",
    model: str | None = "rerank-v3.5",
    api_base: str | None = None,
    api_key: str | None = None,
) -> RerankerConfig:
    return RerankerConfig(
        provider=provider,
        model=model,
        api_base=api_base,
        api_key=api_key,
        timeout_seconds=7.0,
    )


def test_score_reranker_preserves_current_fallback_ordering_and_dedup() -> None:
    candidates = [
        _result("chunk-a", score=0.5, rank=3),
        _result("chunk-a", score=0.4, rank=1),
        _result("chunk-b", score=0.9, rank=2),
        _result("chunk-c", score=0.4, rank=4),
    ]

    output = ScoreReranker().rerank(_request(candidates, top_k=2))

    assert [result.chunk.chunk_id for result in output.results] == ["chunk-b", "chunk-a"]
    assert [result.rank for result in output.results] == [1, 2]
    assert [result.retriever for result in output.results] == ["rerank", "rerank"]
    assert output.results[1].score == 0.4
    assert output.metadata["used_provider"] == "score"
    assert output.metadata["method"] == "score_based_sort"


def test_sentence_transformers_reranker_maps_scores_to_candidates(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeCrossEncoder:
        def __init__(self, model_name: str, device: str | None = None) -> None:
            seen["model_name"] = model_name
            seen["device"] = device

        def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
            seen["pairs"] = pairs
            return [0.1, 0.95, 0.4]

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(CrossEncoder=FakeCrossEncoder),
    )
    candidates = [
        _result("chunk-a", score=0.9, rank=1, text="A"),
        _result("chunk-b", score=0.2, rank=2, text="B"),
        _result("chunk-c", score=0.4, rank=3, text="C"),
    ]
    reranker = SentenceTransformersReranker(
        config=_config(provider="sentence_transformers", model="test-reranker"),
        device="cuda",
    )

    output = reranker.rerank(_request(candidates, top_k=2))

    assert seen["model_name"] == "test-reranker"
    assert seen["device"] == "cuda"
    assert seen["pairs"] == [
        ("warranty question", "A"),
        ("warranty question", "B"),
        ("warranty question", "C"),
    ]
    assert [result.chunk.chunk_id for result in output.results] == ["chunk-b", "chunk-c"]
    assert [result.score for result in output.results] == [0.95, 0.4]
    assert output.metadata["used_provider"] == "sentence_transformers"


def test_litellm_reranker_passes_documents_and_top_n(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_rerank(**kwargs: Any) -> object:
        captured.update(kwargs)
        return {"results": [{"index": 1, "relevance_score": 0.91}]}

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(rerank=fake_rerank))
    candidates = [
        _result("chunk-a", score=0.2, rank=1, text="A"),
        _result("chunk-b", score=0.8, rank=2, text="B"),
    ]
    reranker = LiteLLMReranker(config=_config(api_base="https://example.test/v1", api_key="secret"))

    output = reranker.rerank(_request(candidates, top_k=1))

    assert captured["model"] == "cohere/rerank-v3.5"
    assert captured["query"] == "warranty question"
    assert captured["documents"] == ["A", "B"]
    assert captured["top_n"] == 1
    assert captured["api_base"] == "https://example.test/v1"
    assert captured["api_key"] == "secret"
    assert captured["timeout"] == 7.0
    assert "custom_llm_provider" not in captured
    assert [result.chunk.chunk_id for result in output.results] == ["chunk-b"]
    assert output.results[0].score == 0.91
    assert output.metadata["used_provider"] == "cohere"


def test_local_reranker_passes_explicit_hosted_vllm_provider(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_rerank(**kwargs: Any) -> object:
        captured.update(kwargs)
        return {"results": [{"index": 0, "relevance_score": 0.88}]}

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(rerank=fake_rerank))
    reranker = LiteLLMReranker(
        config=_config(
            provider="local",
            model="local-reranker",
            api_base="http://127.0.0.1:8001",
        )
    )

    output = reranker.rerank(_request([_result("chunk-a", 0.2, 1)], top_k=1))

    assert captured["model"] == "local-reranker"
    assert captured["custom_llm_provider"] == "hosted_vllm"
    assert captured["api_base"] == "http://127.0.0.1:8001"
    assert output.metadata["configured_provider"] == "local"
    assert output.metadata["used_provider"] == "local"
    assert output.metadata["model"] == "local-reranker"


@pytest.mark.parametrize(
    "response",
    [
        {"results": [{"index": 9, "relevance_score": 0.5}]},
        {"results": [{"index": 0, "relevance_score": 0.5}, {"index": 0, "relevance_score": 0.4}]},
        {"results": [{"index": 0}]},
    ],
)
def test_litellm_reranker_validates_result_indices_and_scores(
    monkeypatch: MonkeyPatch,
    response: object,
) -> None:
    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(rerank=lambda **_: response))
    reranker = LiteLLMReranker(config=_config())

    with pytest.raises(ModelInvocationError):
        reranker.rerank(_request([_result("chunk-a", 0.2, 1)], top_k=1))


def test_litellm_runtime_errors_are_normalized(monkeypatch: MonkeyPatch) -> None:
    def fake_rerank(**kwargs: Any) -> object:
        raise RuntimeError("provider failed")

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(rerank=fake_rerank))
    reranker = LiteLLMReranker(config=_config())

    with pytest.raises(ModelInvocationError, match="provider failed"):
        reranker.rerank(_request([_result("chunk-a", 0.2, 1)]))


def test_sentence_transformers_missing_extra_is_configuration_error(
    monkeypatch: MonkeyPatch,
) -> None:
    def fail_import(name: str) -> object:
        # sklearn được preimport trước (chống xung đột DLL) trong contextlib.suppress
        # (ImportError) — cho nó raise ImportError để bị nuốt, rồi sentence_transformers
        # raise ImportError mới là cái cần test.
        if name in {"sentence_transformers", "sklearn"}:
            raise ImportError(name)
        raise AssertionError(name)

    monkeypatch.setattr(
        "agentic_rag.model_runtime.rerankers.importlib.import_module",
        fail_import,
    )
    reranker = SentenceTransformersReranker(
        config=_config(provider="sentence_transformers", model="test-reranker")
    )

    with pytest.raises(ModelRuntimeConfigurationError, match="uv sync --extra local-models"):
        reranker.rerank(_request([_result("chunk-a", 0.2, 1)]))


def test_preload_local_reranker_statuses(monkeypatch: MonkeyPatch) -> None:
    assert (
        preload_local_reranker(RerankerConfig(provider="score", model=None, preload=False))[
            "status"
        ]
        == "disabled"
    )
    assert (
        preload_local_reranker(RerankerConfig(provider="cohere", model="rerank", preload=True))[
            "status"
        ]
        == "skipped"
    )

    class FakeCrossEncoder:
        def __init__(self, model_name: str, device: str | None = None) -> None:
            self.model_name = model_name
            self.device = device

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(CrossEncoder=FakeCrossEncoder),
    )
    loaded = preload_local_reranker(
        RerankerConfig(
            provider="sentence_transformers",
            model="test-reranker",
            preload=True,
            device="cpu",
        )
    )
    assert loaded["status"] == "loaded"

    def fail_import(name: str) -> object:
        if name == "sentence_transformers":
            raise ImportError(name)
        raise AssertionError(name)

    monkeypatch.setattr(
        "agentic_rag.model_runtime.rerankers.importlib.import_module",
        fail_import,
    )
    failed = preload_local_reranker(
        RerankerConfig(provider="sentence_transformers", model="other", preload=True)
    )
    assert failed["status"] == "failed"


class _FakeListwiseModel:
    def __init__(self, response: str) -> None:
        self._response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._response


def _listwise_config(model: str = "castorini/rankzephyr-7b-v1-full") -> RerankerConfig:
    return _config(provider="listwise_llm", model=model)


def test_listwise_llm_reranker_reorders_by_model_permutation(monkeypatch: MonkeyPatch) -> None:
    fake = _FakeListwiseModel("[2] > [3] > [1]")
    monkeypatch.setattr(
        "agentic_rag.model_runtime.rerankers._load_listwise_model",
        lambda model_name, device: fake,
    )
    candidates = [
        _result("chunk-a", 0.9, 1, text="alpha passage"),
        _result("chunk-b", 0.2, 2, text="bravo passage"),
        _result("chunk-c", 0.4, 3, text="charlie passage"),
    ]

    output = ListwiseLLMReranker(config=_listwise_config()).rerank(_request(candidates, top_k=3))

    assert [result.chunk.chunk_id for result in output.results] == ["chunk-b", "chunk-c", "chunk-a"]
    assert [result.rank for result in output.results] == [1, 2, 3]
    assert [result.score for result in output.results] == [3.0, 2.0, 1.0]
    assert [result.retriever for result in output.results] == ["rerank", "rerank", "rerank"]
    assert output.metadata["used_provider"] == "listwise_llm"
    assert output.metadata["model"] == "castorini/rankzephyr-7b-v1-full"
    assert "alpha passage" in fake.prompts[0]


def test_listwise_llm_reranker_keeps_all_candidates_on_unparseable_output(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentic_rag.model_runtime.rerankers._load_listwise_model",
        lambda model_name, device: _FakeListwiseModel("I cannot rank these passages."),
    )
    candidates = [
        _result("chunk-a", 0.9, 1),
        _result("chunk-b", 0.2, 2),
        _result("chunk-c", 0.4, 3),
    ]

    output = ListwiseLLMReranker(config=_listwise_config()).rerank(_request(candidates, top_k=3))

    assert [result.chunk.chunk_id for result in output.results] == [
        "chunk-a",
        "chunk-b",
        "chunk-c",
    ]


def test_listwise_llm_reranker_sliding_window_covers_all_candidates(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentic_rag.model_runtime.rerankers._load_listwise_model",
        lambda model_name, device: _FakeListwiseModel("[2] > [1]"),
    )
    candidates = [_result(name, 0.5, index + 1, text=name) for index, name in enumerate("abcd")]

    output = ListwiseLLMReranker(config=_listwise_config(), window_size=2, step=1).rerank(
        _request(candidates, top_k=4)
    )

    assert [result.chunk.chunk_id for result in output.results] == ["d", "a", "b", "c"]
    assert {result.chunk.chunk_id for result in output.results} == {"a", "b", "c", "d"}


def test_listwise_llm_reranker_runtime_errors_are_normalized(monkeypatch: MonkeyPatch) -> None:
    class _BoomModel:
        def generate(self, prompt: str) -> str:
            raise RuntimeError("model exploded")

    monkeypatch.setattr(
        "agentic_rag.model_runtime.rerankers._load_listwise_model",
        lambda model_name, device: _BoomModel(),
    )

    with pytest.raises(ModelInvocationError, match="model exploded"):
        ListwiseLLMReranker(config=_listwise_config()).rerank(
            _request([_result("chunk-a", 0.2, 1)], top_k=1)
        )


def test_listwise_llm_reranker_missing_extra_is_configuration_error(
    monkeypatch: MonkeyPatch,
) -> None:
    def fail_import(name: str) -> object:
        if name in {"transformers", "sklearn"}:
            raise ImportError(name)
        raise AssertionError(name)

    monkeypatch.setattr(
        "agentic_rag.model_runtime.rerankers.importlib.import_module",
        fail_import,
    )

    with pytest.raises(ModelRuntimeConfigurationError, match="uv sync --extra listwise-reranking"):
        ListwiseLLMReranker(config=_listwise_config()).rerank(
            _request([_result("chunk-a", 0.2, 1)], top_k=1)
        )
