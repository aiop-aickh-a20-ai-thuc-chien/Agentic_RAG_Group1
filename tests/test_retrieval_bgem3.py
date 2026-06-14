from __future__ import annotations

from typing import Any

from pytest import MonkeyPatch

from agentic_rag.retrieval.bgem3 import (
    clear_corpus_cache,
    encode_corpus,
    encode_query,
)


class _FakeBGEM3Model:
    """Records encode calls and returns deterministic sparse/colbert outputs."""

    def __init__(self) -> None:
        self.tokenizer = list(range(32))
        self.calls: list[dict[str, Any]] = []

    def encode(
        self,
        texts: list[str],
        return_dense: bool,
        return_sparse: bool,
        return_colbert_vecs: bool,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "texts": list(texts),
                "sparse": return_sparse,
                "colbert": return_colbert_vecs,
            }
        )
        output: dict[str, Any] = {}
        if return_sparse:
            output["lexical_weights"] = [{"1": 0.5} for _ in texts]
        if return_colbert_vecs:
            output["colbert_vecs"] = [[[0.1, 0.2]] for _ in texts]
        return output


def _install_fake_model(monkeypatch: MonkeyPatch) -> _FakeBGEM3Model:
    model = _FakeBGEM3Model()
    monkeypatch.setattr("agentic_rag.retrieval.bgem3._load_bgem3_model", lambda model_name: model)
    clear_corpus_cache()
    return model


def test_encode_corpus_single_pass_for_both_outputs(monkeypatch: MonkeyPatch) -> None:
    model = _install_fake_model(monkeypatch)
    texts = ["alpha", "bravo"]

    output = encode_corpus("BAAI/bge-m3", texts, want_sparse=True, want_colbert=True)

    assert "lexical_weights" in output
    assert "colbert_vecs" in output
    assert len(model.calls) == 1
    assert model.calls[0]["sparse"] is True
    assert model.calls[0]["colbert"] is True


def test_encode_corpus_reuses_cache_across_requests(monkeypatch: MonkeyPatch) -> None:
    model = _install_fake_model(monkeypatch)
    texts = ["alpha", "bravo"]

    encode_corpus("BAAI/bge-m3", texts, want_sparse=True, want_colbert=True)
    encode_corpus("BAAI/bge-m3", texts, want_sparse=True)
    encode_corpus("BAAI/bge-m3", texts, want_colbert=True)

    # Both outputs were primed in the first call; later requests hit the cache.
    assert len(model.calls) == 1


def test_encode_corpus_merges_separate_sparse_then_colbert(monkeypatch: MonkeyPatch) -> None:
    model = _install_fake_model(monkeypatch)
    texts = ["alpha", "bravo"]

    encode_corpus("BAAI/bge-m3", texts, want_sparse=True)
    encode_corpus("BAAI/bge-m3", texts, want_colbert=True)
    merged = encode_corpus("BAAI/bge-m3", texts, want_sparse=True, want_colbert=True)

    assert len(model.calls) == 2
    assert "lexical_weights" in merged
    assert "colbert_vecs" in merged


def test_encode_corpus_distinct_content_uses_distinct_cache(monkeypatch: MonkeyPatch) -> None:
    model = _install_fake_model(monkeypatch)

    encode_corpus("BAAI/bge-m3", ["alpha"], want_sparse=True)
    encode_corpus("BAAI/bge-m3", ["bravo"], want_sparse=True)

    assert len(model.calls) == 2


def test_encode_corpus_empty_texts_returns_empty(monkeypatch: MonkeyPatch) -> None:
    model = _install_fake_model(monkeypatch)

    assert encode_corpus("BAAI/bge-m3", [], want_sparse=True) == {}
    assert model.calls == []


def test_encode_query_requests_only_what_is_asked(monkeypatch: MonkeyPatch) -> None:
    model = _install_fake_model(monkeypatch)

    result = encode_query("BAAI/bge-m3", "alpha", want_sparse=True)

    assert "lexical_weights" in result
    assert "colbert_vecs" not in result
    assert model.calls[0]["sparse"] is True
    assert model.calls[0]["colbert"] is False
