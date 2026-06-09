import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from pytest import MonkeyPatch

from agentic_rag.core.contracts import Chunk
from agentic_rag.retrieval.search import (
    Store,
    delete_all_qdrant_points,
    delete_qdrant_document_points,
    qdrant_hybrid_search,
    upsert_dense_embeddings,
)


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

    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "local-model")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._configured_embedding", lambda: FakeEmbedding()
    )
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client_from_env", lambda: FakeQdrantClient()
    )

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

        def upsert(self, **kwargs: Any) -> None:
            seen["upsert"] = kwargs

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
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
    assert seen["upsert"]["collection_name"] == "agentic_chunks"


def test_qdrant_upsert_does_not_fallback_after_openai_runtime_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    class FailingOpenAIEmbedding:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("openai rate limited")

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
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

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
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
        qdrant_hybrid_search("pin vf8")


def test_delete_qdrant_document_points_filters_by_document_id(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeQdrantClient:
        def delete(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client_from_env", lambda: FakeQdrantClient()
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
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client_from_env", lambda: FakeQdrantClient()
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
    monkeypatch.setenv("QDRANT_COLLECTION", "agentic_chunks")
    monkeypatch.setattr("agentic_rag.retrieval.search._qdrant_client_from_env", lambda: client)

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
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client_from_env", lambda: FakeQdrantClient()
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
    monkeypatch.setattr(
        "agentic_rag.retrieval.search._qdrant_client_from_env", lambda: FakeQdrantClient()
    )

    with pytest.raises(ConnectionError, match="qdrant unavailable"):
        delete_all_qdrant_points()
