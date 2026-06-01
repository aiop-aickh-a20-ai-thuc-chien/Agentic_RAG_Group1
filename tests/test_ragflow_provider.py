from agentic_rag.core.contracts import Chunk, SearchResult
from agentic_rag.integrations.ragflow.client import RAGFlowClient
from agentic_rag.integrations.ragflow.config import RAGFlowConfig
from agentic_rag.integrations.ragflow.providers import RAGFlowEvidenceProvider


class FakeRAGFlowClient(RAGFlowClient):
    def __init__(self) -> None:
        super().__init__(
            RAGFlowConfig(
                base_url="http://ragflow.local",
                api_key="test-key",
                dataset_id="dataset-1",
            )
        )
        self.parsed_document_ids: list[str] = []
        self.uploaded_documents: list[tuple[str, bytes, str | None]] = []
        self.uploaded_runtime_urls: list[str] = []

    def upload_document(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        dataset_id: str | None = None,
    ) -> dict[str, object]:
        self.uploaded_documents.append((filename, content, content_type))
        return {"id": "doc-1", "name": filename, "dataset_id": dataset_id}

    def upload_runtime_url(self, *, url: str) -> dict[str, object]:
        self.uploaded_runtime_urls.append(url)
        return {"id": "runtime-1", "name": "example-page.html"}

    def download_runtime_attachment(
        self,
        *,
        attachment_id: str,
        ext: str = "markdown",
    ) -> bytes:
        assert attachment_id == "runtime-1"
        assert ext == "markdown"
        return b"# Parsed URL\n\nNoi dung do RAGFlow parse."

    def parse_documents(
        self,
        *,
        document_ids: list[str],
        dataset_id: str | None = None,
    ) -> dict[str, object]:
        self.parsed_document_ids = document_ids
        return {"code": 0}

    def list_chunks(
        self,
        *,
        document_id: str,
        dataset_id: str | None = None,
        keywords: str | None = None,
        page: int = 1,
        page_size: int | None = None,
        chunk_id: str | None = None,
    ) -> dict[str, object]:
        return {
            "data": {
                "doc": {
                    "id": document_id,
                    "name": "warranty.pdf",
                    "dataset_id": dataset_id,
                    "chunk_count": 14,
                },
                "chunks": [
                    {
                        "id": "chunk-1",
                        "content": "Pin cao ap duoc bao hanh 8 nam.",
                        "positions": [[12, 1, 2]],
                    }
                ],
            }
        }

    def retrieve(
        self,
        *,
        question: str,
        dataset_ids: list[str] | None = None,
        document_ids: list[str] | None = None,
        page: int = 1,
        page_size: int | None = None,
    ) -> dict[str, object]:
        return {
            "data": {
                "doc_aggs": [{"doc_id": "doc-1", "doc_name": "warranty.pdf"}],
                "chunks": [
                    {
                        "id": "chunk-1",
                        "document_id": "doc-1",
                        "content": "Pin cao ap duoc bao hanh 8 nam.",
                        "similarity": 0.91,
                        "positions": [[12, 1, 2]],
                    }
                ],
            }
        }


def test_provider_uploads_document_and_starts_parse() -> None:
    client = FakeRAGFlowClient()
    provider = RAGFlowEvidenceProvider(client, dataset_id="dataset-1")

    uploaded = provider.upload_document(
        filename="warranty.pdf",
        content=b"%PDF",
        content_type="application/pdf",
    )

    assert uploaded.document_id == "doc-1"
    assert uploaded.parse_started is True
    assert client.parsed_document_ids == ["doc-1"]


def test_provider_imports_url_with_ragflow_parser_then_indexes_markdown() -> None:
    client = FakeRAGFlowClient()
    provider = RAGFlowEvidenceProvider(client, dataset_id="dataset-1")

    uploaded = provider.import_url_document(url="https://example.com/docs/page")

    assert uploaded.document_id == "doc-1"
    assert uploaded.parse_started is True
    assert client.uploaded_runtime_urls == ["https://example.com/docs/page"]
    assert client.parsed_document_ids == ["doc-1"]
    expected_content = (
        b"Source URL: https://example.com/docs/page\n\n# Parsed URL\n\nNoi dung do RAGFlow parse."
    )
    assert client.uploaded_documents == [
        (
            "example-page.md",
            expected_content,
            "text/markdown; charset=utf-8",
        )
    ]


def test_provider_lists_chunks_as_shared_chunks() -> None:
    provider = RAGFlowEvidenceProvider(FakeRAGFlowClient(), dataset_id="dataset-1")

    chunks = provider.list_document_chunks(document_id="doc-1")

    assert chunks == [
        Chunk(
            chunk_id="chunk-1",
            text="Pin cao ap duoc bao hanh 8 nam.",
            metadata={
                "document_id": "doc-1",
                "dataset_id": "dataset-1",
                "source": "warranty.pdf",
                "document_name": "warranty.pdf",
                "file_name": "warranty.pdf",
                "source_type": "ragflow",
                "id": "chunk-1",
                "content": "Pin cao ap duoc bao hanh 8 nam.",
                "positions": [[12, 1, 2]],
                "url": None,
                "page": 12,
                "section": None,
                "similarity": None,
                "vector_similarity": None,
                "term_similarity": None,
            },
        )
    ]


def test_provider_returns_full_document_chunk_count() -> None:
    provider = RAGFlowEvidenceProvider(FakeRAGFlowClient(), dataset_id="dataset-1")

    document_chunks = provider.document_chunks(document_id="doc-1", page_size=5)

    assert document_chunks.total_chunks == 14
    assert len(document_chunks.chunks) == 1


def test_provider_retrieves_search_results_without_generating_answer() -> None:
    provider = RAGFlowEvidenceProvider(FakeRAGFlowClient(), dataset_id="dataset-1")

    results = provider.retrieve(question="Pin bao hanh bao lau?", document_ids=["doc-1"])

    assert results == [
        SearchResult(
            chunk=Chunk(
                chunk_id="chunk-1",
                text="Pin cao ap duoc bao hanh 8 nam.",
                metadata={
                    "source": "warranty.pdf",
                    "document_name": "warranty.pdf",
                    "dataset_id": "dataset-1",
                    "id": "chunk-1",
                    "document_id": "doc-1",
                    "content": "Pin cao ap duoc bao hanh 8 nam.",
                    "similarity": 0.91,
                    "positions": [[12, 1, 2]],
                    "source_type": "ragflow",
                    "file_name": None,
                    "url": None,
                    "page": 12,
                    "section": None,
                    "vector_similarity": None,
                    "term_similarity": None,
                },
            ),
            score=0.91,
            rank=1,
            retriever="ragflow",
        )
    ]
