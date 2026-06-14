"""Late Interaction (ColBERT) Dense Retrieval using BGE-M3."""

from __future__ import annotations

import logging
from typing import Any

from agentic_rag.core.contracts import Chunk
from agentic_rag.retrieval.bgem3 import colbert_score, encode_corpus, encode_query, load_bgem3_model

logger = logging.getLogger(__name__)


class _PseudoDoc:
    """Mock document class to maintain compatibility with Langchain VectorStore outputs."""

    def __init__(self, metadata: dict[str, Any], page_content: str):
        self.metadata = metadata
        self.page_content = page_content


class ColbertIndex:
    """ColBERT (Late Interaction) index for high-precision dense retrieval.

    Shares the BGE-M3 model and corpus encode with :class:`NeuralSparseIndex`
    via :mod:`agentic_rag.retrieval.bgem3`, so the model loads once and a
    chunk-set is encoded once even when both retrievers are active.
    """

    def __init__(self, chunks: list[Chunk], model_name: str = "BAAI/bge-m3") -> None:
        self.chunks = chunks
        self.model_name = model_name

        logger.info("Loading BGE-M3 model for ColBERT Indexing: %s", model_name)
        load_bgem3_model(model_name)

        if not chunks:
            self.chunk_vecs: list[Any] = []
            return

        texts = [chunk.text for chunk in chunks]
        self.chunk_vecs = encode_corpus(model_name, texts, want_colbert=True)["colbert_vecs"]

    def similarity_search_with_score(
        self, query: str, k: int = 10, filter: Any = None
    ) -> list[tuple[Any, float]]:
        """Compute ColBERT Max-Sim scores and return pseudo-documents."""
        if not self.chunks:
            return []

        query_vecs = encode_query(self.model_name, query, want_colbert=True)["colbert_vecs"]

        results: list[tuple[Any, float]] = []
        for i, chunk_vec in enumerate(self.chunk_vecs):
            # BGE-M3 Max-Sim late-interaction score for this query/chunk pair.
            score = colbert_score(self.model_name, query_vecs, chunk_vec)
            doc = _PseudoDoc(metadata={"chunk_index": i}, page_content=self.chunks[i].text)
            results.append((doc, float(score)))

        results.sort(key=lambda item: item[1], reverse=True)
        return results[:k]
