"""Query preprocessing, BM25 search, and dense search boundaries."""

from __future__ import annotations

import contextlib
import os
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from functools import lru_cache
from hashlib import sha256
from threading import Lock
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from rank_bm25 import BM25Okapi
from turbovec.langchain import TurboQuantVectorStore

from agentic_rag.core.contracts import Chunk, EmbeddingOutput, SearchResult
from agentic_rag.model_runtime.config import EmbeddingConfig, resolve_embedding_config
from agentic_rag.model_runtime.embeddings import (
    EmbeddingCompatibilityAdapter,
    validate_embedding_output,
)
from agentic_rag.model_runtime.factory import get_embedding_client
from agentic_rag.retrieval.config import VectorStoreConfig, resolve_vector_store_config


def _noop_traceable(*, name: str = "", run_type: str = "chain", **_: object) -> Any:
    def _decorator(func: Any) -> Any:
        return func

    return _decorator


try:
    from langsmith import traceable as _ls_traceable
except Exception:  # pragma: no cover - langsmith optional
    _ls_traceable = _noop_traceable  # type: ignore[assignment]


EmbeddingProfile = EmbeddingOutput
_QDRANT_DOCUMENT_ID_FIELD = "document_id"
_QDRANT_DEDUP_PRIMARY_LAYER_FIELD = "metadata.deduplication.primary_layer"
_QDRANT_ENTITIES_CANONICAL_FIELD = "metadata.entities_canonical"
_QDRANT_KEYWORD_PAYLOAD_INDEX_FIELDS = (
    _QDRANT_DOCUMENT_ID_FIELD,
    _QDRANT_DEDUP_PRIMARY_LAYER_FIELD,
    _QDRANT_ENTITIES_CANONICAL_FIELD,
)

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


def _bm25_augment_keywords() -> bool:
    """BM25 keyword-augmentation experiment flag (default OFF → baseline).

    When ``RETRIEVAL_BM25_AUGMENT_KEYWORDS=true``, a chunk's LLM-extracted
    ``keywords`` are appended to the text the sparse index covers so those terms
    gain lexical weight. Used to A/B test sparse recall without touching the
    dense embedding. Off keeps the sparse index text-only (current behaviour).
    """
    return os.getenv("RETRIEVAL_BM25_AUGMENT_KEYWORDS", "false").lower() == "true"


def _bm25_index_text(chunk: Chunk) -> str:
    """Return the document text the sparse index should cover for ``chunk``.

    Baseline is ``chunk.text``. Shared by BOTH sparse backends — the in-memory
    ``BM25Okapi`` corpus and the Qdrant sparse vector — so the augmentation
    experiment behaves identically regardless of which retrieval path runs.
    """
    if not _bm25_augment_keywords():
        return chunk.text
    keywords = chunk.metadata.get("keywords")
    if not isinstance(keywords, (list, tuple)):
        return chunk.text
    appended = " ".join(str(keyword) for keyword in keywords if str(keyword).strip())
    return f"{chunk.text}\n{appended}" if appended else chunk.text


MAX_QUESTIONS_PER_CHUNK = 4


def _question_index_enabled() -> bool:
    """Master toggle for the question-index retriever (default OFF → baseline)."""
    return os.getenv("RETRIEVAL_QUESTION_INDEX_ENABLED", "false").lower() == "true"


def _graph_retrieval_enabled() -> bool:
    """Master toggle for the knowledge-graph retriever (default OFF → baseline)."""
    return os.getenv("GRAPH_RETRIEVAL_ENABLED", "false").lower() == "true"


_KG_RETRIEVER: Any = None


def _kg_retriever() -> Any:
    """Cached KGRetriever over the Neo4j graph (loaded once; reused per query). Returns
    None if the kg package / Neo4j is unavailable so the graph channel degrades quietly."""
    global _KG_RETRIEVER
    if _KG_RETRIEVER is None:
        try:
            from kg.retrieve import KGRetriever
            from kg.store_neo4j import Neo4jStore

            _KG_RETRIEVER = KGRetriever.from_store(Neo4jStore())
        except Exception:
            _KG_RETRIEVER = False
    return _KG_RETRIEVER or None


_CHUNK_ID_INDEXED: set[str] = set()


def _ensure_chunk_id_index(client: Any, collection: str) -> None:
    """A MatchAny filter on chunk_id needs a keyword payload index — create it once
    (idempotent, best-effort) so graph-channel hydration can fetch chunks by id."""
    if collection in _CHUNK_ID_INDEXED:
        return
    import contextlib

    from qdrant_client import models

    with contextlib.suppress(Exception):
        client.create_payload_index(
            collection_name=collection,
            field_name="chunk_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
    _CHUNK_ID_INDEXED.add(collection)


def _fetch_chunks_by_id(client: Any, collection: str, chunk_ids: list[str]) -> dict[str, Chunk]:
    """Hydrate ONLY the given chunk_ids straight from Qdrant (server-side filter), far
    lighter than scrolling + embedding the whole question store just to map ids→chunks."""
    if not chunk_ids:
        return {}
    from qdrant_client import models

    _ensure_chunk_id_index(client, collection)
    flt = models.Filter(
        must=[models.FieldCondition(key="chunk_id", match=models.MatchAny(any=list(chunk_ids)))]
    )
    found: dict[str, Chunk] = {}
    offset = None
    while len(found) < len(chunk_ids):
        batch, offset = client.scroll(
            collection_name=collection,
            scroll_filter=flt,
            limit=len(chunk_ids),
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in batch:
            payload = getattr(point, "payload", None)
            if isinstance(payload, dict):
                cid = str(payload.get("chunk_id") or "")
                if cid and cid not in found:
                    found[cid] = _chunk_from_qdrant_payload(payload)
        if offset is None or not batch:
            break
    return found


def _graph_search(
    query: str, client: Any, collection: str, top_k: int
) -> tuple[list[SearchResult], int]:
    """KG retrieval as a retriever channel: link query→entities, traverse, hydrate the
    provenance chunks (fetched by id from Qdrant) as SearchResults. Returns
    (results, anchor_count) so the caller can trace linking even on a miss."""
    retriever = _kg_retriever()
    if retriever is None or top_k <= 0:
        return [], 0
    hit = retriever.retrieve(query, hops=1)
    if not hit.chunk_scores:
        return [], len(hit.anchors)
    top = hit.ranked_chunks[:top_k]
    by_id = _fetch_chunks_by_id(client, collection, [chunk_id for chunk_id, _ in top])
    out: list[SearchResult] = []
    for rank, (chunk_id, gscore) in enumerate(top, start=1):
        chunk = by_id.get(chunk_id)
        if chunk is not None:
            out.append(SearchResult(chunk=chunk, score=float(gscore), rank=rank, retriever="graph"))
    return out, len(hit.anchors)


@_ls_traceable(name="graph-retrieval", run_type="retriever")
def _trace_graph_retrieval(summary: dict[str, object]) -> dict[str, object]:
    """Emit the knowledge-graph retriever decision to LangSmith (anchors, hits, fusion).
    A span only appears when GRAPH_RETRIEVAL_ENABLED is on, so absent span = feature off."""
    return summary


_TRACE_CHUNK_TEXT_CHARS = int(os.getenv("TRACE_CHUNK_TEXT_CHARS", "400"))


def _trace_chunks(results: list[SearchResult]) -> list[dict[str, object]]:
    """Per-chunk view for a retriever's span: id + score + source channel + a text
    preview so the trace shows WHAT each retriever pulled, not just ids."""
    return [
        {
            "chunk_id": r.chunk.chunk_id,
            "score": round(float(r.score), 4),
            "retriever": r.retriever,
            "text": (r.chunk.text or "")[:_TRACE_CHUNK_TEXT_CHARS],
        }
        for r in results
    ]


@_ls_traceable(name="retrieval-fusion", run_type="tool")
def _trace_fusion(summary: dict[str, object]) -> dict[str, object]:
    """Full INPUT→OUTPUT view of the RRF fusion node in one span:
    INPUT  = every channel's chunk list feeding RRF (hybrid dense+sparse, question-index,
             graph) + per-channel counts;
    OUTPUT = the final fused ranked list, each chunk tagged with the channels that
             produced it — so one span answers 'what went in and what came out of RRF'."""
    return summary


def _question_index_collection() -> str:
    """Name of the auxiliary Qdrant collection holding per-question embeddings.

    Defaults to ``{main_collection}_questions``; override with
    ``QUESTION_INDEX_COLLECTION``. When this collection exists, the question-index
    retriever queries it directly (persistent, no in-memory scroll/embed);
    otherwise it falls back to the in-memory index.
    """
    explicit = os.getenv("QUESTION_INDEX_COLLECTION", "").strip()
    if explicit:
        return explicit
    return f"{_configured_qdrant_collection()}_questions"


def _question_min_score() -> float | None:
    """Min cosine similarity to keep a question match; empty env disables filtering.

    Defaults to 0.5 — a sensible floor for the multilingual MiniLM embedder so a
    question match must be genuinely similar (the question index always returns
    nearest neighbours, so an absolute cutoff is what drops irrelevant noise).
    """
    raw = os.getenv("QUESTION_MIN_SCORE", "0.5").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class Store:
    def __init__(self, chunks: list[Chunk]):
        self._chunks = chunks
        self._bm25_index = self._build_bm25_index(chunks)
        self._vector_index: Any = None
        self._question_index: Any = None

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
        corpus = [_tokenize(_bm25_index_text(chunk)) for chunk in chunks]
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
        if _configured_vector_store() == "pgvector":
            # Search-only: connect to existing pgvector index, do NOT re-embed stored texts.
            # Embeddings were already upserted during ingest via upsert_dense_embeddings().
            pgvector_store = _build_pgvector_store_for_search(embedding=embedding)
            if pgvector_store is not None:
                return pgvector_store

        chunks_list = [chunk.text for chunk in chunks]
        metadatas = _dense_metadatas(chunks)
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

    def _build_question_index(self, chunks: list[Chunk]) -> Any:
        """Build an in-memory dense index over each chunk's LLM-extracted questions.

        Each indexed point is one question, tagged with the parent chunk's index
        so a question hit maps back to its chunk. Returns ``None`` when no chunk
        has questions.
        """
        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            questions = chunk.metadata.get("questions")
            if not isinstance(questions, (list, tuple)):
                continue
            for question in list(questions)[:MAX_QUESTIONS_PER_CHUNK]:
                text = str(question).strip()
                if text:
                    texts.append(text)
                    metadatas.append({"parent_index": index})
        if not texts:
            return None
        return TurboQuantVectorStore.from_texts(
            texts=texts, embedding=_configured_embedding(), metadatas=metadatas
        )

    def question_search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """Match the query against chunk questions; return the parent chunks.

        A second dense search whose index is the chunks' questions instead of
        their text — exploits question↔question similarity. Disabled by default;
        applies ``QUESTION_MIN_SCORE`` and dedups multiple question hits to the
        best score per parent chunk.
        """
        if not _question_index_enabled() or top_k <= 0 or not self._chunks:
            return []

        if self._question_index is None:
            self._question_index = self._build_question_index(self._chunks)
        if self._question_index is None:
            return []

        min_score = _question_min_score()
        # Over-fetch: several questions can map to the same chunk before dedup.
        raw = self._question_index.similarity_search_with_score(
            query=query, k=top_k * MAX_QUESTIONS_PER_CHUNK
        )
        best_by_parent: dict[int, float] = {}
        for doc, score in raw:
            parent_index = doc.metadata.get("parent_index")
            if not isinstance(parent_index, int) or not 0 <= parent_index < len(self._chunks):
                continue
            if min_score is not None and score < min_score:
                continue
            if parent_index not in best_by_parent or score > best_by_parent[parent_index]:
                best_by_parent[parent_index] = score

        ranked = sorted(best_by_parent.items(), key=lambda item: item[1], reverse=True)[:top_k]
        return [
            SearchResult(
                chunk=self._chunks[parent_index],
                score=float(score),
                rank=rank,
                retriever="question",
            )
            for rank, (parent_index, score) in enumerate(ranked, start=1)
        ]

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

    vector_store = _configured_vector_store()
    try:
        config = resolve_embedding_config()
    except ValueError as exc:
        return {
            "provider": None,
            "requested_provider": os.getenv("EMBEDDING_PROVIDER", "sentence_transformers")
            .strip()
            .lower()
            or "sentence_transformers",
            "resolved_provider": None,
            "configuration_error": str(exc),
            "vector_store": vector_store,
            **({"collection": _configured_qdrant_collection()} if vector_store == "qdrant" else {}),
        }
    return {
        "provider": config.provider,
        "requested_provider": config.provider,
        "resolved_provider": config.provider,
        "fallback_reason": None,
        "library": (
            "sentence-transformers" if config.provider == "sentence_transformers" else "litellm"
        ),
        "model": config.model,
        **(
            {"expected_dimensions": config.expected_dimensions}
            if config.expected_dimensions is not None
            else {}
        ),
        "vector_store": vector_store,
        **({"collection": _configured_qdrant_collection()} if vector_store == "qdrant" else {}),
    }


def upsert_dense_embeddings(
    chunks: list[Chunk],
    *,
    vector_config: VectorStoreConfig | None = None,
    precomputed_dense_vectors: list[list[float]] | None = None,
) -> dict[str, object]:
    """Upsert chunk embeddings into the configured persistent vector store.

    ``precomputed_dense_vectors`` (aligned 1-1 with ``chunks``) lets callers that
    already embedded the chunks — e.g. upload-time dedup Layer 3 — reuse those
    vectors instead of paying for a second embedding pass.
    """

    if precomputed_dense_vectors is not None and len(precomputed_dense_vectors) != len(chunks):
        precomputed_dense_vectors = None

    has_validated_config = vector_config is not None
    config = vector_config or _vector_store_config()
    vector_store = config.provider
    if vector_store == "qdrant":
        return _upsert_qdrant_embeddings(
            chunks,
            vector_config=config,
            use_validated_config=has_validated_config,
            precomputed_dense_vectors=precomputed_dense_vectors,
        )
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
        vector_config=config,
    )
    return {
        "enabled": pgvector_store is not None,
        "vector_store": vector_store,
        "chunk_count": len(chunks) if pgvector_store is not None else 0,
        "collection": config.collection,
    }


def _configured_vector_store() -> str:
    return _vector_store_config().provider


def _vector_store_config() -> VectorStoreConfig:
    return resolve_vector_store_config()


def _configured_embedding() -> Any:
    return EmbeddingCompatibilityAdapter(client=get_embedding_client())


def _build_pgvector_store(
    *,
    texts: list[str],
    embedding: Any,
    metadatas: list[dict[str, object]],
    ids: list[str],
    vector_config: VectorStoreConfig | None = None,
) -> Any | None:
    """Upsert texts into pgvector (used at ingest time — calls embedding API)."""
    config = vector_config or _vector_store_config()
    connection = (
        config.url.get_secret_value()
        if config.provider == "pgvector" and config.url is not None
        else None
    )
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
        collection_name=config.collection,
        connection=connection,
        pre_delete_collection=False,
    )


def _build_pgvector_store_for_search(*, embedding: Any) -> Any | None:
    """Connect to existing pgvector index for search (does NOT re-embed stored texts)."""
    connection = _configured_pgvector_connection()
    if not connection:
        return None

    try:
        from langchain_postgres import PGVector
    except ImportError:
        return None

    return PGVector(
        embeddings=embedding,
        collection_name=_configured_pgvector_collection(),
        connection=connection,
    )


def _configured_pgvector_collection() -> str:
    return _vector_store_config().collection


def _configured_pgvector_connection() -> str | None:
    config = _vector_store_config()
    if config.provider != "pgvector" or config.url is None:
        return None
    return config.url.get_secret_value()


def _configured_qdrant_collection() -> str:
    return _vector_store_config().collection


def _hard_filter_enabled() -> bool:
    """Single on/off switch for the entity hard-filter (default ON).

    Set ``HARD_FILTER_ENABLED`` to a falsy string to disable filtering entirely.
    Gated at the Qdrant chokepoint (:func:`_qdrant_combined_filter`) so it applies
    to every path — including the agent path where entities are LLM-extracted in
    ``preprocess_query`` and never pass through :func:`_entity_prefilter_for`.
    """
    import os

    return os.getenv("HARD_FILTER_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _entity_prefilter_llm_enabled() -> bool:
    """LLM paraphrase fallback is OFF unless ENTITY_PREFILTER_LLM is a truthy string."""
    import os

    return os.getenv("ENTITY_PREFILTER_LLM", "false").strip().lower() in {"1", "true", "yes", "on"}


_ENTITY_LLM_SYSTEM = (
    "Bạn trích xuất thực thể để LỌC tài liệu xe điện VinFast. CHỈ được chọn các tên "
    "có trong danh sách cho sẵn. Trả về DUY NHẤT một JSON array, không giải thích."
)


def _parse_str_array(text: str) -> list[str]:
    import json

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    first, last = stripped.find("["), stripped.rfind("]")
    if first >= 0 and last > first:
        stripped = stripped[first : last + 1]
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return []
    return [str(item).strip() for item in data] if isinstance(data, list) else []


@lru_cache(maxsize=512)
@_ls_traceable(name="entity-prefilter-llm", run_type="llm")
def _llm_detect_entities(query: str) -> tuple[str, ...]:
    """Map a paraphrased query onto the canonical menu via the LLM (closed-set).

    Only fires when dictionary detection found nothing AND ENTITY_PREFILTER_LLM is
    on. Cached per query so the retrieve-node trace re-derivation reuses it (no
    second LLM call). Output is validated against the allowlist — the LLM cannot
    invent a filter that is not a known canonical.
    """
    from agentic_rag.core.contracts import LLMCompletionInput
    from agentic_rag.ingestion.metadata import allowlisted_canonicals, build_entity_menu
    from agentic_rag.model_runtime.errors import ModelInvocationError
    from agentic_rag.model_runtime.factory import get_llm_client

    menu = build_entity_menu()
    if not menu:
        return ()
    client = get_llm_client("query_rewrite")
    if client is None:
        return ()
    prompt = (
        f"<menu>\n{menu}\n</menu>\n"
        f"<query>{query}</query>\n"
        "Trả về JSON array các tên CHÍNH XÁC trong <menu> mà câu hỏi đề cập, kể cả khi "
        "diễn đạt khác. Ví dụ: 'Vinfast 8' → 'VF 8', 'Vinfast 9' → 'VF 9', "
        "'SUV điện 7 chỗ' → 'VF 9'. Nếu không có entity nào liên quan thì trả []."
    )
    try:
        response = client.complete(
            LLMCompletionInput(prompt=prompt, system_message=_ENTITY_LLM_SYSTEM, temperature=0.0)
        )
    except ModelInvocationError:
        return ()
    allow = allowlisted_canonicals()
    out: list[str] = []
    seen: set[str] = set()
    for item in _parse_str_array(response.text):
        if item in allow and item not in seen:
            seen.add(item)
            out.append(item)
    return tuple(out)


def _entity_prefilter_for(query: str) -> list[str] | None:
    """Detect filter-worthy canonical entities in the query (None = no pre-filter).

    Dictionary lookup first (free, catches direct mentions). If that finds nothing
    and ENTITY_PREFILTER_LLM is on, an LLM maps a paraphrased query onto the menu.
    """
    if not _hard_filter_enabled():
        return None
    from agentic_rag.ingestion.metadata import detect_in_query

    entities = detect_in_query(query)
    if not entities and _entity_prefilter_llm_enabled():
        entities = list(_llm_detect_entities(query))
    return entities or None


@_ls_traceable(name="entity-prefilter", run_type="tool")
def _trace_entity_prefilter(summary: dict[str, object]) -> dict[str, object]:
    """Emit the entity pre-filter decision to LangSmith (entities, count, fallback)."""
    return summary


@_ls_traceable(name="question-index", run_type="retriever")
def _trace_question_index(summary: dict[str, object]) -> dict[str, object]:
    """Emit the question-index retriever decision to LangSmith.

    A span only appears when ``RETRIEVAL_QUESTION_INDEX_ENABLED`` is on, so an
    absent span = feature off. Carries the inputs/outputs needed to judge whether
    it helped: indexed chunk count, how many question matches survived
    ``QUESTION_MIN_SCORE``, and the hybrid→fused result counts.
    """
    return summary


def _fusion_method() -> str:
    """Active fusion strategy (question-index only fuses under classic RRF)."""
    return os.getenv("FUSION_METHOD", "rrf").strip().lower()


# One in-memory question Store per Qdrant collection. Built by scrolling the whole
# collection once (chunk questions only change on re-ingest), so the first query
# with RETRIEVAL_QUESTION_INDEX_ENABLED pays the build cost and later queries reuse
# it. Cleared on process restart.
_QDRANT_QUESTION_STORE: dict[str, Any] = {}
_QDRANT_QUESTION_STORE_LOCK = Lock()


def _qdrant_question_store(client: Any, collection: str) -> Any:
    """Return a cached in-memory :class:`Store` over the collection's chunks.

    Scrolls every payload once and rebuilds ``Chunk`` objects (carrying their
    ``questions`` metadata) so :meth:`Store.question_search` can match the query
    against chunk questions — the question-index retriever, wired into the Qdrant
    path. Expensive on first call (loads + embeds all questions); cached after.
    """
    cached = _QDRANT_QUESTION_STORE.get(collection)
    if cached is not None:
        return cached
    with _QDRANT_QUESTION_STORE_LOCK:
        cached = _QDRANT_QUESTION_STORE.get(collection)
        if cached is not None:
            return cached
        chunks: list[Chunk] = []
        offset = None
        while True:
            batch, offset = client.scroll(
                collection_name=collection,
                limit=250,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in batch:
                payload = getattr(point, "payload", None)
                if isinstance(payload, dict):
                    chunks.append(_chunk_from_qdrant_payload(payload))
            if offset is None:
                break
        store = Store(chunks)
        _QDRANT_QUESTION_STORE[collection] = store
        return store


def _qdrant_collection_exists(client: Any, collection: str) -> bool:
    """True if ``collection`` exists in Qdrant (handles client API variants)."""
    exists = getattr(client, "collection_exists", None)
    if callable(exists):
        with contextlib.suppress(Exception):
            return bool(exists(collection))
    get_collection = getattr(client, "get_collection", None)
    if not callable(get_collection):
        return False
    try:
        get_collection(collection)
        return True
    except Exception:
        return False


def _question_point_id(parent_chunk_id: str, question_index: int) -> str:
    """Deterministic id for one question point (stable across re-runs)."""
    return str(uuid5(NAMESPACE_URL, f"question:{parent_chunk_id}::{question_index}"))


def _ensure_question_collection(
    *, client: Any, collection: str, embedding_profile: EmbeddingProfile, models: Any
) -> None:
    """Create the dense-only auxiliary questions collection if missing (idempotent)."""
    if _qdrant_collection_exists(client, collection):
        return
    create_collection = getattr(client, "create_collection", None)
    if not callable(create_collection):
        raise RuntimeError("Qdrant client must implement create_collection.")
    create_collection(
        collection_name=collection,
        vectors_config={
            "dense": models.VectorParams(
                size=embedding_profile.dimensions,
                distance=models.Distance.COSINE,
            )
        },
    )


def upsert_question_index(
    chunks: list[Chunk] | None = None, *, batch_size: int = 128
) -> dict[str, object]:
    """Build/refresh the auxiliary Qdrant collection of per-question embeddings.

    One point per chunk question, dense-embedded. The payload carries the parent
    chunk (``chunk_id``/``text``/``metadata``) so a query-time hit reconstructs the
    parent chunk directly — no second lookup into the main collection. Persistent,
    so unlike the in-memory index it survives restarts and costs the embedding pass
    only once.

    ``chunks=None`` scrolls the main collection and rebuilds chunks from payloads.
    Idempotent: point ids are deterministic, so re-running overwrites in place.
    """
    config = _vector_store_config()
    if config.provider != "qdrant" or config.url is None:
        raise ValueError("VECTOR_STORE_PROVIDER=qdrant requires VECTOR_STORE_URL.")
    try:
        from qdrant_client import models
    except ImportError as exc:
        raise RuntimeError("VECTOR_STORE_PROVIDER=qdrant requires qdrant-client.") from exc

    client = _qdrant_client(config)
    questions_collection = _question_index_collection()

    if chunks is None:
        chunks = []
        offset = None
        while True:
            batch, offset = client.scroll(
                collection_name=config.collection,
                limit=250,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in batch:
                payload = getattr(point, "payload", None)
                if isinstance(payload, dict):
                    chunks.append(_chunk_from_qdrant_payload(payload))
            if offset is None:
                break

    pairs: list[tuple[Chunk, int, str]] = []
    for chunk in chunks:
        questions = chunk.metadata.get("questions")
        if not isinstance(questions, (list, tuple)):
            continue
        for q_index, question in enumerate(list(questions)[:MAX_QUESTIONS_PER_CHUNK]):
            text = str(question).strip()
            if text:
                pairs.append((chunk, q_index, text))

    if not pairs:
        return {
            "enabled": True,
            "questions_collection": questions_collection,
            "indexed_questions": 0,
        }

    embedding = _configured_embedding()
    embedding_config = resolve_embedding_config()
    indexed = 0
    ensured = False
    for start in range(0, len(pairs), batch_size):
        batch_pairs = pairs[start : start + batch_size]
        vectors = _embed_documents(embedding, [text for _, _, text in batch_pairs])
        if not ensured:
            embedding_profile = _validate_embedding_vectors(vectors, config=embedding_config)
            _ensure_question_collection(
                client=client,
                collection=questions_collection,
                embedding_profile=embedding_profile,
                models=models,
            )
            ensured = True
        points = [
            models.PointStruct(
                id=_question_point_id(chunk.chunk_id, q_index),
                vector={"dense": vector},
                payload={
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "metadata": dict(chunk.metadata),
                    "question_text": text,
                },
            )
            for (chunk, q_index, text), vector in zip(batch_pairs, vectors, strict=True)
        ]
        client.upsert(collection_name=questions_collection, points=points)
        indexed += len(points)

    return {
        "enabled": True,
        "questions_collection": questions_collection,
        "indexed_questions": indexed,
    }


def question_index_status() -> dict[str, object]:
    """Report whether the auxiliary question collection exists and its point count."""
    config = _vector_store_config()
    collection = _question_index_collection()
    if config.provider != "qdrant" or config.url is None:
        return {"enabled": False, "exists": False, "count": 0, "collection": collection}
    client = _qdrant_client(config)
    if not _qdrant_collection_exists(client, collection):
        return {"enabled": True, "exists": False, "count": 0, "collection": collection}
    count = 0
    with contextlib.suppress(Exception):
        info = client.get_collection(collection)
        count = int(getattr(info, "points_count", 0) or 0)
    return {"enabled": True, "exists": True, "count": count, "collection": collection}


def _qdrant_native_question_search(
    client: Any, query: str, top_k: int, *, dense_vector: list[float] | None = None
) -> list[SearchResult] | None:
    """Query the auxiliary questions collection; ``None`` if it does not exist.

    Maps each question hit back to its parent chunk (dedup to the best score per
    parent), applies ``QUESTION_MIN_SCORE``, and rebuilds parent chunks from the
    denormalized payload — so no second lookup into the main collection.

    ``dense_vector`` lets the caller pass the query embedding already computed for
    the main hybrid search, so the query is embedded once and reused for both (the
    questions collection uses the same embedding model as the main collection).
    """
    collection = _question_index_collection()
    if not _qdrant_collection_exists(client, collection):
        return None
    if top_k <= 0:
        return []
    if dense_vector is None:
        dense_vector = _embed_query(_configured_embedding(), query)
    response = client.query_points(
        collection_name=collection,
        query=dense_vector,
        using="dense",
        limit=top_k * MAX_QUESTIONS_PER_CHUNK,
        with_payload=True,
    )
    raw_points = getattr(response, "points", response)
    if not isinstance(raw_points, Iterable):
        return []
    min_score = _question_min_score()
    best_by_parent: dict[str, tuple[float, dict[str, object]]] = {}
    for point in raw_points:
        payload = getattr(point, "payload", {})
        if not isinstance(payload, dict):
            continue
        score = float(getattr(point, "score", 0.0))
        if min_score is not None and score < min_score:
            continue
        parent_id = str(payload.get("chunk_id") or "")
        if not parent_id:
            continue
        if parent_id not in best_by_parent or score > best_by_parent[parent_id][0]:
            best_by_parent[parent_id] = (score, payload)
    ranked = sorted(best_by_parent.values(), key=lambda item: item[0], reverse=True)[:top_k]
    return [
        SearchResult(
            chunk=_chunk_from_qdrant_payload(payload),
            score=score,
            rank=rank,
            retriever="question",
        )
        for rank, (score, payload) in enumerate(ranked, start=1)
    ]


def qdrant_hybrid_search(
    query: str,
    *,
    document_ids: list[str] | None = None,
    top_k: int = 10,
    exclude_dedup_layers: list[str] | None = None,
    entity_filter: list[str] | None = None,
) -> list[SearchResult]:
    """Run Qdrant-backed hybrid retrieval and return shared search results.

    ``entity_filter`` carries canonical entities detected upstream (preprocess
    node) — a list (possibly empty = "no entities, don't filter"). When it is
    ``None`` (direct callers / tests), entities are self-detected from the query
    via :func:`_entity_prefilter_for`. A non-empty filter pre-filters the Qdrant
    search to chunks whose ``entities_canonical`` contains any of them (union);
    if that returns nothing, the search is retried unfiltered.
    """

    if top_k <= 0:
        return []
    vector_config = _vector_store_config()
    if vector_config.provider != "qdrant" or vector_config.url is None:
        raise ValueError("VECTOR_STORE_PROVIDER=qdrant requires VECTOR_STORE_URL.")
    collection = vector_config.collection
    embedding_config = resolve_embedding_config()
    embedding = _configured_embedding()
    dense_vector = _embed_query(embedding, query)
    embedding_profile = _validate_embedding_vectors([dense_vector], config=embedding_config)
    sparse_vector = _sparse_vector(query)
    client = _qdrant_client(vector_config)
    _validate_qdrant_collection(
        client=client,
        collection=collection,
        embedding_profile=embedding_profile,
    )

    def _run(entity_filter: list[str] | None) -> list[SearchResult]:
        response = _query_qdrant_points(
            client=client,
            collection=collection,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            embedding_profile=embedding_profile,
            document_ids=document_ids,
            top_k=top_k,
            exclude_dedup_layers=exclude_dedup_layers,
            entity_filter=entity_filter,
        )
        raw_points = getattr(response, "points", response)
        if not isinstance(raw_points, Iterable):
            return []
        out: list[SearchResult] = []
        for rank, point in enumerate(raw_points, start=1):
            payload = getattr(point, "payload", {})
            if not isinstance(payload, dict):
                payload = {}
            out.append(
                SearchResult(
                    chunk=_chunk_from_qdrant_payload(payload),
                    score=float(getattr(point, "score", 0.0)),
                    rank=rank,
                    retriever="hybrid",
                )
            )
        return out

    # None = caller did not pre-detect (direct call/test) -> self-detect here.
    # A list (incl. empty) = decision made upstream; respect it as-is.
    if entity_filter is None:
        entity_filter = _entity_prefilter_for(query) or []
    results = _run(entity_filter or None)
    # Fallback: an entity pre-filter that returns nothing must not blank out the
    # query — drop the filter and search the full corpus instead.
    used_fallback = False
    if entity_filter and not results:
        results = _run(None)
        used_fallback = True
    if entity_filter:
        _trace_entity_prefilter(
            {
                "query": query,
                "entities": entity_filter,
                "result_count": len(results),
                "fallback_unfiltered": used_fallback,
            }
        )
    # Question-index retriever as a 3rd RRF path (off by default). Matches the
    # query against each chunk's questions and fuses the parent chunks with the
    # hybrid results. Only under classic RRF, mirroring the linear path. Emits a
    # "question-index" span to LangSmith whenever the toggle is on.
    fusion_method = _fusion_method()
    hybrid_results = list(results)  # dense+sparse, captured before question/graph fusion
    question_results: list[SearchResult] = []  # filled if question-index channel runs
    graph_results: list[SearchResult] = []  # filled if graph channel runs
    if _question_index_enabled() and fusion_method == "rrf":
        hybrid_count = len(results)
        question_results = []
        store_chunks = 0
        source = "qdrant_native"
        error: str | None = None
        try:
            # Prefer the persistent auxiliary collection; fall back to the
            # in-memory index when it has not been built yet. Reuse the query
            # embedding already computed for the hybrid search above.
            native = _qdrant_native_question_search(client, query, top_k, dense_vector=dense_vector)
            if native is None:
                source = "in_memory"
                store = _qdrant_question_store(client, collection)
                store_chunks = len(store._chunks)
                question_results = store.question_search(query, top_k)
            else:
                question_results = native
        except Exception as exc:  # pragma: no cover - defensive, never blank the answer
            error = repr(exc)
        if question_results:
            from agentic_rag.retrieval.fusion_strategies import rrf_fusion_nway

            results = rrf_fusion_nway([results, question_results], top_k=top_k)
        _trace_question_index(
            {
                "query": query,
                "enabled": True,
                "source": source,
                "fusion_method": fusion_method,
                "min_score": _question_min_score(),
                "store_chunks": store_chunks,
                "question_hits": len(question_results),
                "hybrid_count": hybrid_count,
                "fused_count": len(results),
                "chunks": _trace_chunks(question_results),
                "error": error,
            }
        )
    # Knowledge-graph retriever as a 4th RRF path (off by default). Links the query to
    # graph entities, traverses, and fuses the provenance chunks with the rest. Emits a
    # "graph-retrieval" span to LangSmith whenever the toggle is on.
    if _graph_retrieval_enabled() and fusion_method == "rrf":
        hybrid_count = len(results)
        graph_results = []
        anchors = 0
        error = None  # type reuses the str|None annotation from the question-index block
        try:
            graph_results, anchors = _graph_search(query, client, collection, top_k)
            if graph_results:
                from agentic_rag.retrieval.fusion_strategies import rrf_fusion_nway

                results = rrf_fusion_nway([results, graph_results], top_k=top_k)
        except Exception as exc:
            error = repr(exc)
        _trace_graph_retrieval(
            {
                "query": query,
                "enabled": True,
                "fusion_method": fusion_method,
                "anchors": anchors,
                "graph_hits": len(graph_results),
                "hybrid_count": hybrid_count,
                "fused_count": len(results),
                "chunks": _trace_chunks(graph_results),
                "error": error,
            }
        )
    # One span listing every channel's chunks + the final fused list (with source tags).
    if fusion_method == "rrf" and (_question_index_enabled() or _graph_retrieval_enabled()):
        _trace_fusion(
            {
                "query": query,
                # ── INPUT: chunks from each channel that feeds RRF ──
                "input_counts": {
                    "hybrid_dense_sparse": len(hybrid_results),
                    "question_index": len(question_results),
                    "graph": len(graph_results),
                },
                "hybrid_chunks": _trace_chunks(hybrid_results),
                "question_chunks": _trace_chunks(question_results),
                "graph_chunks": _trace_chunks(graph_results),
                # ── OUTPUT: the fused ranked list (each chunk tagged w/ its source channels) ──
                "final_chunks": _trace_chunks(results),
                "final_count": len(results),
            }
        )
    return results


def embed_chunk_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts once with the configured dense embedding runtime (batched).

    Returned vectors can be passed back into ``upsert_dense_embeddings`` via
    ``precomputed_dense_vectors`` so upload-time dedup and indexing share a
    single embedding pass.
    """
    import os
    import time

    if not texts:
        return []
    batch_size = max(int(os.environ.get("DENSE_EMBED_BATCH_SIZE", "50")), 1)
    batch_delay = float(os.environ.get("DENSE_EMBED_BATCH_DELAY_SECONDS", "0"))
    embedding = _configured_embedding()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        vectors.extend(_embed_documents(embedding, texts[start : start + batch_size]))
        if batch_delay > 0 and start + batch_size < len(texts):
            time.sleep(batch_delay)
    return vectors


def qdrant_similar_by_vectors(
    vectors: list[list[float]],
    *,
    exclude_document_id: str | None = None,
    score_threshold: float = 0.92,
    top_k: int = 5,
) -> list[list[dict[str, object]]]:
    """Return indexed chunks similar to each supplied dense vector.

    Dense-only HNSW query with raw cosine scores (the collection distance), so
    callers can apply a similarity threshold — unlike ``qdrant_hybrid_search``
    whose RRF-fused scores are rank-based.
    """
    if not vectors:
        return []
    config = _vector_store_config()
    if config.provider != "qdrant" or config.url is None:
        raise ValueError("VECTOR_STORE_PROVIDER=qdrant requires VECTOR_STORE_URL.")
    try:
        from qdrant_client import models
    except ImportError as exc:
        raise RuntimeError("VECTOR_STORE_PROVIDER=qdrant requires qdrant-client.") from exc

    client = _qdrant_client(config)
    query_filter = None
    if exclude_document_id:
        query_filter = models.Filter(
            must_not=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=exclude_document_id),
                )
            ]
        )

    hits_per_vector: list[list[dict[str, object]]] = []
    for vector in vectors:
        response = client.query_points(
            collection_name=config.collection,
            query=vector,
            using="dense",
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=query_filter,
            with_payload=True,
        )
        raw_points = getattr(response, "points", response)
        hits: list[dict[str, object]] = []
        if isinstance(raw_points, Iterable):
            for point in raw_points:
                payload = getattr(point, "payload", {})
                if not isinstance(payload, dict):
                    payload = {}
                hits.append(
                    {
                        "chunk_id": str(payload.get("chunk_id") or ""),
                        "document_id": str(payload.get("document_id") or ""),
                        "score": float(getattr(point, "score", 0.0)),
                    }
                )
        hits_per_vector.append(hits)
    return hits_per_vector


def delete_qdrant_document_points(document_id: str) -> dict[str, object]:
    """Delete Qdrant points belonging to one source document."""

    config = _vector_store_config()
    vector_store = config.provider
    if vector_store != "qdrant":
        return {"enabled": False, "vector_store": vector_store}
    client = _qdrant_client(config)
    try:
        _delete_qdrant_points(
            client=client,
            collection=config.collection,
            document_ids=[document_id],
        )
    except Exception as exc:
        if not _is_qdrant_not_found(exc):
            raise
    return {
        "enabled": True,
        "vector_store": "qdrant",
        "collection": config.collection,
        "document_id": document_id,
        "deleted": True,
    }


def delete_all_qdrant_points() -> dict[str, object]:
    """Delete all Qdrant points in the configured collection."""

    config = _vector_store_config()
    vector_store = config.provider
    if vector_store != "qdrant":
        return {"enabled": False, "vector_store": vector_store}
    client = _qdrant_client(config)
    try:
        _delete_qdrant_points(
            client=client,
            collection=config.collection,
            document_ids=None,
        )
    except Exception as exc:
        if not _is_qdrant_not_found(exc):
            raise
    return {
        "enabled": True,
        "vector_store": "qdrant",
        "collection": config.collection,
        "deleted": True,
    }


def delete_qdrant_document_questions(document_id: str) -> dict[str, object]:
    """Delete one document's points from the auxiliary question collection.

    Question points denormalize the parent chunk, so they must be removed when the
    document is deleted — otherwise a query hit would surface stale/deleted content.
    Best-effort: a missing side collection is a no-op (returns ``skipped``).
    """
    config = _vector_store_config()
    if config.provider != "qdrant":
        return {"enabled": False, "vector_store": config.provider}
    client = _qdrant_client(config)
    collection = _question_index_collection()
    if not _qdrant_collection_exists(client, collection):
        return {"enabled": True, "questions_collection": collection, "skipped": "absent"}
    try:
        from qdrant_client import models
    except ImportError as exc:
        raise RuntimeError("VECTOR_STORE_PROVIDER=qdrant requires qdrant-client.") from exc
    delete = getattr(client, "delete", None)
    if not callable(delete):
        raise RuntimeError("Qdrant client must implement delete.")
    selector = models.Filter(
        must=[
            models.FieldCondition(
                key="metadata.document_id", match=models.MatchValue(value=document_id)
            )
        ]
    )
    try:
        delete(
            collection_name=collection,
            points_selector=models.FilterSelector(filter=selector),
            wait=True,
        )
    except Exception as exc:
        if not _is_qdrant_not_found(exc):
            raise
    return {
        "enabled": True,
        "questions_collection": collection,
        "document_id": document_id,
        "deleted": True,
    }


def delete_all_qdrant_questions() -> dict[str, object]:
    """Delete every point in the auxiliary question collection (best-effort)."""
    config = _vector_store_config()
    if config.provider != "qdrant":
        return {"enabled": False, "vector_store": config.provider}
    client = _qdrant_client(config)
    collection = _question_index_collection()
    if not _qdrant_collection_exists(client, collection):
        return {"enabled": True, "questions_collection": collection, "skipped": "absent"}
    try:
        _delete_qdrant_points(client=client, collection=collection, document_ids=None)
    except Exception as exc:
        if not _is_qdrant_not_found(exc):
            raise
    return {"enabled": True, "questions_collection": collection, "deleted": True}


def update_qdrant_payload(chunks: list[Chunk]) -> dict[str, object]:
    """Update only the payload metadata of existing Qdrant points (no re-embed).

    Backfilling LLM ``[L]`` metadata changes the payload but not the chunk text,
    so the stored dense vector is already correct. ``set_payload`` merges the new
    ``metadata`` dict into each existing point — keeping the vector and the
    ``_embedding_profile`` untouched — instead of paying for a redundant
    embedding pass via :func:`upsert_dense_embeddings`.

    Point ids are derived deterministically (``_qdrant_point_id``) from each
    chunk's storage id, so they match the points written at ingest time.
    """

    config = _vector_store_config()
    if config.provider != "qdrant" or config.url is None:
        raise ValueError("VECTOR_STORE_PROVIDER=qdrant requires VECTOR_STORE_URL.")
    if not chunks:
        return {
            "enabled": True,
            "vector_store": "qdrant",
            "updated_points": 0,
            "collection": config.collection,
        }

    client = _qdrant_client(config)
    updated = 0
    for index, chunk in enumerate(chunks, start=1):
        point_id = _qdrant_point_id(chunk=chunk, fallback_index=index)
        client.set_payload(
            collection_name=config.collection,
            payload={"metadata": dict(chunk.metadata)},
            points=[point_id],
            wait=True,
        )
        updated += 1
    return {
        "enabled": True,
        "vector_store": "qdrant",
        "updated_points": updated,
        "collection": config.collection,
    }


def reupsert_qdrant_sparse(batch_size: int = 250) -> dict[str, object]:
    """Recompute and overwrite every point's sparse vector (no dense re-embed).

    The BM25 keyword augmentation (``RETRIEVAL_BM25_AUGMENT_KEYWORDS``) only
    changes the *document-side* sparse vector, which Qdrant stores at ingest time.
    Toggling the flag has no effect on an existing collection until the sparse
    vectors are rebuilt — that is what this does: scroll every point, recompute
    ``_sparse_vector(_bm25_index_text(chunk))`` (honouring the flag's current
    value), and ``update_vectors`` only the ``sparse`` named vector. Dense vectors
    and payloads are left untouched.

    Run with ``RETRIEVAL_BM25_AUGMENT_KEYWORDS=true`` to switch augmentation ON for
    the collection, or with it ``false`` to revert to text-only sparse.
    """

    config = _vector_store_config()
    if config.provider != "qdrant" or config.url is None:
        raise ValueError("VECTOR_STORE_PROVIDER=qdrant requires VECTOR_STORE_URL.")
    try:
        from qdrant_client import models
    except ImportError as exc:
        raise RuntimeError("VECTOR_STORE_PROVIDER=qdrant requires qdrant-client.") from exc

    client = _qdrant_client(config)
    collection = config.collection
    updated = 0
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=collection,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        point_vectors = []
        for point in batch:
            payload = getattr(point, "payload", None)
            if not isinstance(payload, dict):
                continue
            chunk = _chunk_from_qdrant_payload(payload)
            sparse_vector = _sparse_vector(_bm25_index_text(chunk))
            point_vectors.append(
                models.PointVectors(
                    id=point.id,
                    vector={
                        "sparse": models.SparseVector(
                            indices=[int(v) for v in sparse_vector["indices"]],
                            values=[float(v) for v in sparse_vector["values"]],
                        )
                    },
                )
            )
        if point_vectors:
            client.update_vectors(collection_name=collection, points=point_vectors, wait=True)
            updated += len(point_vectors)
        if offset is None:
            break
    return {
        "enabled": True,
        "vector_store": "qdrant",
        "updated_points": updated,
        "collection": collection,
        "augment_keywords": _bm25_augment_keywords(),
    }


def ensure_entity_canonical_index() -> dict[str, object]:
    """Create the Qdrant keyword index on ``metadata.entities_canonical`` (idempotent).

    Required so the query-time entity pre-filter (``MatchAny`` on canonical
    entities) runs against an index instead of a full scan. Safe to call repeatedly.
    """
    config = _vector_store_config()
    if config.provider != "qdrant" or config.url is None:
        raise ValueError("VECTOR_STORE_PROVIDER=qdrant requires VECTOR_STORE_URL.")
    client = _qdrant_client(config)
    create_payload_index = getattr(client, "create_payload_index", None)
    if not callable(create_payload_index):
        return {"created": False, "reason": "client lacks create_payload_index"}
    from qdrant_client import models

    with contextlib.suppress(Exception):
        create_payload_index(
            collection_name=config.collection,
            field_name=_QDRANT_ENTITIES_CANONICAL_FIELD,
            field_schema=models.PayloadSchemaType.KEYWORD,
            wait=True,
        )
    return {
        "created": True,
        "field": _QDRANT_ENTITIES_CANONICAL_FIELD,
        "collection": config.collection,
    }


def _upsert_qdrant_embeddings(
    chunks: list[Chunk],
    *,
    vector_config: VectorStoreConfig,
    use_validated_config: bool,
    precomputed_dense_vectors: list[list[float]] | None = None,
) -> dict[str, object]:
    import os
    import time

    if not chunks:
        return {
            "enabled": True,
            "vector_store": "qdrant",
            "chunk_count": 0,
            "collection": vector_config.collection,
        }

    batch_size = int(os.environ.get("DENSE_EMBED_BATCH_SIZE", "50"))
    batch_delay = float(os.environ.get("DENSE_EMBED_BATCH_DELAY_SECONDS", "0"))

    embedding_config = resolve_embedding_config()
    embedding = _configured_embedding() if precomputed_dense_vectors is None else None

    try:
        from qdrant_client import models
    except ImportError as exc:
        raise RuntimeError("VECTOR_STORE_PROVIDER=qdrant requires qdrant-client.") from exc

    embedding_profile: object = None
    collection = vector_config.collection
    client: Any = None

    for batch_start in range(0, len(chunks), batch_size):
        batch = chunks[batch_start : batch_start + batch_size]
        if precomputed_dense_vectors is not None:
            dense_vectors = precomputed_dense_vectors[batch_start : batch_start + batch_size]
        else:
            dense_vectors = _embed_documents(embedding, [c.text for c in batch])

        if client is None:
            client = (
                _qdrant_client(vector_config) if use_validated_config else _qdrant_client_from_env()
            )

        if embedding_profile is None:
            embedding_profile = _validate_embedding_vectors(dense_vectors, config=embedding_config)
            _ensure_qdrant_collection(
                client=client,
                collection=collection,
                embedding_profile=embedding_profile,
            )

        points = []
        for local_idx, chunk in enumerate(batch):
            global_idx = batch_start + local_idx + 1
            sparse_vector = _sparse_vector(_bm25_index_text(chunk))
            sparse_indices = sparse_vector["indices"]
            sparse_values = sparse_vector["values"]
            points.append(
                models.PointStruct(
                    id=_qdrant_point_id(chunk=chunk, fallback_index=global_idx),
                    vector={
                        "dense": dense_vectors[local_idx],
                        "sparse": models.SparseVector(
                            indices=[int(v) for v in sparse_indices],
                            values=[float(v) for v in sparse_values],
                        ),
                    },
                    payload=_qdrant_payload(
                        chunk=chunk,
                        fallback_index=global_idx,
                        embedding_profile=embedding_profile,  # type: ignore[arg-type]
                    ),
                )
            )
        client.upsert(collection_name=collection, points=points)

        if (
            precomputed_dense_vectors is None
            and batch_delay > 0
            and batch_start + batch_size < len(chunks)
        ):
            time.sleep(batch_delay)

    return {
        "enabled": True,
        "vector_store": "qdrant",
        "chunk_count": len(chunks),
        "collection": collection,
        **_embedding_trace_metadata(
            config=embedding_config,
            profile=embedding_profile,  # type: ignore[arg-type]
        ),
    }


def _qdrant_client_from_env() -> Any:
    config = _vector_store_config()
    return _qdrant_client(config)


def _qdrant_client(config: VectorStoreConfig) -> Any:
    if config.provider != "qdrant" or config.url is None:
        raise ValueError("VECTOR_STORE_PROVIDER=qdrant requires VECTOR_STORE_URL.")
    api_key = config.api_key.get_secret_value() if config.api_key is not None else None
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise RuntimeError("VECTOR_STORE_PROVIDER=qdrant requires qdrant-client.") from exc
    return QdrantClient(url=config.url.get_secret_value(), api_key=api_key)


def _ensure_qdrant_collection(
    *,
    client: Any,
    collection: str | None = None,
    embedding_profile: EmbeddingProfile,
) -> None:
    collection = collection or _configured_qdrant_collection()
    get_collection = getattr(client, "get_collection", None)
    if not callable(get_collection):
        raise RuntimeError("Qdrant client must implement get_collection.")
    try:
        collection_info = get_collection(collection)
    except Exception as exc:
        if not _is_qdrant_not_found(exc):
            raise
    else:
        _validate_qdrant_collection_info(
            client=client,
            collection=collection,
            collection_info=collection_info,
            embedding_profile=embedding_profile,
        )
        return

    create_collection = getattr(client, "create_collection", None)
    if not callable(create_collection):
        raise RuntimeError("Qdrant client must implement create_collection.")
    try:
        from qdrant_client import models
    except ImportError as exc:
        raise RuntimeError("VECTOR_STORE_PROVIDER=qdrant requires qdrant-client.") from exc
    create_collection(
        collection_name=collection,
        vectors_config={
            "dense": models.VectorParams(
                size=embedding_profile.dimensions,
                distance=models.Distance.COSINE,
            )
        },
        sparse_vectors_config={"sparse": models.SparseVectorParams()},
    )
    _ensure_qdrant_payload_indexes(client=client, collection=collection, models=models)


def _validate_qdrant_collection(
    *,
    client: Any,
    collection: str,
    embedding_profile: EmbeddingProfile,
) -> None:
    get_collection = getattr(client, "get_collection", None)
    if not callable(get_collection):
        raise RuntimeError("Qdrant client must implement get_collection.")
    try:
        collection_info = get_collection(collection)
    except Exception as exc:
        if _is_qdrant_not_found(exc):
            raise ValueError(
                f"Qdrant collection {collection!r} does not exist. "
                "Ingest a document before querying."
            ) from exc
        raise
    _validate_qdrant_collection_info(
        client=client,
        collection=collection,
        collection_info=collection_info,
        embedding_profile=embedding_profile,
    )


def _ensure_qdrant_payload_indexes(*, client: Any, collection: str, models: Any) -> None:
    """Create keyword indexes required by retrieval filters (idempotent)."""
    create_payload_index = getattr(client, "create_payload_index", None)
    if not callable(create_payload_index):
        return
    for field_name in _QDRANT_KEYWORD_PAYLOAD_INDEX_FIELDS:
        with contextlib.suppress(Exception):
            create_payload_index(
                collection_name=collection,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )


def _validate_qdrant_collection_info(
    *,
    client: Any,
    collection: str,
    collection_info: object,
    embedding_profile: EmbeddingProfile,
) -> None:
    stored_dimensions = _qdrant_dense_vector_size(collection_info)
    if stored_dimensions != embedding_profile.dimensions:
        raise ValueError(
            f"Qdrant collection {collection!r} dense dimension is {stored_dimensions}, "
            f"but the active embedding dimension is {embedding_profile.dimensions}. "
            "Change VECTOR_STORE_COLLECTION or delete the collection and reindex."
        )

    stored_profile = _qdrant_stored_embedding_profile(client, collection=collection)
    if stored_profile is None:
        return
    expected_profile = _embedding_profile_payload(embedding_profile)
    if stored_profile != expected_profile:
        raise ValueError(
            f"Qdrant collection {collection!r} embedding profile is incompatible: "
            f"stored={stored_profile}, active={expected_profile}. "
            "Change VECTOR_STORE_COLLECTION or delete the collection and reindex."
        )

    try:
        from qdrant_client import models

        _ensure_qdrant_payload_indexes(client=client, collection=collection, models=models)
    except Exception:
        pass


def _qdrant_dense_vector_size(collection_info: object) -> int:
    config = getattr(collection_info, "config", None)
    params = getattr(config, "params", None)
    vectors = getattr(params, "vectors", None)
    dense_config = vectors.get("dense") if isinstance(vectors, dict) else None
    size = getattr(dense_config, "size", None)
    if not isinstance(size, int) or size <= 0:
        raise ValueError(
            "Qdrant collection does not expose the required named dense vector. "
            "Change VECTOR_STORE_COLLECTION or delete the collection and reindex."
        )
    return size


def _qdrant_stored_embedding_profile(
    client: Any,
    *,
    collection: str,
) -> dict[str, object] | None:
    scroll = getattr(client, "scroll", None)
    if not callable(scroll):
        raise RuntimeError("Qdrant client must implement scroll for profile validation.")
    response = scroll(
        collection_name=collection,
        limit=1,
        with_payload=True,
        with_vectors=False,
    )
    raw_points = (
        response[0] if isinstance(response, tuple) else getattr(response, "points", response)
    )
    if not isinstance(raw_points, Iterable):
        raise ValueError("Qdrant scroll returned an invalid response.")
    points = list(raw_points)
    if not points:
        return None
    payload = getattr(points[0], "payload", None)
    profile = payload.get("_embedding_profile") if isinstance(payload, dict) else None
    if not isinstance(profile, dict):
        raise ValueError(
            f"Qdrant collection {collection!r} contains legacy points "
            "without an embedding profile. Change VECTOR_STORE_COLLECTION or delete the "
            "collection and reindex."
        )
    return dict(profile)


def _is_qdrant_not_found(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 404:
        return True
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) == 404


def _query_qdrant_points(
    *,
    client: Any,
    collection: str,
    dense_vector: list[float],
    sparse_vector: dict[str, list[int] | list[float]],
    embedding_profile: EmbeddingProfile,
    document_ids: list[str] | None,
    top_k: int,
    exclude_dedup_layers: list[str] | None = None,
    entity_filter: list[str] | None = None,
) -> object:
    if type(client).__module__.startswith("qdrant_client"):
        try:
            from qdrant_client import models
        except ImportError:
            pass
        else:
            q_filter = _qdrant_combined_filter(
                document_ids,
                exclude_dedup_layers=exclude_dedup_layers,
                entity_filter=entity_filter,
                models=models,
            )
            sparse_indices = sparse_vector["indices"]
            sparse_values = sparse_vector["values"]
            if not all(isinstance(index, int) for index in sparse_indices):
                sparse_indices = []
            if not all(isinstance(value, float) for value in sparse_values):
                sparse_values = []
            return client.query_points(
                collection_name=collection,
                prefetch=[
                    models.Prefetch(
                        query=dense_vector,
                        using="dense",
                        limit=top_k,
                        filter=q_filter,
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_indices,
                            values=sparse_values,
                        ),
                        using="sparse",
                        limit=top_k,
                        filter=q_filter,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=top_k,
                with_payload=True,
            )
    return client.query_points(
        collection_name=collection,
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        document_ids=document_ids,
        limit=top_k,
        with_payload=True,
    )


def _delete_qdrant_points(
    *,
    client: Any,
    collection: str,
    document_ids: list[str] | None,
) -> None:
    delete = getattr(client, "delete", None)
    if not callable(delete):
        raise RuntimeError("Qdrant client must implement delete.")
    if type(client).__module__.startswith("qdrant_client"):
        try:
            from qdrant_client import models
        except ImportError:
            pass
        else:
            selector_filter = _qdrant_document_filter(document_ids, models=models)
            delete(
                collection_name=collection,
                points_selector=models.FilterSelector(filter=selector_filter),
                wait=True,
            )
            return
    delete(
        collection_name=collection,
        document_ids=document_ids,
        wait=True,
    )


def _qdrant_document_filter(document_ids: list[str] | None, *, models: Any) -> Any:
    if not document_ids:
        return models.Filter(must=[])
    if len(document_ids) == 1:
        match = models.MatchValue(value=document_ids[0])
    else:
        match = models.MatchAny(any=document_ids)
    return models.Filter(
        must=[
            models.FieldCondition(
                key=_QDRANT_DOCUMENT_ID_FIELD,
                match=match,
            )
        ]
    )


def _qdrant_combined_filter(
    document_ids: list[str] | None,
    *,
    exclude_dedup_layers: list[str] | None,
    entity_filter: list[str] | None = None,
    models: Any,
) -> Any:
    """Build a Qdrant filter that optionally restricts document_ids AND excludes
    chunks whose dedup primary_layer matches the given list.

    Chunks flagged by the selected layers have
    ``metadata.deduplication.primary_layer`` set in their Qdrant payload;
    non-duplicate chunks lack that field entirely and are unaffected.
    """
    must: list[Any] = []
    must_not: list[Any] = []

    if document_ids:
        match = (
            models.MatchValue(value=document_ids[0])
            if len(document_ids) == 1
            else models.MatchAny(any=document_ids)
        )
        must.append(models.FieldCondition(key=_QDRANT_DOCUMENT_ID_FIELD, match=match))

    if exclude_dedup_layers:
        must_not.append(
            models.FieldCondition(
                key=_QDRANT_DEDUP_PRIMARY_LAYER_FIELD,
                match=models.MatchAny(any=list(exclude_dedup_layers)),
            )
        )

    if entity_filter and _hard_filter_enabled():
        # Union (OR) across canonical entities: a chunk matches if it carries ANY
        # of them. Pre-filter only removes chunks about none of the entities.
        # Gated by the master kill-switch so entities extracted upstream (agent
        # path: LLM-extracted in preprocess_query, bypassing _entity_prefilter_for)
        # also stop filtering when HARD_FILTER_ENABLED is off.
        must.append(
            models.FieldCondition(
                key=_QDRANT_ENTITIES_CANONICAL_FIELD,
                match=models.MatchAny(any=list(entity_filter)),
            )
        )

    return models.Filter(must=must, must_not=must_not)


def _embed_documents(embedding: object, texts: list[str]) -> list[list[float]]:
    embed_documents = getattr(embedding, "embed_documents", None)
    if callable(embed_documents):
        vectors = embed_documents(texts)
        return [[float(value) for value in vector] for vector in vectors]
    embed_query = getattr(embedding, "embed_query", None)
    if callable(embed_query):
        return [[float(value) for value in embed_query(text)] for text in texts]
    raise TypeError("Embedding provider must implement embed_documents or embed_query.")


def _embed_query(embedding: object, query: str) -> list[float]:
    embed_query = getattr(embedding, "embed_query", None)
    if callable(embed_query):
        return [float(value) for value in embed_query(query)]
    return _embed_documents(embedding, [query])[0]


def _validate_embedding_vectors(
    vectors: list[list[float]],
    *,
    config: EmbeddingConfig,
) -> EmbeddingProfile:
    return validate_embedding_output(
        vectors,
        config=config,
        input_count=len(vectors),
        model_name=config.model,
    )


def _sparse_vector(text: str) -> dict[str, list[int] | list[float]]:
    counts = Counter(_tokenize(text))
    indices = [_stable_sparse_index(token) for token in counts]
    values = [float(count) for count in counts.values()]
    return {"indices": indices, "values": values}


def _stable_sparse_index(token: str) -> int:
    # Qdrant sparse vector indices must be unsigned integers. A deterministic
    # token hash is sufficient for the lightweight lexical signal used here.
    return int.from_bytes(sha256(token.encode()).digest()[:8], "big") % 2_147_483_647


def _qdrant_payload(
    *,
    chunk: Chunk,
    fallback_index: int,
    embedding_profile: EmbeddingProfile,
) -> dict[str, object]:
    metadata = chunk.metadata
    return {
        "document_id": str(metadata.get("document_id") or ""),
        "chunk_id": chunk.chunk_id,
        "storage_chunk_id": _dense_id(chunk=chunk, fallback_index=fallback_index),
        "source_type": str(metadata.get("source_type") or ""),
        "source": str(metadata.get("source") or ""),
        "url": metadata.get("url"),
        "page": metadata.get("page"),
        "section": metadata.get("section"),
        "text": chunk.text,
        "metadata": metadata,
        "_embedding_profile": _embedding_profile_payload(embedding_profile),
    }


def _embedding_profile_payload(profile: EmbeddingProfile) -> dict[str, object]:
    return {
        "schema_version": 1,
        "provider": profile.provider,
        "model": profile.model,
        "dimensions": profile.dimensions,
    }


def _embedding_trace_metadata(
    *,
    config: EmbeddingConfig,
    profile: EmbeddingProfile,
) -> dict[str, object]:
    return {
        "requested_provider": config.provider,
        "resolved_provider": config.provider,
        "fallback_reason": None,
        "model": profile.model,
        "dimensions": profile.dimensions,
    }


def _chunk_from_qdrant_payload(payload: dict[str, object]) -> Chunk:
    metadata = payload.get("metadata")
    chunk_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    payload_metadata_keys = (
        "document_id",
        "storage_chunk_id",
        "source_type",
        "source",
        "url",
        "page",
        "section",
    )
    for key in payload_metadata_keys:
        value = payload.get(key)
        if value is not None:
            chunk_metadata.setdefault(key, value)
    return Chunk(
        chunk_id=str(
            payload.get("chunk_id") or payload.get("storage_chunk_id") or "qdrant_unknown"
        ),
        text=str(payload.get("text") or ""),
        metadata=chunk_metadata,
    )


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
        _dense_id(chunk=chunk, fallback_index=index) for index, chunk in enumerate(chunks, start=1)
    ]


def _dense_id(*, chunk: Chunk, fallback_index: int) -> str:
    storage_chunk_id = chunk.metadata.get("storage_chunk_id")
    if isinstance(storage_chunk_id, str) and storage_chunk_id:
        return storage_chunk_id
    ingestion_id = chunk.metadata.get("chunk_id")
    if isinstance(ingestion_id, str) and ingestion_id:
        return ingestion_id
    document_id = str(chunk.metadata.get("document_id") or "document")
    return f"{document_id}:{fallback_index:04d}"


def _qdrant_point_id(*, chunk: Chunk, fallback_index: int) -> str:
    storage_id = _dense_id(chunk=chunk, fallback_index=fallback_index)
    return str(uuid5(NAMESPACE_URL, storage_id))


_DENSE_FILTER_MAX_IDS = 5


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
    # With many document_ids, a $in filter on JSONB is slower than a full collection scan.
    # Skip the filter and let pgvector use its vector index efficiently.
    if len(document_ids) > _DENSE_FILTER_MAX_IDS:
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
        chunk_id = str(metadata["chunk_id"])
        chunk_metadata = dict(nested_metadata) if isinstance(nested_metadata, dict) else {}
        chunk_metadata.setdefault("chunk_id", chunk_id)
        return Chunk(
            chunk_id=chunk_id,
            text=str(getattr(doc, "page_content", "")),
            metadata=chunk_metadata,
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
