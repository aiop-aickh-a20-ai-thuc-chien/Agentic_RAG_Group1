"""Query preprocessing, BM25 search, and dense search boundaries."""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any

from rank_bm25 import BM25Okapi
from turbovec.langchain import TurboQuantVectorStore

from agentic_rag.core.contracts import Chunk, SearchResult

DEFAULT_DENSE_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_DENSE_EMBEDDING_DIMENSIONS = 1536
DEFAULT_HF_EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
DENSE_EMBEDDING_PROVIDER_ENV = "DENSE_EMBEDDING_PROVIDER"
DENSE_VECTOR_STORE_ENV = "DENSE_VECTOR_STORE"
DENSE_PGVECTOR_CONNECTION_ENV = "DENSE_PGVECTOR_CONNECTION"
DENSE_PGVECTOR_COLLECTION_ENV = "DENSE_PGVECTOR_COLLECTION"
HF_EMBEDDING_MODEL_ENV = "HF_EMBEDDING_MODEL"

REQUERY_ROUTER_PROMPT = """
<task>
Analyze the user's query and choose one retrieval query clarification method.
</task>

<methods>
- Decompose: If the query mentions two or more distinct components simultaneously,
  break it down into 2-3 simpler sub-queries as a JSON array of strings.
- Expand: If the query contains a specific entity or name, generate one
  expanded/rephrased query string with more context.
</methods>

<output>
Return Vietnamese only. Use this exact JSON format:
  For Decompose: {"method": "Decompose", "answer": ["sub-query 1", "sub-query 2"]}
  For Expand:    {"method": "Expand", "answer": "expanded query string"}
</output>
"""


class Store:
    def __init__(self, chunks: list[Chunk]):
        self._chunks = chunks
        self._bm25_index = self._build_bm25_index(chunks)
        self._vector_index: Any = None

    def preprocess_query(self, query: str, llm_client: object = None) -> dict[str, Any]:
        """Normalize a raw user query before retrieval."""
        import json

        normalized = _normalize_text(query)
        base: dict[str, Any] = {
            "raw": query,
            "normalized": normalized,
            "tokens": " ".join(_tokenize(normalized)),
        }

        if llm_client is None:
            return {**base, "requery": {"method": "Expand", "answer": query}}

        try:
            complete = getattr(llm_client, "complete", None)
            if not callable(complete):
                raise TypeError("llm_client must implement LLMClient protocol")
            prompt = f"{REQUERY_ROUTER_PROMPT}\n<query>\n{query}\n</query>"
            raw: str = complete(prompt)
            requery = json.loads(raw)
            if not isinstance(requery, dict) or "method" not in requery or "answer" not in requery:
                raise ValueError("unexpected requery format")
        except Exception:
            return {**base, "requery": {"method": "Expand", "answer": query}}

        return {**base, "requery": requery}

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

    def _build_vector_index(self, chunks: list[Chunk]) -> Any:
        """Build or refresh a dense vector index from shared chunks."""

        embedding = _configured_embedding()
        chunks_list = [chunk.text for chunk in chunks]
        metadatas = _dense_metadatas(chunks)
        ids = _dense_ids(chunks)
        if _configured_vector_store() == "pgvector":
            pgvector_store = _build_pgvector_store(
                texts=chunks_list,
                embedding=embedding,
                metadatas=metadatas,
                ids=ids,
            )
            if pgvector_store is not None:
                return pgvector_store

        return TurboQuantVectorStore.from_texts(
            texts=chunks_list, embedding=embedding, metadatas=metadatas
        )

    def dense_search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """Return top-k dense retrieval results."""
        if top_k <= 0 or not self._chunks:
            return []

        if self._vector_index is None:
            self._vector_index = self._build_vector_index(self._chunks)

        filter_value = _dense_filter_for_chunks(self._chunks)
        if filter_value is None:
            search_result = self._vector_index.similarity_search_with_score(query=query, k=top_k)
        else:
            search_result = self._vector_index.similarity_search_with_score(
                query=query,
                k=top_k,
                filter=filter_value,
            )

        result = []
        for i, (doc, score) in enumerate(search_result):
            result.append(
                SearchResult(
                    chunk=_chunk_from_dense_document(
                        doc=doc,
                        vector_index=self._vector_index,
                        chunks=self._chunks,
                    ),
                    score=score,
                    rank=i + 1,
                    retriever="dense",
                )
            )

        return result

    def search(
        self,
        query: str,
        top_k: int = 10,
        llm_client: object = None,
    ) -> tuple[list[SearchResult], list[SearchResult]]:
        nquery = self.preprocess_query(query=query, llm_client=llm_client)
        method = nquery["requery"].get("method", "Expand")
        answer = nquery["requery"].get("answer", query)

        if method == "Decompose" and isinstance(answer, list):
            return self._search_decomposed(answer, top_k=top_k)

        expanded = answer if isinstance(answer, str) else " ".join(str(a) for a in answer)
        return self.bm25_search(expanded, top_k=top_k), self.dense_search(expanded, top_k=top_k)

    def _search_decomposed(
        self,
        sub_queries: list[str],
        top_k: int,
    ) -> tuple[list[SearchResult], list[SearchResult]]:
        seen: set[str] = set()
        all_bm25: list[SearchResult] = []
        all_dense: list[SearchResult] = []
        for sub_query in sub_queries:
            for result in self.bm25_search(sub_query, top_k=top_k):
                if result.chunk.chunk_id not in seen:
                    seen.add(result.chunk.chunk_id)
                    all_bm25.append(result)
            for result in self.dense_search(sub_query, top_k=top_k):
                if result.chunk.chunk_id not in seen:
                    seen.add(result.chunk.chunk_id)
                    all_dense.append(result)
        return all_bm25, all_dense


def dense_embedding_metadata() -> dict[str, object]:
    """Return the dense retrieval embedding configuration used by Store."""

    provider = _configured_embedding_provider()
    vector_store = _configured_vector_store()
    if provider == "huggingface":
        return {
            "provider": "huggingface",
            "library": "langchain-huggingface",
            "model": os.getenv(HF_EMBEDDING_MODEL_ENV, DEFAULT_HF_EMBEDDING_MODEL),
            "vector_store": vector_store,
        }
    return {
        "provider": "openai",
        "library": "langchain-openai",
        "model": DEFAULT_DENSE_EMBEDDING_MODEL,
        "dimensions": DEFAULT_DENSE_EMBEDDING_DIMENSIONS,
        "vector_store": vector_store,
    }


def upsert_dense_embeddings(chunks: list[Chunk]) -> dict[str, object]:
    """Upsert chunk embeddings into the configured persistent vector store."""

    vector_store = _configured_vector_store()
    if vector_store != "pgvector":
        return {
            "enabled": False,
            "vector_store": vector_store,
            "reason": "only pgvector persists dense embeddings",
        }
    if not chunks:
        return {"enabled": True, "vector_store": vector_store, "chunk_count": 0}

    embedding = _configured_embedding()
    pgvector_store = _build_pgvector_store(
        texts=[chunk.text for chunk in chunks],
        embedding=embedding,
        metadatas=_dense_metadatas(chunks),
        ids=_dense_ids(chunks),
    )
    return {
        "enabled": pgvector_store is not None,
        "vector_store": vector_store,
        "chunk_count": len(chunks) if pgvector_store is not None else 0,
        "collection": _configured_pgvector_collection(),
    }


def _configured_embedding_provider() -> str:
    return os.getenv(DENSE_EMBEDDING_PROVIDER_ENV, "openai").strip().lower()


def _configured_vector_store() -> str:
    raw = os.getenv(DENSE_VECTOR_STORE_ENV, "turbovec").strip().lower()
    return "pgvector" if raw in {"pgvector", "postgres", "postgresql"} else "turbovec"


def _configured_embedding() -> Any:
    provider = _configured_embedding_provider()
    if provider == "huggingface":
        from langchain_huggingface.embeddings import HuggingFaceEmbeddings

        model = os.getenv(HF_EMBEDDING_MODEL_ENV, DEFAULT_HF_EMBEDDING_MODEL)
        return HuggingFaceEmbeddings(model_name=model)
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model=DEFAULT_DENSE_EMBEDDING_MODEL,
        dimensions=DEFAULT_DENSE_EMBEDDING_DIMENSIONS,
    )


def _build_pgvector_store(
    *,
    texts: list[str],
    embedding: Any,
    metadatas: list[dict[str, object]],
    ids: list[str],
) -> Any | None:
    connection = os.getenv(DENSE_PGVECTOR_CONNECTION_ENV, "").strip()
    if not connection:
        return None

    try:
        from langchain_postgres import PGVector
    except ImportError:
        return None

    return PGVector.from_texts(
        texts=texts,
        embedding=embedding,
        metadatas=metadatas,
        ids=ids,
        collection_name=_configured_pgvector_collection(),
        connection=connection,
        pre_delete_collection=False,
    )


def _configured_pgvector_collection() -> str:
    return os.getenv(DENSE_PGVECTOR_COLLECTION_ENV, "document").strip() or "document"


def _dense_metadatas(chunks: list[Chunk]) -> list[dict[str, object]]:
    return [
        {
            "chunk_id": chunk.chunk_id,
            "storage_chunk_id": _dense_id(chunk=chunk, fallback_index=index),
            "document_id": str(chunk.metadata.get("document_id") or ""),
            "source_type": str(chunk.metadata.get("source_type") or ""),
            "metadata": chunk.metadata,
        }
        for index, chunk in enumerate(chunks, start=1)
    ]


def _dense_ids(chunks: list[Chunk]) -> list[str]:
    return [
        _dense_id(chunk=chunk, fallback_index=index)
        for index, chunk in enumerate(chunks, start=1)
    ]


def _dense_id(*, chunk: Chunk, fallback_index: int) -> str:
    storage_chunk_id = chunk.metadata.get("storage_chunk_id")
    if isinstance(storage_chunk_id, str) and storage_chunk_id:
        return storage_chunk_id
    document_id = str(chunk.metadata.get("document_id") or "document")
    return f"{document_id}:{fallback_index:04d}"


def _dense_filter_for_chunks(chunks: list[Chunk]) -> dict[str, object] | None:
    if _configured_vector_store() != "pgvector":
        return None
    document_ids = sorted(
        {
            str(chunk.metadata.get("document_id"))
            for chunk in chunks
            if chunk.metadata.get("document_id")
        }
    )
    if not document_ids:
        return None
    if len(document_ids) == 1:
        return {"document_id": document_ids[0]}
    return {"document_id": {"$in": document_ids}}


def _chunk_from_dense_document(
    *,
    doc: object,
    vector_index: Any,
    chunks: list[Chunk],
) -> Chunk:
    metadata = getattr(doc, "metadata", {})
    if isinstance(metadata, dict) and "chunk_id" in metadata:
        nested_metadata = metadata.get("metadata")
        return Chunk(
            chunk_id=str(metadata["chunk_id"]),
            text=str(getattr(doc, "page_content", "")),
            metadata=nested_metadata if isinstance(nested_metadata, dict) else {},
        )

    doc_id = getattr(doc, "id", None)
    str_to_u64 = getattr(vector_index, "_str_to_u64", {})
    if doc_id is not None and doc_id in str_to_u64:
        chunk_index = int(str_to_u64[doc_id]) - 1
        if 0 <= chunk_index < len(chunks):
            return chunks[chunk_index]

    return Chunk(
        chunk_id=str(doc_id or "dense_unknown"),
        text=str(getattr(doc, "page_content", "")),
        metadata={},
    )


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
    print(store.preprocess_query("so sánh VF8 và VF9"))
