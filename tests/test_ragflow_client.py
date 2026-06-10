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
        if path.startswith("/v1/document/upload_info"):
            return {"code": 0, "data": {"id": "attachment-1", "name": "page.md"}}
        return {"code": 0, "data": {"chunks": []}}

    def _request_bytes(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, object] | None = None,
    ) -> bytes:
        query_suffix = ""
        if query:
            query_suffix = "?" + "&".join(f"{key}={value}" for key, value in query.items())
        self.calls.append((method, f"{path}{query_suffix}", None))
        return b"# Parsed by RAGFlow\n\nNoi dung URL"


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


def test_upload_runtime_url_uses_ragflow_url_attachment_endpoint() -> None:
    client = RecordingRAGFlowClient()

    attachment = client.upload_runtime_url(url="https://example.com/docs/page")

    assert attachment["id"] == "attachment-1"
    assert client.calls[0][0] == "POST"
    assert client.calls[0][1] == (
        "/v1/document/upload_info?url=https%3A%2F%2Fexample.com%2Fdocs%2Fpage"
    )


def test_download_runtime_attachment_returns_parsed_bytes() -> None:
    client = RecordingRAGFlowClient()

    content = client.download_runtime_attachment(attachment_id="attachment-1")

    assert content.startswith(b"# Parsed by RAGFlow")
    assert client.calls[0] == (
        "GET",
        "/v1/document/download/attachment-1?ext=markdown",
        None,
    )
