"""Shared BGE-M3 model loading and corpus encoding for SPLADE + ColBERT.

BGE-M3 produces sparse (SPLADE-style lexical weights), dense, and ColBERT
multi-vectors from a single forward pass. ``NeuralSparseIndex`` and
``ColbertIndex`` both build on this module so that:

* the (heavy) BGE-M3 model is loaded **once** and reused across retrievers, and
* a given chunk-set is **encoded once** — even when both retrievers are active —
  and reused across ``Store`` rebuilds, which would otherwise re-encode the whole
  corpus on every request.
"""

from __future__ import annotations

from collections import OrderedDict
from functools import lru_cache
from hashlib import sha256
from typing import Any

_CORPUS_CACHE_MAX = 8
# (model_name, corpus_signature) -> {"lexical_weights": ..., "colbert_vecs": ...}
_corpus_cache: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()


def load_bgem3_model(model_name: str) -> Any:
    """Return a shared, lazily-loaded BGE-M3 model (cached per model name)."""

    return _load_bgem3_model(model_name)


@lru_cache(maxsize=2)
def _load_bgem3_model(model_name: str) -> Any:
    try:
        from FlagEmbedding import BGEM3FlagModel
    except ImportError as exc:
        raise ImportError(
            "BGE-M3 retrievers (SPLADE/ColBERT) require 'FlagEmbedding'. "
            "Run `uv sync --extra local-retrievers`."
        ) from exc
    return BGEM3FlagModel(model_name, use_fp16=True)


def corpus_signature(texts: list[str]) -> str:
    """Return a stable content signature for a corpus, used as a cache key."""

    digest = sha256()
    for text in texts:
        digest.update(text.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def encode_corpus(
    model_name: str,
    texts: list[str],
    *,
    want_sparse: bool = False,
    want_colbert: bool = False,
) -> dict[str, Any]:
    """Encode a corpus with BGE-M3, caching by ``(model, content)`` signature.

    Returns a dict with the requested keys (``lexical_weights`` and/or
    ``colbert_vecs``). Repeated calls for the same corpus reuse the cached
    encode, and a single call requesting both outputs runs only one forward
    pass — so ``Store`` can prime both SPLADE and ColBERT vectors at once.
    """

    if not texts:
        return {}
    signature = (model_name, corpus_signature(texts))
    cached = _corpus_cache.get(signature)
    need_sparse = want_sparse and (cached is None or "lexical_weights" not in cached)
    need_colbert = want_colbert and (cached is None or "colbert_vecs" not in cached)
    if need_sparse or need_colbert:
        model = _load_bgem3_model(model_name)
        output = model.encode(
            texts,
            return_dense=False,
            return_sparse=need_sparse,
            return_colbert_vecs=need_colbert,
        )
        merged = dict(cached) if cached is not None else {}
        if need_sparse:
            merged["lexical_weights"] = output["lexical_weights"]
        if need_colbert:
            merged["colbert_vecs"] = output["colbert_vecs"]
        _store_corpus(signature, merged)
        cached = merged
    return cached if cached is not None else {}


def encode_query(
    model_name: str,
    query: str,
    *,
    want_sparse: bool = False,
    want_colbert: bool = False,
) -> dict[str, Any]:
    """Encode a single query with BGE-M3 and return the requested outputs."""

    model = _load_bgem3_model(model_name)
    output = model.encode(
        [query],
        return_dense=False,
        return_sparse=want_sparse,
        return_colbert_vecs=want_colbert,
    )
    result: dict[str, Any] = {}
    if want_sparse:
        result["lexical_weights"] = output["lexical_weights"][0]
    if want_colbert:
        result["colbert_vecs"] = output["colbert_vecs"][0]
    return result


def colbert_score(model_name: str, query_vecs: Any, doc_vecs: Any) -> float:
    """Compute the BGE-M3 ColBERT Max-Sim score for one query/doc pair."""

    model = _load_bgem3_model(model_name)
    return float(model.colbert_score(query_vecs, doc_vecs))


def _store_corpus(signature: tuple[str, str], value: dict[str, Any]) -> None:
    _corpus_cache[signature] = value
    _corpus_cache.move_to_end(signature)
    while len(_corpus_cache) > _CORPUS_CACHE_MAX:
        _corpus_cache.popitem(last=False)


def clear_corpus_cache() -> None:
    """Clear cached corpus encodings (used by tests and reindex flows)."""

    _corpus_cache.clear()
