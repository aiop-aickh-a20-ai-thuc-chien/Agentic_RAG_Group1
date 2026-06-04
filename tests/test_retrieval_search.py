import json
from types import SimpleNamespace
from typing import Any

from pytest import MonkeyPatch

from agentic_rag.core.contracts import Chunk
from agentic_rag.retrieval.search import Store, upsert_dense_embeddings


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
    assert results[0].chunk.metadata["document_id"] == "doc-1"
