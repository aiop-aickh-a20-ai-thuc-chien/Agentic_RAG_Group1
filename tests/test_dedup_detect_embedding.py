from agentic_rag.core.contracts import EmbeddingInput, EmbeddingOutput
from agentic_rag.ingestion.dedup_detect.embedding import embedding_vectors_from_client
from agentic_rag.ingestion.dedup_detect.models import DedupDocument


def test_embedding_vectors_from_client_batches_and_preserves_order() -> None:
    class FakeEmbeddingClient:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def embed(self, request: EmbeddingInput) -> EmbeddingOutput:
            self.calls.append(list(request.texts))
            return EmbeddingOutput(
                vectors=[[_text_index(text)] for text in request.texts],
                provider="fake",
                model="fake-embedding",
                dimensions=1,
            )

    client = FakeEmbeddingClient()
    documents = [
        DedupDocument(document_id=f"doc-{index}", text=f"text-{index}") for index in range(5)
    ]

    vectors = embedding_vectors_from_client(documents, client, batch_size=2)

    assert client.calls == [
        ["text-0", "text-1"],
        ["text-2", "text-3"],
        ["text-4"],
    ]
    assert vectors == {
        "doc-0": [0.0],
        "doc-1": [1.0],
        "doc-2": [2.0],
        "doc-3": [3.0],
        "doc-4": [4.0],
    }


def _text_index(text: str) -> float:
    return float(text.rsplit("-", maxsplit=1)[-1])
