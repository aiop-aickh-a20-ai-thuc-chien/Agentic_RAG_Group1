"""Query preprocessing, BM25 search, and dense search boundaries."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from langchain_postgres import PGVector
from rank_bm25 import BM25Okapi
from turbovec.langchain import TurboQuantVectorStore

from agentic_rag.core.contracts import Chunk, SearchResult

DEFAULT_DENSE_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_DENSE_EMBEDDING_DIMENSIONS = 1536

REQUERY_ROUTER_PROMPT = """
You're a good at understanding user's query. \
    Your task is to analyze the user's query and choose a method to clarify the query.
Chose:
- Decompose: If the query mentions two or more components at same time.
- Expand: If the query contains an entity, the name of the entity. 
Ouput is one of these: "decompose", "expand"
"""

DECOMPOSITION_PROMPT = """
You are a Query Decomposition Expert for a Retrieval-Augmented Generation (RAG) system.
Your mission is to analyze the user's input query and break it down into smaller, simpler, and\
    independent sub-queries. Each sub-query must focus on retrieving ONE specific\
          aspect of information.

INSTRUCTIONS:
1. If the query is complex (contains conjunctions like "and", "as well as", "along with", or\
    requires comparison/synthesis of multiple entities), split it into distinct queries to\
          enable parallel retrieval.
2. Ensure each sub-query is self-contained with a clear subject and context.\
    Do not use ambiguous pronouns like "it", "they", or "this algorithm"; replace them with\
          the explicit entity names.
3. If the query is already simple and atomic, return an array containing only the original query.

OUTPUT FORMAT:
You MUST return the output as a raw JSON object. Follow this schema:
{
  "method": "decompose",
  "transformed_queries": [
    "First sub-query?",
    "Second sub-query?"
  ]
}

EXAMPLE:
User: "So sánh hiệu năng huấn luyện của mô hình Transformer và\
      LSTM khi xử lý dữ liệu tiếng Việt ngắn."
Output:
{
  "method": "decompose",
  "transformed_queries": [
    "Hiệu năng huấn luyện của mô hình Transformer khi xử lý dữ liệu tiếng Việt ngắn là bao nhiêu?",
    "Hiệu năng huấn luyện của mô hình LSTM khi xử lý dữ liệu tiếng Việt ngắn là bao nhiêu?"
  ]
}
"""

EXPANSION_PROMPT = """
You are an AI assistant specializing in search optimization through Query Expansion.
Your task is to help the system retrieve documents more accurately by generating alternative\
      variations (synonyms or different phrasings) of the user's original query.

INSTRUCTIONS:
1. Generate exactly 3 rewritten versions of the original query from different angles or\
      using alternative terminology.
2. Diversify the queries by: utilizing synonyms, converting informal conversational terms into\
      technical documentation language, and incorporating equivalent English/Vietnamese\
          technical terms where appropriate.
3. Maintain the core intent of the original query. Do not broaden the scope to unrelated topics or\
      alter the search objective.

OUTPUT FORMAT:
You MUST return the output as a raw JSON object. Follow this schema:
{
  "medthod": "expand",
  "transformed_queries": [
    "Rewritten version 1",
    "Rewritten version 2",
    "Rewritten version 3"
  ]
}

EXAMPLE:
User: "cách sửa lỗi văng ram khi train model AI trên colab"
Output:
{
  "method": "expand",
  "transformed_queries": [
    "Khắc phục lỗi sập nguồn sập bộ nhớ OOM Out of Memory khi huấn luyện mô hình trên Google Colab",
    "Làm sao để tối ưu hóa bộ nhớ RAM và tránh bị crash khi train deep learning trên Colab?",
    "Biện pháp xử lý Google Colab bị mất kết nối do tràn RAM khi chạy các mô hình học máy"
  ]
}
"""


class Store:
    def __init__(self, chunks: list[Chunk]):
        self._chunks = chunks
        self._bm25_index = self._build_bm25_index(chunks)
        self._vector_index: TurboQuantVectorStore | PGVector | None = None

    def preprocess_query(self, query: str) -> dict[str, Any]:
        """Normalize a raw user query before retrieval."""
        import json
        import os

        from dotenv import load_dotenv
        from openai import OpenAI

        load_dotenv()

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        def _transform_query(query: str, method: str):
            if method == "decompose":
                tprompt = DECOMPOSITION_PROMPT
            elif method == "expand":
                tprompt = EXPANSION_PROMPT

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": tprompt},
                    {"role": "user", "content": query},
                ],
            )

            return json.loads(response.choices[0].message.content)

        normalized = _normalize_text(query)

        router_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": REQUERY_ROUTER_PROMPT},
                {"role": "user", "content": query},
            ],
        )
        requery_method = router_response.choices[0].message.content  # type: ignore[arg-type]
        requery = _transform_query(query, requery_method)

        return {
            "raw": query,
            "normalized": normalized,
            "tokens": " ".join(_tokenize(normalized)),
            "requery": requery,
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

    def _build_vector_index(self, chunks: list[Chunk]) -> PGVector | TurboQuantVectorStore:
        """Build or refresh a dense vector index from shared chunks."""

        from langchain_huggingface.embeddings import HuggingFaceEmbeddings

        embedding = HuggingFaceEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2")

        chunks_list = [chunk.text for chunk in chunks]
        metadatas = [{"chunk_id": chunk.chunk_id, "metadata": chunk.metadata} for chunk in chunks]

        try:
            connection_string = "postgresql+psycopg://postgres.sohcypopuryiipmlyttb:vsf-agenticrag@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"
            store = PGVector(
                embeddings=embedding,
                collection_name="document",
                connection=connection_string,
                pre_delete_collection=True,
            ).from_texts(
                texts=chunks_list,
                embedding=embedding,
                metadatas=metadatas,
                collection_name="document",
                connection=connection_string,
            )

        except Exception:
            store = TurboQuantVectorStore.from_texts(
                texts=chunks_list, embedding=embedding, metadatas=metadatas
            )  # type: ignore[assignment]

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

    def search(self, query: str, top_k: int = 10) -> tuple[list[SearchResult], list[SearchResult]]:
        nquery = self.preprocess_query(query=query)
        transformed_query = " ".join(nquery["requery"]["transformed_queries"])
        bm25_result = self.bm25_search(transformed_query, top_k=top_k)
        dense_result = self.dense_search(transformed_query, top_k=top_k)

        return bm25_result, dense_result


def dense_embedding_metadata() -> dict[str, object]:
    """Return the dense retrieval embedding configuration used by Store."""

    return {
        "provider": "openai",
        "library": "langchain-openai",
        "model": DEFAULT_DENSE_EMBEDDING_MODEL,
        "dimensions": DEFAULT_DENSE_EMBEDDING_DIMENSIONS,
        "vector_store": "pgvector",
    }


def _chunk_from_dense_document(
    *,
    doc: object,
    vector_index: TurboQuantVectorStore | PGVector,
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
