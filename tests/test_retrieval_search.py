from agentic_rag.core.contracts import Chunk
from agentic_rag.retrieval.search import Store


def test_preprocess_query_normalizes_vietnamese_text() -> None:
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
