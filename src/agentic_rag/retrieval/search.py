"""Query preprocessing, BM25 search, and dense search boundaries."""

from __future__ import annotations

from rank_bm25 import BM25Okapi
from turbovec.langchain import TurboQuantVectorStore

from agentic_rag.core.contracts import Chunk, SearchResult


class Store:
    def __init__(self, chunks: list[Chunk]):
        self._chunks = chunks
        self._vector_index = self._build_vector_index(chunks)
        self._bm25_index = self._build_bm25_index(chunks)

    def _preprocess_query(self, query: str) -> dict[str, str]:
        """Normalize a raw user query before retrieval."""

        raise NotImplementedError("preprocess_query is scaffolded for retrieval.")

    def _build_bm25_index(self, chunks: list[Chunk]) -> BM25Okapi:
        """Build or refresh a BM25 index from shared chunks."""
        corpus = [chunk.text.split() for chunk in chunks]
        store = BM25Okapi(corpus=corpus)  # type: ignore
        return store

    def bm25_search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """Return top-k BM25 retrieval results."""
        scores = self._bm25_index.get_scores(query=query.split())  # type: ignore

        top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        result = []
        for i, idx in enumerate(top):
            result.append(
                SearchResult(chunk=self._chunks[i], score=scores[idx], rank=i + 1, retriever="bm25")
            )

        return result

    def _build_vector_index(self, chunks: list[Chunk]) -> TurboQuantVectorStore:
        """Build or refresh a dense vector index from shared chunks."""
        from dotenv import load_dotenv
        from langchain_openai import OpenAIEmbeddings

        load_dotenv()

        dimensions = 1536
        embedding = OpenAIEmbeddings(model="text-embedding-3-small", dimensions=dimensions)

        chunks_list = [chunk.text for chunk in chunks]
        metadatas = [{"chunk_id": chunk.chunk_id, "metadata": chunk.metadata} for chunk in chunks]

        store = TurboQuantVectorStore.from_texts(
            texts=chunks_list, embedding=embedding, metadatas=metadatas
        )

        return store

    def dense_search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """Return top-k dense retrieval results."""
        # query = self._preprocess_query(query)
        search_result = self._vector_index.similarity_search_with_score(query=query, k=top_k)

        result = []
        for i, (doc, score) in enumerate(search_result):
            result.append(
                SearchResult(
                    chunk=self._chunks[self._vector_index._str_to_u64[doc.id] - 1],  # type: ignore
                    score=score,
                    rank=i + 1,
                    retriever="dense",
                )
            )

        return result


if __name__ == "__main__":
    from agentic_rag.testing.fixtures import sample_chunks

    store = Store(sample_chunks())
    print(store.dense_search("chinh sach bao hanh"))
