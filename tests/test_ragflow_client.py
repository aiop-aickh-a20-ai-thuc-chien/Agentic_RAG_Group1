from collections.abc import Mapping

from agentic_rag.integrations.ragflow.client import RAGFlowClient
from agentic_rag.integrations.ragflow.config import RAGFlowConfig


class RecordingRAGFlowClient(RAGFlowClient):
    def __init__(self) -> None:
        super().__init__(
            RAGFlowConfig(
                base_url="http://ragflow.local",
                api_key="test-key",
                dataset_id="dataset-1",
            )
        )
        self.calls: list[tuple[str, str, bytes | None]] = []

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        self.calls.append((method, path, body))
        if path.endswith("/documents"):
            return {"code": 0, "data": [{"id": "doc-1", "name": "warranty.pdf"}]}
        return {"code": 0, "data": {"chunks": []}}


def test_upload_document_targets_dataset_documents_endpoint() -> None:
    client = RecordingRAGFlowClient()

    document = client.upload_document(
        filename="warranty.pdf",
        content=b"%PDF",
        content_type="application/pdf",
    )

    assert document["id"] == "doc-1"
    assert client.calls[0][0] == "POST"
    assert client.calls[0][1] == "/api/v1/datasets/dataset-1/documents"
    assert b'name="file"; filename="warranty.pdf"' in (client.calls[0][2] or b"")


def test_retrieve_targets_retrieval_endpoint_with_dataset_id() -> None:
    client = RecordingRAGFlowClient()

    client.retrieve(question="Pin bao hanh bao lau?", document_ids=["doc-1"])

    method, path, body = client.calls[0]
    assert method == "POST"
    assert path == "/api/v1/retrieval"
    assert body is not None
    assert b'"dataset_ids": ["dataset-1"]' in body
    assert b'"document_ids": ["doc-1"]' in body


def test_list_chunks_targets_document_chunks_endpoint() -> None:
    client = RecordingRAGFlowClient()

    client.list_chunks(document_id="doc-1", page_size=20)

    assert client.calls[0][0] == "GET"
    assert client.calls[0][1] == (
        "/api/v1/datasets/dataset-1/documents/doc-1/chunks?page=1&page_size=20"
    )
