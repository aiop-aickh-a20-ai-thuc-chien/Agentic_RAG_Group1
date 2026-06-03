import json
from types import SimpleNamespace

from pytest import MonkeyPatch

from agentic_rag.core.contracts import Chunk
from agentic_rag.retrieval.search import Store


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
