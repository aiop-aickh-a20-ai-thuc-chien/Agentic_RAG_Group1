import json
import warnings
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from pytest import MonkeyPatch

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.metadata import QDRANT_INDEX_FIELDS
from agentic_rag.retrieval.search import (
    Store,
    _qdrant_client_from_env,
    delete_all_qdrant_points,
    delete_qdrant_document_points,
    qdrant_hybrid_search,
    upsert_dense_embeddings,
)

_VECTOR_STORE_ENV_NAMES = (
    "VECTOR_STORE_PROVIDER",
    "VECTOR_STORE_URL",
    "VECTOR_STORE_API_KEY",
    "VECTOR_STORE_COLLECTION",
    "DENSE_VECTOR_STORE",
    "DENSE_PGVECTOR_CONNECTION",
    "DENSE_PGVECTOR_COLLECTION",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_COLLECTION",
)


@pytest.fixture(autouse=True)
def _isolate_vector_store_env(monkeypatch: MonkeyPatch) -> None:
    for name in _VECTOR_STORE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DENSE_VECTOR_STORE", "turbovec")
    monkeypatch.setattr("agentic_rag.retrieval.config.load_local_env", lambda: None)


def test_preprocess_query_normalizes_vietnamese_text(monkeypatch: MonkeyPatch) -> None:
    class FakeOpenAI:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self._call_count = 0
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, *_args: object, **_kwargs: object) -> object:
            self._call_count += 1
            if self._call_count == 1:
                content = "decompose"
            else:
                content = json.dumps(
                    {
                        "method": "decompose",
                        "transformed_queries": ["bao hanh pin"],
                    }
                )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    store = Store([Chunk(chunk_id="c1", text="Pin cao ap", metadata={})])

    preprocessed = store.preprocess_query("  Bảo hành PIN  ")

    assert len(preprocessed) == 4


def test_bm25_search_returns_matching_chunk_not_loop_index() -> None:
    chunks = [
        Chunk(chunk_id="c1", text="lich bao duong lop xe", metadata={}),
        Chunk(chunk_id="c2", text="pin vf8 duoc bao hanh 8 nam", metadata={}),
    ]
    store = Store(chunks)

    results = store.bm25_search("pin bao hanh", top_k=2)

    assert results[0].chunk.chunk_id == "c2"
    assert results[0].retriever == "bm25"
    assert results[0].rank == 1


def test_bm25_indexes_text_only_by_default(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("RETRIEVAL_BM25_AUGMENT_KEYWORDS", raising=False)
    # "pin" lives only in metadata keywords, not in the chunk text.
    chunk = Chunk(
        chunk_id="c1",
        text="noi dung khong chua tu khoa muc tieu",
        metadata={"keywords": ["pin"]},
    )
    store = Store([chunk])

    results = store.bm25_search("pin", top_k=1)

    # Baseline indexes chunk.text only, so the keyword contributes nothing.
    assert results[0].score == 0.0


# Three chunks so the appended keyword lands in 1/3 docs → positive BM25 IDF
# (with 2 docs a 1/2-frequency term gets idf log(1)=0 and scores 0).
def test_bm25_augments_with_keywords_when_enabled(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVAL_BM25_AUGMENT_KEYWORDS", "true")
    chunks = [
        Chunk(chunk_id="c1", text="lich bao duong lop xe", metadata={}),
        Chunk(chunk_id="c2", text="huong dan thay the gat mua", metadata={}),
        Chunk(
            chunk_id="c3",
            text="noi dung khong chua tu khoa muc tieu",
            metadata={"keywords": ["pin"]},
        ),
    ]
    store = Store(chunks)

    results = store.bm25_search("pin", top_k=3)

    # The appended keyword makes c3 the only lexical match for "pin".
    assert results[0].chunk.chunk_id == "c3"
    assert results[0].score > 0.0


def test_question_search_disabled_by_default(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("RETRIEVAL_QUESTION_INDEX_ENABLED", raising=False)
    store = Store([Chunk(chunk_id="c1", text="noi dung", metadata={"questions": ["cau hoi"]})])

    assert store.question_search("bat ky", top_k=5) == []


def test_question_search_maps_to_parent_and_dedups(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVAL_QUESTION_INDEX_ENABLED", "true")
    monkeypatch.delenv("QUESTION_MIN_SCORE", raising=False)
    chunks = [
        Chunk(chunk_id="c1", text="a", metadata={"questions": ["q0"]}),
        Chunk(chunk_id="c2", text="b", metadata={"questions": ["q1a", "q1b"]}),
    ]
    store = Store(chunks)

    class FakeQuestionIndex:
        def similarity_search_with_score(self, *, query: str, k: int) -> list[tuple[Any, float]]:
            return [
                (SimpleNamespace(metadata={"parent_index": 1}), 0.9),
                (SimpleNamespace(metadata={"parent_index": 1}), 0.8),  # dup → keep best 0.9
                (SimpleNamespace(metadata={"parent_index": 0}), 0.6),
            ]

    monkeypatch.setattr(store, "_build_question_index", lambda chunks: FakeQuestionIndex())

    results = store.question_search("q", top_k=5)

    assert [r.chunk.chunk_id for r in results] == ["c2", "c1"]
    assert results[0].score == 0.9
    assert results[0].retriever == "question"
    assert results[0].rank == 1


def test_question_search_applies_min_score(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVAL_QUESTION_INDEX_ENABLED", "true")
    monkeypatch.setenv("QUESTION_MIN_SCORE", "0.5")
    chunks = [
        Chunk(chunk_id="c1", text="a", metadata={"questions": ["q0"]}),
        Chunk(chunk_id="c2", text="b", metadata={"questions": ["q1"]}),
    ]
    store = Store(chunks)

    class FakeQuestionIndex:
        def similarity_search_with_score(self, *, query: str, k: int) -> list[tuple[Any, float]]:
            return [
                (SimpleNamespace(metadata={"parent_index": 0}), 0.9),
                (SimpleNamespace(metadata={"parent_index": 1}), 0.3),  # below 0.5 → dropped
            ]

    monkeypatch.setattr(store, "_build_question_index", lambda chunks: FakeQuestionIndex())

    results = store.question_search("q", top_k=5)

    assert [r.chunk.chunk_id for r in results] == ["c1"]


def test_upsert_dense_embeddings_uses_stable_ids_without_deleting_collection(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    class FakePGVector:
        @classmethod
        def from_texts(cls, **kwargs: Any) -> object:
            calls.update(kwargs)
            return object()

    monkeypatch.setenv("DENSE_VECTOR_STORE", "pgvector")
    monkeypatch.setenv("DENSE_PGVECTOR_CONNECTION", "postgresql://example/rag")
    monkeypatch.setenv("DENSE_PGVECTOR_CONNECTION", "postgresql://example/rag")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("DENSE_PGVECTOR_CONNECTION", "postgresql://example")
    monkeypatch.setenv("DENSE_PGVECTOR_COLLECTION", "agentic_chunks")
    monkeypatch.setattr("agentic_rag.retrieval.search._configured_embedding", lambda: object())
    monkeypatch.setattr("langchain_postgres.PGVector", FakePGVector)
    chunks = [
        Chunk(
            chunk_id="c1",
            text="Pin VF8",
            metadata={"document_id": "doc-1", "storage_chunk_id": "doc-1:0001"},
        )
    ]

    trace = upsert_dense_embeddings(chunks)

    assert trace["enabled"] is True
    assert calls["ids"] == ["doc-1:0001"]
    assert calls["collection_name"] == "agentic_chunks"
    assert calls["pre_delete_collection"] is False
    assert calls["metadatas"][0]["document_id"] == "doc-1"
    assert calls["metadatas"][0]["chunk_id"] == "c1"


def test_upsert_dense_embeddings_uses_canonical_pgvector_configuration(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    class FakePGVector:
        @classmethod
        def from_texts(cls, **kwargs: Any) -> object:
            calls.update(kwargs)
            return object()

    monkeypatch.delenv("DENSE_VECTOR_STORE", raising=False)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "pgvector")
    monkeypatch.setenv("VECTOR_STORE_URL", "postgresql://example/rag")
    monkeypatch.setenv("VECTOR_STORE_COLLECTION", "canonical_chunks")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence_transformers")
    monkeypatch.setattr("agentic_rag.retrieval.search._configured_embedding", lambda: object())
    monkeypatch.setattr("langchain_postgres.PGVector", FakePGVector)

    trace = upsert_dense_embeddings(
        [
            Chunk(
                chunk_id="c1",
                text="Pin VF8",
                metadata={"document_id": "doc-1"},
            )
        ]
    )

    assert trace["enabled"] is True
    assert trace["collection"] == "canonical_chunks"
    assert calls["connection"] == "postgresql://example/rag"
    assert calls["collection_name"] == "canonical_chunks"


def test_pgvector_dense_search_filters_to_selected_documents(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    class FakeVectorIndex:
        def similarity_search_with_score(
            self,
            *,
            query: str,
            k: int,
            filter: dict[str, object] | None = None,
        ) -> list[tuple[object, float]]:
            seen["query"] = query
            seen["k"] = k
            seen["filter"] = filter
            return [
                (
                    SimpleNamespace(
                        page_content="Pin VF8",
                        metadata={
                            "chunk_id": "c1",
                            "metadata": {
                                "document_id": "doc-1",
                                "storage_chunk_id": "doc-1:0001",
                            },
                        },
                    ),
                    0.12,
                )
            ]

    monkeypatch.setenv("DENSE_VECTOR_STORE", "pgvector")
    monkeypatch.setenv("DENSE_PGVECTOR_CONNECTION", "postgresql://example/rag")
    chunks = [
        Chunk(
            chunk_id="c1",
            text="Pin VF8",
            metadata={"document_id": "doc-1", "storage_chunk_id": "doc-1:0001"},
        )
    ]
    store = Store(chunks)
    monkeypatch.setattr(store, "_build_vector_index", lambda chunks: FakeVectorIndex())

    results = store.dense_search("pin vf8", top_k=3)

    assert seen["filter"] == {"document_id": "doc-1"}
    assert results[0].chunk.metadata["chunk_id"] == "c1"
    assert results[0].chunk.metadata["document_id"] == "doc-1"


def test_qdrant_upsert_dense_embeddings_writes_dense_sparse_vectors_and_payload(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    class FakeEmbedding:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            calls["embedded_texts"] = texts
            return [[0.1, 0.2] for _ in texts]

    class FakeQdrantClient:
        def get_collection(self, collection_name: str) -> object:
            calls["get_collection"] = collection_name
            return SimpleNamespace(
                config=SimpleNamespace(
                    params=SimpleNamespace(
                        vectors={"dense": SimpleNamespace(size=2)},
                    )
                )
            )

        def scroll(self, **kwargs: Any) -> tuple[list[object], None]:
            calls["scroll"] = kwargs
            return ([], None)

        def upsert(self, *, collection_name: str, points: list[dict[str, Any]]) -> object:
            calls["collection_name"] = collection_name
            calls["points"] = points
            return object()

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "local-model")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._configured_embedding", lambda: FakeEmbedding()
    )
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client_from_env", lambda: FakeQdrantClient()
    )
    chunks = [
        Chunk(
            chunk_id="c1",
            text="Pin VF8 duoc bao hanh",
            metadata={
                "document_id": "doc-1",
                "storage_chunk_id": "doc-1:0001",
                "source_type": "pdf",
                "source": "warranty.pdf",
                "page": 3,
                "section": "Warranty",
            },
        )
    ]

    trace = upsert_dense_embeddings(chunks)

    point = calls["points"][0]
    assert trace["enabled"] is True
    assert trace["vector_store"] == "qdrant"
    assert trace["collection"] == "agentic_chunks"
    assert trace["requested_provider"] == "local"
    assert trace["resolved_provider"] == "local"
    assert trace["model"] == "local-model"
    assert trace["dimensions"] == 2
    assert str(UUID(str(point.id))) == str(point.id)
    assert point.vector["dense"] == [0.1, 0.2]
    assert point.vector["sparse"].indices
    assert point.payload["storage_chunk_id"] == "doc-1:0001"
    assert point.payload["document_id"] == "doc-1"
    assert point.payload["chunk_id"] == "c1"
    assert point.payload["text"] == "Pin VF8 duoc bao hanh"
    assert point.payload["page"] == 3
    assert point.payload["_embedding_profile"] == {
        "schema_version": 1,
        "provider": "local",
        "model": "local-model",
        "dimensions": 2,
    }


def test_qdrant_client_uses_canonical_url_and_api_key(monkeypatch: MonkeyPatch) -> None:
    seen: dict[str, str | None] = {}

    class FakeQdrantClient:
        def __init__(self, *, url: str, api_key: str | None = None) -> None:
            seen["url"] = url
            seen["api_key"] = api_key

    monkeypatch.delenv("DENSE_VECTOR_STORE", raising=False)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://canonical-qdrant.example")
    monkeypatch.setenv("VECTOR_STORE_API_KEY", "canonical-secret")
    monkeypatch.setattr("qdrant_client.QdrantClient", FakeQdrantClient)

    client = _qdrant_client_from_env()

    assert isinstance(client, FakeQdrantClient)
    assert seen == {
        "url": "https://canonical-qdrant.example",
        "api_key": "canonical-secret",
    }


def test_delete_all_qdrant_points_uses_canonical_provider_and_collection(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeQdrantClient:
        def delete(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    monkeypatch.delenv("DENSE_VECTOR_STORE", raising=False)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://canonical-qdrant.example")
    monkeypatch.setenv("VECTOR_STORE_COLLECTION", "canonical_chunks")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client", lambda config: FakeQdrantClient()
    )

    trace = delete_all_qdrant_points()

    assert trace["enabled"] is True
    assert trace["collection"] == "canonical_chunks"
    assert seen["collection_name"] == "canonical_chunks"


def test_qdrant_hybrid_search_filters_documents_and_reconstructs_search_results(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeEmbedding:
        def embed_query(self, text: str) -> list[float]:
            seen["embedded_query"] = text
            return [0.3, 0.4]

    class FakeQdrantClient:
        def get_collection(self, collection_name: str) -> object:
            seen["get_collection"] = collection_name
            return SimpleNamespace(
                config=SimpleNamespace(
                    params=SimpleNamespace(
                        vectors={"dense": SimpleNamespace(size=2)},
                    )
                )
            )

        def scroll(self, **kwargs: Any) -> tuple[list[object], None]:
            seen["scroll"] = kwargs
            return (
                [
                    SimpleNamespace(
                        payload={
                            "_embedding_profile": {
                                "schema_version": 1,
                                "provider": "local",
                                "model": "local-model",
                                "dimensions": 2,
                            }
                        }
                    )
                ],
                None,
            )

        def query_points(self, **kwargs: Any) -> object:
            seen.update(kwargs)
            point = SimpleNamespace(
                score=0.91,
                payload={
                    "chunk_id": "c1",
                    "text": "Pin VF8 duoc bao hanh",
                    "metadata": {
                        "document_id": "doc-1",
                        "storage_chunk_id": "doc-1:0001",
                        "source": "warranty.pdf",
                    },
                },
            )
            return SimpleNamespace(points=[point])

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "local-model")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._configured_embedding", lambda: FakeEmbedding()
    )
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client", lambda config: FakeQdrantClient()
    )
    # Isolate from the question-index path (and any leaked env flag) so only the
    # main hybrid query_points call is captured.
    monkeypatch.setenv("RETRIEVAL_QUESTION_INDEX_ENABLED", "false")

    results = qdrant_hybrid_search("pin vf8", document_ids=["doc-1"], top_k=3)

    assert seen["collection_name"] == "agentic_chunks"
    assert seen["document_ids"] == ["doc-1"]
    assert seen["limit"] == 3
    assert seen["dense_vector"] == [0.3, 0.4]
    assert seen["sparse_vector"]["indices"]
    assert results[0].chunk.chunk_id == "c1"
    assert results[0].chunk.text == "Pin VF8 duoc bao hanh"
    assert results[0].chunk.metadata["document_id"] == "doc-1"
    assert results[0].score == 0.91
    assert results[0].retriever == "hybrid"


def test_qdrant_upsert_creates_missing_collection_with_native_dimensions(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class NotFoundError(Exception):
        status_code = 404

    class FakeEmbedding:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2, 0.3] for _ in texts]

    class FakeQdrantClient:
        def get_collection(self, collection_name: str) -> object:
            raise NotFoundError(collection_name)

        def create_collection(self, **kwargs: Any) -> None:
            seen["create_collection"] = kwargs

        def create_payload_index(self, **kwargs: Any) -> None:
            seen.setdefault("payload_indexes", []).append(kwargs)

        def upsert(self, **kwargs: Any) -> None:
            seen["upsert"] = kwargs

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "local-model")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._configured_embedding",
        lambda: FakeEmbedding(),
    )
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client",
        lambda config: FakeQdrantClient(),
    )

    upsert_dense_embeddings(
        [
            Chunk(
                chunk_id="c1",
                text="Pin VF8",
                metadata={"document_id": "doc-1", "storage_chunk_id": "doc-1:0001"},
            )
        ]
    )

    dense_config = seen["create_collection"]["vectors_config"]["dense"]
    assert dense_config.size == 3
    assert [index["field_name"] for index in seen["payload_indexes"]] == list(QDRANT_INDEX_FIELDS)
    assert seen["upsert"]["collection_name"] == "agentic_chunks"


def test_qdrant_hybrid_search_filters_out_excluded_dedup_layers(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeEmbedding:
        def embed_query(self, text: str) -> list[float]:
            seen["embedded_query"] = text
            return [0.3, 0.4]

    class FakeQdrantClient:
        __module__ = "qdrant_client.fake"

        def get_collection(self, collection_name: str) -> object:
            seen["get_collection"] = collection_name
            return SimpleNamespace(
                config=SimpleNamespace(
                    params=SimpleNamespace(
                        vectors={"dense": SimpleNamespace(size=2)},
                    )
                )
            )

        def scroll(self, **kwargs: Any) -> tuple[list[object], None]:
            return (
                [
                    SimpleNamespace(
                        payload={
                            "_embedding_profile": {
                                "schema_version": 1,
                                "provider": "local",
                                "model": "local-model",
                                "dimensions": 2,
                            }
                        }
                    )
                ],
                None,
            )

        def create_payload_index(self, **kwargs: Any) -> None:
            seen.setdefault("payload_indexes", []).append(kwargs)

        def query_points(self, **kwargs: Any) -> object:
            seen["query_points"] = kwargs
            point = SimpleNamespace(
                score=0.91,
                payload={
                    "chunk_id": "c1",
                    "text": "Pin VF8 duoc bao hanh",
                    "metadata": {
                        "document_id": "doc-1",
                        "storage_chunk_id": "doc-1:0001",
                        "source": "warranty.pdf",
                    },
                },
            )
            return SimpleNamespace(points=[point])

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "local-model")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._configured_embedding", lambda: FakeEmbedding()
    )
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client", lambda config: FakeQdrantClient()
    )

    # Isolate from the question-index path (and any leaked env flag) so only the
    # main hybrid query_points call is captured.
    monkeypatch.setenv("RETRIEVAL_QUESTION_INDEX_ENABLED", "false")

    results = qdrant_hybrid_search(
        "pin vf8",
        document_ids=["doc-1"],
        top_k=3,
        exclude_dedup_layers=["exact_sha256", "simhash", "embedding"],
    )

    assert [index["field_name"] for index in seen["payload_indexes"]] == list(QDRANT_INDEX_FIELDS)
    query_filter = seen["query_points"]["prefetch"][0].filter
    assert query_filter.must[0].key == "document_id"
    assert query_filter.must[0].match.value == "doc-1"
    assert query_filter.must_not[0].key == "metadata.deduplication.primary_layer"
    assert query_filter.must_not[0].match.any == ["exact_sha256", "simhash", "embedding"]
    assert query_filter.must_not[1].key == "metadata.metadata_prefilter_exclude"
    assert query_filter.must_not[1].match.value is True
    assert results[0].chunk.chunk_id == "c1"


def test_qdrant_upsert_does_not_fallback_after_openai_runtime_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    class FailingOpenAIEmbedding:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("openai rate limited")

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "local-model")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._configured_embedding",
        lambda: FailingOpenAIEmbedding(),
    )
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client_from_env",
        lambda: (_ for _ in ()).throw(AssertionError("Qdrant must not be contacted")),
    )

    with pytest.raises(RuntimeError, match="openai rate limited"):
        upsert_dense_embeddings(
            [
                Chunk(
                    chunk_id="c1",
                    text="Pin VF8",
                    metadata={"document_id": "doc-1"},
                )
            ]
        )


def test_upsert_question_index_embeds_questions_into_side_collection(
    monkeypatch: MonkeyPatch,
) -> None:
    from agentic_rag.retrieval.search import upsert_question_index

    calls: dict[str, Any] = {}

    class FakeEmbedding:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            calls.setdefault("embedded", []).extend(texts)
            return [[0.1, 0.2] for _ in texts]

    class FakeQdrantClient:
        def collection_exists(self, collection_name: str) -> bool:
            return False

        def create_collection(self, **kwargs: Any) -> object:
            calls["create_collection"] = kwargs
            return object()

        def upsert(self, *, collection_name: str, points: list[Any]) -> object:
            calls["collection_name"] = collection_name
            calls.setdefault("points", []).extend(points)
            return object()

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "local-model")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._configured_embedding", lambda: FakeEmbedding()
    )
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client", lambda config: FakeQdrantClient()
    )

    chunks = [
        Chunk(
            chunk_id="c1",
            text="Pin VF8 duoc bao hanh 10 nam",
            metadata={"document_id": "doc-1", "questions": ["Pin bao lau?", "Bao hanh the nao?"]},
        ),
        Chunk(chunk_id="c2", text="No questions here", metadata={"document_id": "doc-1"}),
    ]

    result = upsert_question_index(chunks)

    assert result["questions_collection"] == "agentic_chunks_questions"
    assert result["indexed_questions"] == 2  # two questions on c1, none on c2
    assert calls["embedded"] == ["Pin bao lau?", "Bao hanh the nao?"]
    assert "dense" in calls["create_collection"]["vectors_config"]
    point = calls["points"][0]
    assert point.vector["dense"] == [0.1, 0.2]
    assert point.payload["chunk_id"] == "c1"
    assert point.payload["text"] == "Pin VF8 duoc bao hanh 10 nam"
    assert point.payload["question_text"] == "Pin bao lau?"
    assert str(UUID(str(point.id))) == str(point.id)  # deterministic uuid id


def test_qdrant_native_question_search_dedups_to_best_parent(monkeypatch: MonkeyPatch) -> None:
    from agentic_rag.retrieval import search

    class FakeEmbedding:
        def embed_query(self, text: str) -> list[float]:
            return [0.3, 0.4]

    class FakeQdrantClient:
        def collection_exists(self, collection_name: str) -> bool:
            return True

        def query_points(self, **kwargs: Any) -> object:
            def _hit(chunk_id: str, score: float, q: str) -> object:
                return SimpleNamespace(
                    score=score,
                    payload={
                        "chunk_id": chunk_id,
                        "text": f"text of {chunk_id}",
                        "metadata": {"document_id": "doc-1"},
                        "question_text": q,
                    },
                )

            return SimpleNamespace(
                points=[
                    _hit("c1", 0.92, "q-a"),
                    _hit("c1", 0.80, "q-b"),  # same parent, lower score -> dropped by dedup
                    _hit("c2", 0.71, "q-c"),
                    _hit("c3", 0.30, "q-d"),  # below min_score -> filtered out
                ]
            )

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setenv("QUESTION_MIN_SCORE", "0.5")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._configured_embedding", lambda: FakeEmbedding()
    )

    results = search._qdrant_native_question_search(FakeQdrantClient(), "pin vf8", top_k=5)

    assert results is not None
    ids = [r.chunk.chunk_id for r in results]
    assert ids == ["c1", "c2"]  # c1 deduped to best score, c3 below min_score dropped
    assert results[0].score == pytest.approx(0.92)
    assert all(r.retriever == "question" for r in results)


def test_qdrant_native_question_search_returns_none_when_collection_absent(
    monkeypatch: MonkeyPatch,
) -> None:
    from agentic_rag.retrieval import search

    class FakeQdrantClient:
        def collection_exists(self, collection_name: str) -> bool:
            return False

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")

    # None signals "no side collection" so the caller falls back to the in-memory index.
    assert search._qdrant_native_question_search(FakeQdrantClient(), "q", top_k=5) is None


def test_delete_qdrant_document_questions_filters_by_metadata_document_id(
    monkeypatch: MonkeyPatch,
) -> None:
    from agentic_rag.retrieval import search

    seen: dict[str, Any] = {}

    class FakeQdrantClient:
        __module__ = "qdrant_client.fake"

        def collection_exists(self, collection_name: str) -> bool:
            return True

        def delete(self, *, collection_name: str, points_selector: Any, wait: bool) -> object:
            seen["collection_name"] = collection_name
            seen["selector"] = points_selector
            return object()

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client", lambda config: FakeQdrantClient()
    )

    result = search.delete_qdrant_document_questions("doc-1")

    assert result["deleted"] is True
    assert seen["collection_name"] == "agentic_chunks_questions"
    condition = seen["selector"].filter.must[0]
    assert condition.key == "metadata.document_id"
    assert condition.match.value == "doc-1"


def test_delete_qdrant_document_questions_skips_when_collection_absent(
    monkeypatch: MonkeyPatch,
) -> None:
    from agentic_rag.retrieval import search

    class FakeQdrantClient:
        def collection_exists(self, collection_name: str) -> bool:
            return False

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client", lambda config: FakeQdrantClient()
    )

    result = search.delete_qdrant_document_questions("doc-1")
    assert result["skipped"] == "absent"


def test_qdrant_question_store_scrolls_all_points_and_caches() -> None:
    # The question-index retriever on the Qdrant path builds an in-memory Store by
    # scrolling the whole collection once, preserving each chunk's questions, and
    # caches it per collection so later queries reuse it.
    from agentic_rag.retrieval import search

    search._QDRANT_QUESTION_STORE.clear()
    scroll_calls = {"n": 0}

    class FakeClient:
        def scroll(self, **kwargs: Any) -> tuple[list[object], Any]:
            scroll_calls["n"] += 1
            if kwargs.get("offset") is None:
                return (
                    [
                        SimpleNamespace(
                            payload={
                                "chunk_id": "c1",
                                "text": "Pin VF8 bao hanh",
                                "metadata": {"questions": ["Pin bao lau?"]},
                            }
                        )
                    ],
                    "page2",
                )
            return (
                [SimpleNamespace(payload={"chunk_id": "c2", "text": "t2", "metadata": {}})],
                None,
            )

    client = FakeClient()
    try:
        store = search._qdrant_question_store(client, "col")
        assert len(store._chunks) == 2  # both pages scrolled
        assert store._chunks[0].metadata["questions"] == ["Pin bao lau?"]
        assert scroll_calls["n"] == 2  # paginated until offset is None

        cached = search._qdrant_question_store(client, "col")
        assert cached is store  # cached: no re-scroll
        assert scroll_calls["n"] == 2
    finally:
        search._QDRANT_QUESTION_STORE.clear()


def test_qdrant_upsert_accepts_matching_populated_embedding_profile(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeEmbedding:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

    class FakeQdrantClient:
        def get_collection(self, collection_name: str) -> object:
            return SimpleNamespace(
                config=SimpleNamespace(
                    params=SimpleNamespace(
                        vectors={"dense": SimpleNamespace(size=2)},
                    )
                )
            )

        def scroll(self, **kwargs: Any) -> tuple[list[object], None]:
            return (
                [
                    SimpleNamespace(
                        payload={
                            "_embedding_profile": {
                                "schema_version": 1,
                                "provider": "local",
                                "model": "local-model",
                                "dimensions": 2,
                            }
                        }
                    )
                ],
                None,
            )

        def upsert(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "local-model")
    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._configured_embedding",
        lambda: FakeEmbedding(),
    )
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client",
        lambda config: FakeQdrantClient(),
    )

    upsert_dense_embeddings(
        [
            Chunk(
                chunk_id="c1",
                text="Pin VF8",
                metadata={"document_id": "doc-1"},
            )
        ]
    )

    assert seen["collection_name"] == "agentic_chunks"


def test_qdrant_upsert_does_not_create_collection_after_non_404_error(
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeEmbedding:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

    class UnauthorizedError(Exception):
        status_code = 401

    class FakeQdrantClient:
        def get_collection(self, collection_name: str) -> object:
            raise UnauthorizedError(collection_name)

        def create_collection(self, **kwargs: Any) -> None:
            raise AssertionError("non-404 errors must not recreate the collection")

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "local-model")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._configured_embedding",
        lambda: FakeEmbedding(),
    )
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client_from_env",
        lambda: FakeQdrantClient(),
    )

    with pytest.raises(UnauthorizedError):
        upsert_dense_embeddings(
            [
                Chunk(
                    chunk_id="c1",
                    text="Pin VF8",
                    metadata={"document_id": "doc-1"},
                )
            ]
        )


def test_qdrant_upsert_rejects_existing_dimension_mismatch(
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeEmbedding:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

    class FakeQdrantClient:
        def get_collection(self, collection_name: str) -> object:
            return SimpleNamespace(
                config=SimpleNamespace(
                    params=SimpleNamespace(
                        vectors={"dense": SimpleNamespace(size=3)},
                    )
                )
            )

        def upsert(self, **kwargs: Any) -> None:
            raise AssertionError("mismatched collection must not be written")

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "local-model")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._configured_embedding",
        lambda: FakeEmbedding(),
    )
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client_from_env",
        lambda: FakeQdrantClient(),
    )

    with pytest.raises(ValueError, match=r"dimension.*3.*2.*reindex"):
        upsert_dense_embeddings(
            [
                Chunk(
                    chunk_id="c1",
                    text="Pin VF8",
                    metadata={"document_id": "doc-1"},
                )
            ]
        )


@pytest.mark.parametrize(
    "stored_profile",
    [
        {
            "schema_version": 1,
            "provider": "openai",
            "model": "text-embedding-3-small",
            "dimensions": 2,
        },
        {
            "schema_version": 1,
            "provider": "local",
            "model": "different-model",
            "dimensions": 2,
        },
        None,
    ],
)
def test_qdrant_upsert_rejects_incompatible_or_legacy_profile(
    monkeypatch: MonkeyPatch,
    stored_profile: dict[str, object] | None,
) -> None:
    class FakeEmbedding:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

    class FakeQdrantClient:
        def get_collection(self, collection_name: str) -> object:
            return SimpleNamespace(
                config=SimpleNamespace(
                    params=SimpleNamespace(
                        vectors={"dense": SimpleNamespace(size=2)},
                    )
                )
            )

        def scroll(self, **kwargs: Any) -> tuple[list[object], None]:
            payload = {} if stored_profile is None else {"_embedding_profile": stored_profile}
            return ([SimpleNamespace(payload=payload)], None)

        def upsert(self, **kwargs: Any) -> None:
            raise AssertionError("incompatible collection must not be written")

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "local-model")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._configured_embedding",
        lambda: FakeEmbedding(),
    )
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client_from_env",
        lambda: FakeQdrantClient(),
    )

    with pytest.raises(ValueError, match=r"embedding profile.*reindex"):
        upsert_dense_embeddings(
            [
                Chunk(
                    chunk_id="c1",
                    text="Pin VF8",
                    metadata={"document_id": "doc-1"},
                )
            ]
        )


def test_qdrant_query_rejects_incompatible_profile_before_search(
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeEmbedding:
        def embed_query(self, text: str) -> list[float]:
            return [0.1, 0.2]

    class FakeQdrantClient:
        def get_collection(self, collection_name: str) -> object:
            return SimpleNamespace(
                config=SimpleNamespace(
                    params=SimpleNamespace(
                        vectors={"dense": SimpleNamespace(size=2)},
                    )
                )
            )

        def scroll(self, **kwargs: Any) -> tuple[list[object], None]:
            return (
                [
                    SimpleNamespace(
                        payload={
                            "_embedding_profile": {
                                "schema_version": 1,
                                "provider": "openai",
                                "model": "text-embedding-3-small",
                                "dimensions": 2,
                            }
                        }
                    )
                ],
                None,
            )

        def query_points(self, **kwargs: Any) -> object:
            raise AssertionError("incompatible collection must not be queried")

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "local-model")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._configured_embedding",
        lambda: FakeEmbedding(),
    )
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client",
        lambda config: FakeQdrantClient(),
    )

    with pytest.raises(ValueError, match=r"embedding profile.*reindex"):
        qdrant_hybrid_search("pin vf8")


def test_delete_qdrant_document_points_filters_by_document_id(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeQdrantClient:
        def delete(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client", lambda config: FakeQdrantClient()
    )

    trace = delete_qdrant_document_points("doc-1")

    assert trace["enabled"] is True
    assert trace["deleted"] is True
    assert seen["collection_name"] == "agentic_chunks"
    assert seen["document_ids"] == ["doc-1"]
    assert seen["wait"] is True


def test_delete_all_qdrant_points_preserves_collection(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeQdrantClient:
        def delete(self, **kwargs: Any) -> None:
            seen.update(kwargs)

        def delete_collection(self, **kwargs: Any) -> None:
            raise AssertionError("clearing points must preserve the collection")

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client", lambda config: FakeQdrantClient()
    )

    trace = delete_all_qdrant_points()

    assert trace["enabled"] is True
    assert trace["deleted"] is True
    assert seen["collection_name"] == "agentic_chunks"
    assert seen["document_ids"] is None
    assert seen["wait"] is True


def test_delete_all_qdrant_points_keeps_real_in_memory_collection(
    monkeypatch: MonkeyPatch,
) -> None:
    from qdrant_client import QdrantClient, models

    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="agentic_chunks",
        vectors_config={"dense": models.VectorParams(size=2, distance=models.Distance.COSINE)},
        sparse_vectors_config={"sparse": models.SparseVectorParams()},
    )
    client.upsert(
        collection_name="agentic_chunks",
        points=[
            models.PointStruct(
                id=1,
                vector={
                    "dense": [0.1, 0.2],
                    "sparse": models.SparseVector(indices=[1], values=[1.0]),
                },
                payload={"document_id": "doc-1"},
            )
        ],
    )
    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setattr("agentic_rag.retrieval.search._qdrant_client", lambda config: client)

    delete_all_qdrant_points()

    collection = client.get_collection("agentic_chunks")
    points, _ = client.scroll(collection_name="agentic_chunks", limit=10)
    assert collection.points_count == 0
    assert points == []


def test_delete_qdrant_document_points_treats_missing_collection_as_deleted(
    monkeypatch: MonkeyPatch,
) -> None:
    class MissingCollectionError(Exception):
        status_code = 404

    class FakeQdrantClient:
        def delete(self, **kwargs: Any) -> None:
            raise MissingCollectionError("collection does not exist")

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client", lambda config: FakeQdrantClient()
    )

    trace = delete_qdrant_document_points("doc-1")

    assert trace["deleted"] is True


def test_delete_all_qdrant_points_propagates_non_not_found_error(
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeQdrantClient:
        def delete(self, **kwargs: Any) -> None:
            raise ConnectionError("qdrant unavailable")

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client", lambda config: FakeQdrantClient()
    )

    with pytest.raises(ConnectionError, match="qdrant unavailable"):
        delete_all_qdrant_points()


def test_delete_all_qdrant_points_resolves_disabled_store_once(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("DENSE_VECTOR_STORE", "turbovec")

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        trace = delete_all_qdrant_points()

    assert trace == {"enabled": False, "vector_store": "turbovec"}
    legacy_warnings = [
        warning
        for warning in caught_warnings
        if "DENSE_VECTOR_STORE is deprecated" in str(warning.message)
    ]
    assert len(legacy_warnings) == 1
