"""Query preprocessing, BM25 search, and dense search boundaries."""

from __future__ import annotations

import re
import unicodedata

from langchain_community.vectorstores import FAISS
from rank_bm25 import BM25Okapi

from agentic_rag.core.contracts import Chunk, SearchResult

DEFAULT_DENSE_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_DENSE_EMBEDDING_DIMENSIONS = 1536


class Store:
    def __init__(self, chunks: list[Chunk]):
        self._chunks = chunks
        self._bm25_index = self._build_bm25_index(chunks)
        self._vector_index: FAISS | None = None

    def preprocess_query(self, query: str) -> dict[str, str]:
        """Normalize a raw user query before retrieval."""

        normalized = _normalize_text(query)
        return {
            "raw": query,
            "normalized": normalized,
            "tokens": " ".join(_tokenize(normalized)),
        }

    def _build_bm25_index(self, chunks: list[Chunk]) -> BM25Okapi:
        """Build or refresh a BM25 index from shared chunks."""
        corpus = [_tokenize(chunk.text) for chunk in chunks]
        store = BM25Okapi(corpus=corpus)  # type: ignore[no-untyped-call]
        return store

    def bm25_search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """Return top-k BM25 retrieval results."""
        if top_k <= 0 or not self._chunks:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25_index.get_scores(query_tokens)  # type: ignore[no-untyped-call]
        top_indexes = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)[
            :top_k
        ]

        results = []
        for rank, chunk_index in enumerate(top_indexes, start=1):
            score = float(scores[chunk_index])
            results.append(
                SearchResult(
                    chunk=self._chunks[chunk_index],
                    score=score,
                    rank=rank,
                    retriever="bm25",
                )
            )

        return results

    def _build_vector_index(self, chunks: list[Chunk]) -> FAISS:
        """Build or refresh a dense vector index from shared chunks."""
        from langchain_openai import OpenAIEmbeddings

        embedding = OpenAIEmbeddings(
            model=DEFAULT_DENSE_EMBEDDING_MODEL,
            dimensions=DEFAULT_DENSE_EMBEDDING_DIMENSIONS,
        )

        chunks_list = [chunk.text for chunk in chunks]
        metadatas = [{"chunk_id": chunk.chunk_id, "metadata": chunk.metadata} for chunk in chunks]

        store = FAISS.from_texts(texts=chunks_list, embedding=embedding, metadatas=metadatas)

        return store

    def dense_search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """Return top-k dense retrieval results."""
        if top_k <= 0 or not self._chunks:
            return []

        if self._vector_index is None:
            self._vector_index = self._build_vector_index(self._chunks)

        search_result = self._vector_index.similarity_search_with_score(query=query, k=top_k)

        result = []
        for i, (doc, score) in enumerate(search_result):
            result.append(
                SearchResult(
                    chunk=Chunk(
                        chunk_id=doc.metadata["chunk_id"],
                        text=doc.page_content,
                        metadata=doc.metadata["metadata"],
                    ),
                    score=score,
                    rank=i + 1,
                    retriever="dense",
                )
            )

        return result


def dense_embedding_metadata() -> dict[str, object]:
    """Return the dense retrieval embedding configuration used by Store."""

    return {
        "provider": "openai",
        "library": "langchain-openai",
        "model": DEFAULT_DENSE_EMBEDDING_MODEL,
        "dimensions": DEFAULT_DENSE_EMBEDDING_DIMENSIONS,
        "vector_store": "faiss",
    }


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", _normalize_text(text))


def _normalize_text(text: str) -> str:
    lowered = text.lower().replace("\u0111", "d").replace("\u0110", "d")
    normalized = unicodedata.normalize("NFKD", lowered)
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(without_accents.split())


if __name__ == "__main__":
    from agentic_rag.testing.fixtures import sample_chunks

    store = Store(sample_chunks())
    print(store.bm25_search("pin cao ap"))
