"""Neural Sparse Retrieval using BGE-M3 (SPLADE architecture equivalent)."""

from __future__ import annotations

import logging
from typing import Any

from agentic_rag.core.contracts import Chunk
from agentic_rag.retrieval.bgem3 import encode_corpus, encode_query, load_bgem3_model

logger = logging.getLogger(__name__)


class NeuralSparseIndex:
    """A drop-in replacement for BM25Okapi using Neural Sparse Weights (BGE-M3/SPLADE).

    Shares the BGE-M3 model and corpus encode with :class:`ColbertIndex` via
    :mod:`agentic_rag.retrieval.bgem3`, so the model loads once and a chunk-set
    is encoded once even when both retrievers are active.
    """

    def __init__(self, chunks: list[Chunk], model_name: str = "BAAI/bge-m3") -> None:
        try:
            import scipy.sparse as sp
        except ImportError as exc:
            raise ImportError(
                "Neural sparse retrieval requires 'scipy'. Run `uv sync --extra local-retrievers`."
            ) from exc

        self.chunks = chunks
        self.model_name = model_name

        logger.info("Loading BGE-M3 model for Neural Sparse Indexing: %s", model_name)
        model = load_bgem3_model(model_name)
        self.vocab_size = len(model.tokenizer)

        if not chunks:
            self.chunk_matrix = sp.csr_matrix((0, self.vocab_size))
            return

        texts = [chunk.text for chunk in chunks]
        # BGE-M3 lexical weights are the 'SPLADE' part: {token_id_str: weight_float}.
        lexical_weights_list = encode_corpus(model_name, texts, want_sparse=True)["lexical_weights"]

        rows: list[int] = []
        cols: list[int] = []
        data: list[float] = []
        for i, weight_dict in enumerate(lexical_weights_list):
            for token_str, weight in weight_dict.items():
                rows.append(i)
                cols.append(int(token_str))
                data.append(weight)

        if not rows:
            self.chunk_matrix = sp.csr_matrix((len(chunks), self.vocab_size))
        else:
            self.chunk_matrix = sp.csr_matrix(
                (data, (rows, cols)),
                shape=(len(chunks), self.vocab_size),
            )

    def get_scores(self, query: str | list[str]) -> list[float]:
        """Compute sparse dot product scores against all chunks."""
        import scipy.sparse as sp

        if not self.chunks:
            return []

        if isinstance(query, list):
            query = " ".join(query)

        lexical_weights = encode_query(self.model_name, query, want_sparse=True)["lexical_weights"]

        rows: list[int] = []
        cols: list[int] = []
        data: list[float] = []
        for token_str, weight in lexical_weights.items():
            rows.append(0)
            cols.append(int(token_str))
            data.append(weight)

        if not rows:
            query_matrix = sp.csr_matrix((1, self.vocab_size))
        else:
            query_matrix = sp.csr_matrix(
                (data, (rows, cols)),
                shape=(1, self.vocab_size),
            )

        # Dot product between chunks and query.
        scores: Any = self.chunk_matrix.dot(query_matrix.T).toarray().flatten()
        return [float(score) for score in scores]
