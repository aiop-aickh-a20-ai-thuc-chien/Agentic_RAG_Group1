import json
import os
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import BaseModel, ValidationError
from pytest import MonkeyPatch

from agentic_rag.core.contracts import Chunk, RetrievalInput, SearchResult
from agentic_rag.ingestion.pdf import LoadedPdfDocument
from agentic_rag.ingestion.pdf.config import PdfIngestionConfig
from agentic_rag.ingestion.url import LoadedUrlDocument
from agentic_rag.integrations.local_pdf import providers as providers_module
from agentic_rag.integrations.local_pdf.providers import (
    LocalPdfDocumentChunks,
    LocalPdfEvidenceProvider,
    LocalPdfUploadedDocument,
)
from agentic_rag.integrations.local_pdf.storage import (
    S3LocalSourceStore,
    StoredRawSource,
    StoredSourceDocument,
)
from agentic_rag.retrieval.config import VectorStoreConfig
from agentic_rag.retrieval.search import Store


@pytest.fixture(autouse=True)
def _stub_provider_qdrant_delete(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.delete_qdrant_document_points",
        lambda document_id: {
            "enabled": True,
            "vector_store": "qdrant",
            "document_id": document_id,
            "deleted": True,
        },
    )


def _mock_openai_client(monkeypatch: MonkeyPatch) -> None:
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
                        "transformed_queries": ["pin bao hanh bao lau"],
                    }
                )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)


def test_local_pdf_provider_models_are_pydantic_contracts() -> None:
    uploaded = LocalPdfUploadedDocument(
        document_id="doc-1",
        name="warranty.pdf",
        dataset_id="local_pdf",
        parse_started=True,
        trace={"parser": "docling"},
    )
    page = LocalPdfDocumentChunks(chunks=[], total_chunks=0)

    assert isinstance(uploaded, BaseModel)
    assert isinstance(page, BaseModel)

    with pytest.raises(ValidationError):
        LocalPdfUploadedDocument.model_validate(
            {
                "document_id": "doc-1",
                "name": "warranty.pdf",
                "dataset_id": "local_pdf",
                "parse_started": True,
                "trace": {},
                "unexpected": True,
            }
        )

    field_name = "name"

    with pytest.raises(ValidationError):
        setattr(uploaded, field_name, "changed.pdf")


def test_local_pdf_provider_uploads_chunks_and_lists_them(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    seen_kwargs: dict[str, str] = {}

    def fake_load_pdf_with_markdown(path: str, **kwargs: str) -> LoadedPdfDocument:
        seen_kwargs.update(kwargs)
        return LoadedPdfDocument(
            markdown="# Bao hanh\nPin VF8 duoc bao hanh 8 nam.",
            chunks=[
                Chunk(
                    chunk_id="pdf_doc_c0001",
                    text="Pin VF8 duoc bao hanh 8 nam.",
                    metadata={"chunk_index": 1, "section": "Bao hanh"},
                ),
                Chunk(
                    chunk_id="pdf_doc_c0002",
                    text="Dieu kien bao hanh can co hoa don.",
                    metadata={"chunk_index": 2, "section": "Dieu kien"},
                ),
            ],
            parser=kwargs["strategy_name"],
            pipeline=kwargs["pipeline_name"],
            strategy=kwargs["strategy_name"],
            chunker=kwargs["chunker_name"],
        )

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_pdf_with_markdown",
        fake_load_pdf_with_markdown,
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    uploaded = provider.upload_document(
        filename="warranty.pdf",
        content=b"%PDF-1.4",
        content_type="application/pdf",
    )
    document_chunks = provider.document_chunks(document_id=uploaded.document_id)

    assert uploaded.dataset_id == "local_pdf"
    assert uploaded.name == "warranty.pdf"
    assert uploaded.parse_started is True
    trace = cast(dict[str, dict[str, Any]], uploaded.trace)
    assert trace["source_upload"]["filename"] == "warranty.pdf"
    assert trace["parse"]["parser"] == "docling"
    assert trace["parse"]["markdown_chars"] == 39
    assert trace["parse"]["markdown_preview"] == "# Bao hanh\nPin VF8 duoc bao hanh 8 nam."
    assert "markdown" not in trace["parse"]
    assert seen_kwargs == {
        "pipeline_name": "ocr",
        "strategy_name": "docling",
        "chunker_name": "deterministic",
    }
    assert trace["chunking"]["chunk_count"] == 2
    assert trace["parse"]["pipeline"] == "ocr"
    assert trace["parse"]["strategy"] == "docling"
    assert trace["chunking"]["chunker"] == "deterministic"
    assert trace["index_write"]["type"] == "jsonl"
    assert document_chunks.total_chunks == 2
    assert [chunk.chunk_id for chunk in document_chunks.chunks] == [
        "pdf_doc_c0001",
        "pdf_doc_c0002",
    ]
    assert document_chunks.chunks[0].metadata["document_id"] == uploaded.document_id
    assert document_chunks.chunks[0].metadata["source"] == "warranty.pdf"
    assert (tmp_path / "chunks" / f"{uploaded.document_id}.jsonl").exists()
    markdown_path = tmp_path / "parsed" / f"{uploaded.document_id}.md"
    assert trace["parse"]["markdown_path"] == str(markdown_path)
    assert markdown_path.read_text(encoding="utf-8") == ("# Bao hanh\nPin VF8 duoc bao hanh 8 nam.")
    debug = provider.document_debug(document_id=uploaded.document_id)
    assert debug.markdown == "# Bao hanh\nPin VF8 duoc bao hanh 8 nam."
    assert debug.chunk_input == "# Bao hanh\nPin VF8 duoc bao hanh 8 nam."
    assert debug.chunk_input_type == "markdown"
    assert debug.name == "warranty.pdf"
    assert debug.source_type == "pdf"


def test_local_pdf_provider_can_include_full_markdown_in_trace(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_TRACE_FULL_CONTENT", "true")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_pdf_with_markdown",
        lambda path, **kwargs: LoadedPdfDocument(
            markdown="# Full\nMarkdown noi dung.",
            chunks=[],
        ),
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    uploaded = provider.upload_document(
        filename="notes.pdf",
        content=b"%PDF-1.4",
        content_type="application/pdf",
    )

    trace = cast(dict[str, dict[str, Any]], uploaded.trace)
    assert trace["parse"]["markdown"] == "# Full\nMarkdown noi dung."


def test_local_pdf_provider_passes_configured_parser_and_chunker(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    seen_kwargs: dict[str, str] = {}

    def fake_load_pdf_with_markdown(path: str, **kwargs: str) -> LoadedPdfDocument:
        seen_kwargs.update(kwargs)
        return LoadedPdfDocument(
            markdown="# Configured\nNoi dung.",
            chunks=[],
            parser=kwargs["strategy_name"],
            pipeline=kwargs["pipeline_name"],
            strategy=kwargs["strategy_name"],
            chunker=kwargs["chunker_name"],
        )

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_pdf_with_markdown",
        fake_load_pdf_with_markdown,
    )
    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        pdf_config=PdfIngestionConfig(
            pipeline_name="vlm",
            strategy_name="mineru",
            chunker_name="deterministic",
        ),
    )

    uploaded = provider.upload_document(
        filename="configured.pdf",
        content=b"%PDF-1.4",
        content_type="application/pdf",
    )

    trace = cast(dict[str, dict[str, Any]], uploaded.trace)
    assert seen_kwargs == {
        "pipeline_name": "vlm",
        "strategy_name": "mineru",
        "chunker_name": "deterministic",
    }
    assert trace["parse"]["parser"] == "mineru"
    assert trace["parse"]["pipeline"] == "vlm"
    assert trace["parse"]["strategy"] == "mineru"
    assert trace["chunking"]["chunker"] == "deterministic"


def test_local_pdf_provider_uploads_url_chunks(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_url_with_artifacts",
        lambda url, **kwargs: LoadedUrlDocument(
            markdown="# Trang chinh sach\n\n## Chinh sach\n\nNoi dung URL ve chinh sach mua nha.",
            chunks=[
                Chunk(
                    chunk_id="url_doc_c0001",
                    text="Noi dung URL ve chinh sach mua nha.",
                    metadata={
                        "source": url,
                        "source_type": "url",
                        "url": url,
                        "title": "Trang chinh sach",
                        "section": "Chinh sach",
                        "chunking_method": "deterministic-character-overlap",
                        "chunking_provider": None,
                        "chunking_model": None,
                    },
                )
            ],
            artifacts=None,
        ),
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    uploaded = provider.upload_url(url="https://example.com/chinh-sach")
    document_chunks = provider.document_chunks(document_id=uploaded.document_id)

    assert uploaded.dataset_id == "local_pdf"
    assert uploaded.name == "example.com-chinh-sach.txt"
    assert uploaded.parse_started is True
    trace = cast(dict[str, dict[str, Any]], uploaded.trace)
    assert trace["source_upload"]["source_type"] == "url"
    assert trace["source_upload"]["requested_url"] == "https://example.com/chinh-sach"
    assert trace["source_upload"]["final_url"] == "https://example.com/chinh-sach"
    assert trace["parse"]["parser"] == "url.load_url_with_artifacts"
    assert trace["parse"]["title"] == "Trang chinh sach"
    assert trace["parse"]["section_count"] == 1
    assert trace["parse"]["sections"] == ["Chinh sach"]
    markdown_path = tmp_path / "parsed" / f"{uploaded.document_id}.md"
    assert trace["parse"]["markdown_path"] == str(markdown_path)
    assert trace["parse"]["markdown_chars"] == 70
    assert trace["parse"]["markdown_preview"].startswith("# Trang chinh sach")
    assert trace["chunking"]["chunk_count"] == 1
    assert trace["chunking"]["chunking_methods"] == ["deterministic-character-overlap"]
    assert document_chunks.total_chunks == 1
    chunk = document_chunks.chunks[0]
    assert chunk.metadata["document_id"] == uploaded.document_id
    assert chunk.metadata["source_type"] == "url"
    assert chunk.metadata["source"] == "https://example.com/chinh-sach"
    assert chunk.metadata["url"] == "https://example.com/chinh-sach"
    debug = provider.document_debug(document_id=uploaded.document_id)
    assert debug.markdown.startswith("# Trang chinh sach")
    assert debug.chunk_input == "Noi dung URL ve chinh sach mua nha."
    assert debug.chunk_input_type == "parsed_sections"
    assert debug.source_type == "url"
    assert debug.source == "https://example.com/chinh-sach"


def test_local_pdf_provider_uploads_text_chunks(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    uploaded = provider.upload_text(title="Ghi chu", text="Noi dung tu nguoi dung")
    document_chunks = provider.document_chunks(document_id=uploaded.document_id)

    assert uploaded.name == "Ghi-chu.txt"
    assert document_chunks.total_chunks == 1
    chunk = document_chunks.chunks[0]
    assert chunk.metadata["document_id"] == uploaded.document_id
    assert chunk.metadata["source_type"] == "text"
    assert chunk.text == "Noi dung tu nguoi dung"


def test_local_pdf_provider_can_persist_chunks_with_source_store(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeSourceStore:
        def __init__(self) -> None:
            self.documents: dict[str, list[Chunk]] = {}
            self.seen_metadata: dict[str, object] | None = None

        def write_document(
            self,
            *,
            document_id: str,
            dataset_id: str,
            name: str,
            source_type: str,
            source: str,
            raw_path: Path | None,
            markdown_path: Path | None,
            metadata: dict[str, object],
            chunks: list[Chunk],
        ) -> None:
            self.seen_metadata = metadata
            self.documents[document_id] = chunks

        def read_chunks(self, document_id: str) -> list[Chunk]:
            return self.documents.get(document_id, [])

        def read_all_chunks(self) -> list[Chunk]:
            return [chunk for chunks in self.documents.values() for chunk in chunks]

        def list_documents(self) -> list[StoredSourceDocument]:
            return [
                StoredSourceDocument(
                    document_id=document_id,
                    dataset_id="local_pdf",
                    name="Ghi-chu.txt",
                    source_type="text",
                    source="Ghi-chu.txt",
                    total_chunks=len(chunks),
                    metadata={"title": "Ghi chu"},
                )
                for document_id, chunks in self.documents.items()
            ]

        def delete_document(self, document_id: str) -> None:
            if document_id not in self.documents:
                raise ValueError(f"Document {document_id!r} not found.")
            del self.documents[document_id]

        def delete_all_documents(self) -> int:
            count = len(self.documents)
            self.documents.clear()
            return count

        def read_chunks_for_documents(self, document_ids: list[str]) -> list[Chunk]:
            result = []
            for doc_id in document_ids:
                result.extend(self.documents.get(doc_id, []))
            return result

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        lambda chunks, **kwargs: {"enabled": False, "vector_store": "turbovec"},
    )
    source_store = FakeSourceStore()
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path, source_store=source_store)

    uploaded = provider.upload_text(title="Ghi chu", text="Noi dung tu nguoi dung")
    document_chunks = provider.document_chunks(document_id=uploaded.document_id)

    assert uploaded.document_id in source_store.documents
    assert source_store.seen_metadata == {"title": "Ghi chu"}
    assert document_chunks.total_chunks == 1
    assert document_chunks.chunks[0].metadata["storage_chunk_id"] == (
        f"{uploaded.document_id}:0001"
    )
    documents = provider.list_documents()
    assert len(documents) == 1
    assert documents[0].document_id == uploaded.document_id
    assert documents[0].chunks[0].text == "Noi dung tu nguoi dung"


def test_local_pdf_provider_source_store_mode_does_not_write_local_cache(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeSourceStore:
        def __init__(self) -> None:
            self.documents: dict[str, list[Chunk]] = {}
            self.markdown_seen: str | None = None

        def write_document(self, **kwargs: Any) -> None:
            markdown_path = cast(Path, kwargs["markdown_path"])
            self.markdown_seen = markdown_path.read_text(encoding="utf-8")
            self.documents[str(kwargs["document_id"])] = cast(list[Chunk], kwargs["chunks"])

        def read_chunks(self, document_id: str) -> list[Chunk]:
            return self.documents.get(document_id, [])

        def read_all_chunks(self) -> list[Chunk]:
            return [chunk for chunks in self.documents.values() for chunk in chunks]

        def read_chunks_for_documents(self, document_ids: list[str]) -> list[Chunk]:
            return [chunk for doc_id in document_ids for chunk in self.documents.get(doc_id, [])]

        def list_documents(self) -> list[StoredSourceDocument]:
            return []

        def delete_document(self, document_id: str) -> None:
            self.documents.pop(document_id, None)

        def delete_all_documents(self) -> int:
            count = len(self.documents)
            self.documents.clear()
            return count

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        lambda chunks, **kwargs: {"enabled": False, "vector_store": "turbovec"},
    )
    source_store = FakeSourceStore()
    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        source_store=cast(Any, source_store),
    )

    uploaded = provider.upload_text(title="Ghi chu", text="Noi dung tu nguoi dung")

    assert uploaded.document_id in source_store.documents
    assert source_store.markdown_seen == "Noi dung tu nguoi dung"
    assert not (tmp_path / "chunks").exists()
    assert not (tmp_path / "parsed").exists()
    assert not (tmp_path / "files").exists()
    assert not (tmp_path / "debug").exists()
    assert not (tmp_path / "artifacts").exists()


def test_local_pdf_provider_preserves_source_store_when_dense_index_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeSourceStore:
        def __init__(self) -> None:
            self.documents: dict[str, list[Chunk]] = {}

        def write_document(self, **kwargs: Any) -> None:
            self.documents[str(kwargs["document_id"])] = cast(list[Chunk], kwargs["chunks"])

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.dense_embedding_metadata",
        lambda: {
            "requested_provider": "auto",
            "resolved_provider": "local",
            "fallback_reason": "openai_api_key_missing",
            "model": "local-model",
        },
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        lambda chunks, **kwargs: (_ for _ in ()).throw(
            ConnectionError("local endpoint unavailable")
        ),
    )
    source_store = FakeSourceStore()
    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        source_store=cast(Any, source_store),
    )

    uploaded = provider.upload_text(title="Ghi chu", text="Noi dung tu nguoi dung")

    assert uploaded.document_id in source_store.documents
    trace = cast(dict[str, dict[str, Any]], uploaded.trace)
    assert trace["index_write"]["source_store"]["enabled"] is True
    assert trace["index_write"]["dense_index"] == {
        "enabled": True,
        "status": "error",
        "error": "Dense indexing failed.",
        "requested_provider": "auto",
        "resolved_provider": "local",
        "fallback_reason": "openai_api_key_missing",
        "model": "local-model",
        "latency_ms": trace["index_write"]["dense_index"]["latency_ms"],
    }


def test_dense_search_failure_metadata_is_sanitized() -> None:
    class FakeStore:
        def dense_search(self, query: str, *, top_k: int) -> list[SearchResult]:
            raise RuntimeError("postgresql://user:secret-token@db.example/rag connection failed")

    results, error = providers_module._dense_search_safely(
        cast(Any, FakeStore()),
        "pin vf8",
        top_k=5,
    )

    assert results == []
    assert error == "Dense retrieval failed."
    assert "secret-token" not in error


def test_local_pdf_provider_rolls_back_source_store_when_qdrant_index_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeSourceStore:
        def __init__(self) -> None:
            self.documents: dict[str, list[Chunk]] = {}
            self.deleted: list[str] = []

        def write_document(self, **kwargs: Any) -> None:
            self.documents[str(kwargs["document_id"])] = cast(list[Chunk], kwargs["chunks"])

        def delete_document(self, document_id: str) -> None:
            self.deleted.append(document_id)
            self.documents.pop(document_id, None)

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    raw_qdrant_error = "api_key=secret-token url=https://qdrant.example.test"
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        lambda chunks, **kwargs: (_ for _ in ()).throw(ConnectionError(raw_qdrant_error)),
    )
    source_store = FakeSourceStore()
    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        source_store=cast(Any, source_store),
    )

    with pytest.raises(RuntimeError) as raised:
        provider.upload_text(title="Ghi chu", text="Noi dung tu nguoi dung")

    assert str(raised.value) == "Qdrant upsert failed; source storage was rolled back."
    assert "secret-token" not in str(raised.value)
    assert raw_qdrant_error not in str(raised.value)
    assert raised.value.__cause__ is not None
    assert source_store.documents == {}
    assert len(source_store.deleted) == 1


def test_local_pdf_provider_successful_generic_replacement_removes_obsolete_qdrant_points(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeSourceStore:
        def __init__(self) -> None:
            self.documents: dict[str, list[Chunk]] = {}

        def write_document(self, **kwargs: Any) -> None:
            self.documents[str(kwargs["document_id"])] = cast(list[Chunk], kwargs["chunks"])

        def read_chunks(self, document_id: str) -> list[Chunk]:
            return self.documents[document_id]

        def list_documents(self) -> list[StoredSourceDocument]:
            return [
                StoredSourceDocument(
                    document_id=document_id,
                    dataset_id="local_pdf",
                    name="note.txt",
                    source_type="text",
                    source="note.txt",
                    total_chunks=len(chunks),
                    metadata={},
                )
                for document_id, chunks in self.documents.items()
            ]

        def delete_document(self, document_id: str) -> None:
            self.documents.pop(document_id, None)

    def load_chunks(text: str, **kwargs: str) -> list[Chunk]:
        count = 3 if text == "long" else 1
        return [
            Chunk(
                chunk_id=f"text_doc_c{index:04d}",
                text=f"{text}-{index}",
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
            for index in range(1, count + 1)
        ]

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        load_chunks,
    )
    dense_state: dict[str, str] = {}

    def delete_points(document_id: str) -> dict[str, object]:
        dense_state.clear()
        return {"enabled": True, "document_id": document_id, "deleted": True}

    def upsert(chunks: list[Chunk], **_: object) -> dict[str, object]:
        dense_state.update({chunk.chunk_id: chunk.text for chunk in chunks})
        return {"enabled": True, "status": "ok", "count": len(chunks)}

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.delete_qdrant_document_points",
        delete_points,
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        upsert,
    )
    source_store = FakeSourceStore()
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path, source_store=cast(Any, source_store))

    provider.upload_text(title="Ghi chu", text="long")
    provider.upload_text(title="Ghi chu", text="short")

    assert dense_state == {"text_doc_c0001": "short-1"}
    assert [chunk.text for chunk in source_store.read_chunks("text_doc")] == ["short-1"]


def test_local_pdf_provider_restores_generic_source_when_qdrant_replacement_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeSourceStore:
        def __init__(self) -> None:
            self.documents: dict[str, list[Chunk]] = {}

        def write_document(self, **kwargs: Any) -> None:
            self.documents[str(kwargs["document_id"])] = list(cast(list[Chunk], kwargs["chunks"]))

        def snapshot_document(self, document_id: str) -> list[Chunk] | None:
            chunks = self.documents.get(document_id)
            return list(chunks) if chunks is not None else None

        def restore_document(self, document_id: str, snapshot: list[Chunk]) -> None:
            self.documents[document_id] = list(snapshot)

        def read_chunks(self, document_id: str) -> list[Chunk]:
            return self.documents[document_id]

        def list_documents(self) -> list[StoredSourceDocument]:
            return [
                StoredSourceDocument(
                    document_id=document_id,
                    dataset_id="local_pdf",
                    name="note.txt",
                    source_type="text",
                    source="note.txt",
                    total_chunks=len(chunks),
                    metadata={},
                )
                for document_id, chunks in self.documents.items()
            ]

        def delete_document(self, document_id: str) -> None:
            self.documents.pop(document_id, None)

    def load_chunks(text: str, **kwargs: str) -> list[Chunk]:
        label = "old" if text == "original" else "new"
        return [
            Chunk(
                chunk_id=f"text_doc_c{index:04d}",
                text=f"{label}-{index}",
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
            for index in range(1, 3)
        ]

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        load_chunks,
    )
    dense_state: dict[str, str] = {}
    replacement_failed = False

    def delete_points(document_id: str) -> dict[str, object]:
        dense_state.clear()
        return {"enabled": True, "document_id": document_id, "deleted": True}

    def upsert(chunks: list[Chunk], **_: object) -> dict[str, object]:
        nonlocal replacement_failed
        for chunk in chunks:
            dense_state[chunk.chunk_id] = chunk.text
            if chunk.text == "new-2" and not replacement_failed:
                replacement_failed = True
                raise ConnectionError("api_key=secret-token")
        return {"enabled": True, "status": "ok", "count": len(chunks)}

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.delete_qdrant_document_points",
        delete_points,
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        upsert,
    )
    source_store = FakeSourceStore()
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path, source_store=cast(Any, source_store))

    provider.upload_text(title="Ghi chu", text="original")
    with pytest.raises(RuntimeError, match="source storage was restored"):
        provider.upload_text(title="Ghi chu", text="replacement")

    assert replacement_failed is True
    assert dense_state == {
        "text_doc_c0001": "old-1",
        "text_doc_c0002": "old-2",
    }
    assert [chunk.text for chunk in source_store.read_chunks("text_doc")] == [
        "old-1",
        "old-2",
    ]


def test_local_pdf_provider_cleans_partial_qdrant_points_without_source_store(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    dense_state: dict[str, str] = {}

    def fail_after_partial_write(chunks: list[Chunk], **_: object) -> dict[str, object]:
        dense_state[chunks[0].chunk_id] = chunks[0].text
        raise ConnectionError("api_key=secret-token")

    def delete_points(document_id: str) -> dict[str, object]:
        dense_state.clear()
        return {"enabled": True, "document_id": document_id, "deleted": True}

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        fail_after_partial_write,
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.delete_qdrant_document_points",
        delete_points,
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    with pytest.raises(RuntimeError, match="partial dense index was cleaned"):
        provider.upload_text(title="Ghi chu", text="Noi dung tu nguoi dung")

    assert dense_state == {}


def test_local_pdf_provider_restores_jsonl_source_when_qdrant_replacement_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    def load_chunks(text: str, **kwargs: str) -> list[Chunk]:
        label = "old" if text == "original" else "new"
        return [
            Chunk(
                chunk_id=f"text_doc_c{index:04d}",
                text=f"{label}-{index}",
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
            for index in range(1, 3)
        ]

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        load_chunks,
    )
    dense_state: dict[str, str] = {}
    replacement_failed = False

    def delete_points(document_id: str) -> dict[str, object]:
        dense_state.clear()
        return {"enabled": True, "document_id": document_id, "deleted": True}

    def upsert(chunks: list[Chunk], **_: object) -> dict[str, object]:
        nonlocal replacement_failed
        for chunk in chunks:
            dense_state[chunk.chunk_id] = chunk.text
            if chunk.text == "new-2" and not replacement_failed:
                replacement_failed = True
                raise ConnectionError("api_key=secret-token")
        return {"enabled": True, "status": "ok", "count": len(chunks)}

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.delete_qdrant_document_points",
        delete_points,
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        upsert,
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    provider.upload_text(title="Ghi chu", text="original")
    with pytest.raises(RuntimeError, match="partial dense index was cleaned"):
        provider.upload_text(title="Ghi chu", text="replacement")

    assert replacement_failed is True
    assert dense_state == {
        "text_doc_c0001": "old-1",
        "text_doc_c0002": "old-2",
    }
    assert [chunk.text for chunk in provider._read_chunks("text_doc")] == [
        "old-1",
        "old-2",
    ]
    assert provider._markdown_path("text_doc").read_text(encoding="utf-8") == "original"


def test_local_pdf_provider_sanitizes_jsonl_qdrant_repair_failure_after_restore(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    def load_chunks(text: str, **kwargs: str) -> list[Chunk]:
        label = "old" if text == "original" else "new"
        return [
            Chunk(
                chunk_id=f"text_doc_c{index:04d}",
                text=f"{label}-{index}",
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
            for index in range(1, 3)
        ]

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        load_chunks,
    )
    raw_qdrant_error = "api_key=secret-token url=https://qdrant.example.test"
    call_count = 0

    def upsert(chunks: list[Chunk], **_: object) -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"enabled": True, "status": "ok", "count": len(chunks)}
        raise ConnectionError(raw_qdrant_error)

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        upsert,
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    provider.upload_text(title="Ghi chu", text="original")
    with pytest.raises(RuntimeError) as raised:
        provider.upload_text(title="Ghi chu", text="replacement")

    assert str(raised.value) == (
        "Qdrant upsert failed; local source storage was restored but dense index repair failed."
    )
    assert "secret-token" not in str(raised.value)
    assert raw_qdrant_error not in str(raised.value)
    assert [chunk.text for chunk in provider._read_chunks("text_doc")] == [
        "old-1",
        "old-2",
    ]
    assert provider._markdown_path("text_doc").read_text(encoding="utf-8") == "original"


def test_local_pdf_provider_marks_s3_source_orphaned_when_qdrant_index_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeBody:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    class FakeS3Client:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}
            self.delete_called = False

        def put_object(self, *, Bucket: str, Key: str, Body: bytes | str, **_: object) -> None:
            self.objects[Key] = Body.encode() if isinstance(Body, str) else Body

        def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            return {"Body": FakeBody(self.objects[Key])}

        def list_objects_v2(self, *, Bucket: str, Prefix: str, **_: object) -> dict[str, object]:
            return {
                "Contents": [
                    {"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)
                ],
                "IsTruncated": False,
            }

        def delete_objects(self, *, Bucket: str, Delete: dict[str, object]) -> None:
            self.delete_called = True
            raise AssertionError("S3 rollback must not delete objects")

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    raw_qdrant_error = "api_key=secret-token url=https://qdrant.example.test"
    dense_state: dict[str, str] = {}

    def fail_after_partial_write(
        chunks: list[Chunk],
        **_: object,
    ) -> dict[str, object]:
        assert chunks[0].chunk_id == "text_doc_c0001"
        dense_state[chunks[0].chunk_id] = chunks[0].text
        raise ConnectionError(raw_qdrant_error)

    def delete_partial_points(document_id: str) -> dict[str, object]:
        dense_state.clear()
        return {"enabled": True, "document_id": document_id, "deleted": True}

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        fail_after_partial_write,
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.delete_qdrant_document_points",
        delete_partial_points,
    )
    client = FakeS3Client()
    source_store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        source_store=source_store,
    )

    with pytest.raises(RuntimeError) as raised:
        provider.upload_text(title="Ghi chu", text="Noi dung tu nguoi dung")

    error_message = str(raised.value)
    assert error_message == "Qdrant upsert failed; S3 source storage was marked orphaned."
    assert "secret-token" not in error_message
    assert "api_key" not in error_message
    assert "qdrant.example.test" not in error_message
    assert raw_qdrant_error not in error_message
    assert isinstance(raised.value.__cause__, ConnectionError)
    assert str(raised.value.__cause__) == raw_qdrant_error
    assert client.delete_called is False
    manifest = json.loads(client.objects["sources/text_doc/manifest.json"].decode())
    assert manifest["metadata"]["source_index_status"] == "orphaned"
    assert manifest["metadata"]["source_index_reason"] == "qdrant_upsert_failed"
    assert dense_state == {}


def test_local_pdf_provider_restores_existing_s3_source_when_qdrant_reupload_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeBody:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    class FakeS3Client:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}

        def put_object(self, *, Bucket: str, Key: str, Body: bytes | str, **_: object) -> None:
            self.objects[Key] = Body.encode() if isinstance(Body, str) else Body

        def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            return {"Body": FakeBody(self.objects[Key])}

        def list_objects_v2(self, *, Bucket: str, Prefix: str, **_: object) -> dict[str, object]:
            return {
                "Contents": [
                    {"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)
                ],
                "IsTruncated": False,
            }

        def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> None:
            for item in cast(list[dict[str, object]], Delete["Objects"]):
                self.objects.pop(str(item["Key"]), None)

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    upsert_count = 0

    def upsert(chunks: list[Chunk], **_: object) -> dict[str, object]:
        nonlocal upsert_count
        upsert_count += 1
        if upsert_count == 2:
            raise ConnectionError("api_key=secret-token")
        return {"enabled": True, "status": "ok", "count": len(chunks)}

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        upsert,
    )
    client = FakeS3Client()
    source_store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path, source_store=source_store)

    uploaded = provider.upload_text(title="Ghi chu", text="Noi dung ban dau")
    original_objects = dict(client.objects)

    with pytest.raises(
        RuntimeError,
        match="Qdrant upsert failed; existing S3 source storage was restored",
    ):
        provider.upload_text(title="Ghi chu", text="Noi dung thay the")

    assert client.objects == original_objects
    assert [document.document_id for document in source_store.list_documents()] == [
        uploaded.document_id
    ]
    assert source_store.read_chunks(uploaded.document_id)[0].text == "Noi dung ban dau"


def test_local_pdf_provider_repairs_partial_multi_batch_qdrant_replacement(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeBody:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    class FakeS3Client:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}

        def put_object(self, *, Bucket: str, Key: str, Body: bytes | str, **_: object) -> None:
            self.objects[Key] = Body.encode() if isinstance(Body, str) else Body

        def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            return {"Body": FakeBody(self.objects[Key])}

        def list_objects_v2(self, *, Bucket: str, Prefix: str, **_: object) -> dict[str, object]:
            return {
                "Contents": [
                    {"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)
                ],
                "IsTruncated": False,
            }

        def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> None:
            for item in cast(list[dict[str, object]], Delete["Objects"]):
                self.objects.pop(str(item["Key"]), None)

    def load_chunks(text: str, **kwargs: str) -> list[Chunk]:
        label = "old" if text == "original" else "new"
        return [
            Chunk(
                chunk_id=f"text_doc_c{index:04d}",
                text=f"{label}-{index}",
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
            for index in range(1, 3)
        ]

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setenv("DENSE_EMBED_BATCH_SIZE", "1")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        load_chunks,
    )
    dense_state: dict[str, str] = {}
    replacement_failed = False

    def delete_points(document_id: str) -> dict[str, object]:
        dense_state.clear()
        return {"enabled": True, "document_id": document_id, "deleted": True}

    def upsert(chunks: list[Chunk], **_: object) -> dict[str, object]:
        nonlocal replacement_failed
        assert os.environ["DENSE_EMBED_BATCH_SIZE"] == "1"
        for chunk in chunks:
            dense_state[chunk.chunk_id] = chunk.text
            if chunk.text == "new-2" and not replacement_failed:
                replacement_failed = True
                raise ConnectionError("api_key=secret-token")
        return {"enabled": True, "status": "ok", "count": len(chunks)}

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.delete_qdrant_document_points",
        delete_points,
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        upsert,
    )
    source_store = S3LocalSourceStore(
        bucket="rag-bucket",
        prefix="sources",
        client=FakeS3Client(),
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path, source_store=source_store)

    provider.upload_text(title="Ghi chu", text="original")

    with pytest.raises(
        RuntimeError,
        match="Qdrant upsert failed; existing S3 source storage was restored",
    ):
        provider.upload_text(title="Ghi chu", text="replacement")

    assert replacement_failed is True
    assert dense_state == {
        "text_doc_c0001": "old-1",
        "text_doc_c0002": "old-2",
    }
    assert [chunk.text for chunk in source_store.read_chunks("text_doc")] == [
        "old-1",
        "old-2",
    ]


def test_local_pdf_provider_successful_shorter_replacement_removes_obsolete_points(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeBody:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    class FakeS3Client:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}

        def put_object(self, *, Bucket: str, Key: str, Body: bytes | str, **_: object) -> None:
            self.objects[Key] = Body.encode() if isinstance(Body, str) else Body

        def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            return {"Body": FakeBody(self.objects[Key])}

        def list_objects_v2(self, *, Bucket: str, Prefix: str, **_: object) -> dict[str, object]:
            return {
                "Contents": [
                    {"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)
                ],
                "IsTruncated": False,
            }

        def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> None:
            for item in cast(list[dict[str, object]], Delete["Objects"]):
                self.objects.pop(str(item["Key"]), None)

    def load_chunks(text: str, **kwargs: str) -> list[Chunk]:
        count = 3 if text == "long" else 1
        return [
            Chunk(
                chunk_id=f"text_doc_c{index:04d}",
                text=f"{text}-{index}",
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
            for index in range(1, count + 1)
        ]

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        load_chunks,
    )
    dense_state: dict[str, str] = {}

    def delete_points(document_id: str) -> dict[str, object]:
        dense_state.clear()
        return {"enabled": True, "document_id": document_id, "deleted": True}

    def upsert(chunks: list[Chunk], **_: object) -> dict[str, object]:
        dense_state.update({chunk.chunk_id: chunk.text for chunk in chunks})
        return {"enabled": True, "status": "ok", "count": len(chunks)}

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.delete_qdrant_document_points",
        delete_points,
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        upsert,
    )
    source_store = S3LocalSourceStore(
        bucket="rag-bucket",
        prefix="sources",
        client=FakeS3Client(),
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path, source_store=source_store)

    provider.upload_text(title="Ghi chu", text="long")
    assert set(dense_state) == {
        "text_doc_c0001",
        "text_doc_c0002",
        "text_doc_c0003",
    }

    provider.upload_text(title="Ghi chu", text="short")

    assert dense_state == {"text_doc_c0001": "short-1"}
    assert [chunk.text for chunk in source_store.read_chunks("text_doc")] == ["short-1"]


def test_local_pdf_provider_restores_existing_s3_source_when_replacement_write_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeBody:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    class FakeS3Client:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}
            self.fail_next_chunks_write = False

        def put_object(self, *, Bucket: str, Key: str, Body: bytes | str, **_: object) -> None:
            if self.fail_next_chunks_write and Key.endswith("/chunks/chunks.jsonl"):
                self.fail_next_chunks_write = False
                raise RuntimeError("aws_secret_access_key=secret-token")
            self.objects[Key] = Body.encode() if isinstance(Body, str) else Body

        def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            return {"Body": FakeBody(self.objects[Key])}

        def list_objects_v2(self, *, Bucket: str, Prefix: str, **_: object) -> dict[str, object]:
            return {
                "Contents": [
                    {"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)
                ],
                "IsTruncated": False,
            }

        def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> None:
            for item in cast(list[dict[str, object]], Delete["Objects"]):
                self.objects.pop(str(item["Key"]), None)

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    upsert_count = 0

    def upsert(chunks: list[Chunk], **_: object) -> dict[str, object]:
        nonlocal upsert_count
        upsert_count += 1
        return {"enabled": True, "status": "ok", "count": len(chunks)}

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        upsert,
    )
    client = FakeS3Client()
    source_store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path, source_store=source_store)
    uploaded = provider.upload_text(title="Ghi chu", text="Noi dung ban dau")
    original_objects = dict(client.objects)
    client.fail_next_chunks_write = True

    with pytest.raises(
        RuntimeError,
        match="S3 source replacement failed; existing S3 source storage was restored",
    ) as raised:
        provider.upload_text(title="Ghi chu", text="Noi dung thay the")

    assert "secret-token" not in str(raised.value)
    assert client.objects == original_objects
    assert source_store.read_chunks(uploaded.document_id)[0].text == "Noi dung ban dau"
    assert upsert_count == 1


def test_local_pdf_provider_removes_partial_stage_when_first_source_write_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeS3Client:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}

        def put_object(self, *, Bucket: str, Key: str, Body: bytes | str, **_: object) -> None:
            if Key.endswith("/chunks/chunks.jsonl"):
                raise RuntimeError("aws_secret_access_key=secret-token")
            self.objects[Key] = Body.encode() if isinstance(Body, str) else Body

        def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            raise KeyError(Key)

        def list_objects_v2(self, *, Bucket: str, Prefix: str, **_: object) -> dict[str, object]:
            return {
                "Contents": [
                    {"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)
                ],
                "IsTruncated": False,
            }

        def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> None:
            for item in cast(list[dict[str, object]], Delete["Objects"]):
                self.objects.pop(str(item["Key"]), None)

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    client = FakeS3Client()
    source_store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path, source_store=source_store)

    with pytest.raises(RuntimeError) as raised:
        provider.upload_text(title="Ghi chu", text="Noi dung")

    assert "secret-token" not in str(raised.value)
    assert client.objects == {}


def test_local_pdf_provider_successful_replacements_prune_prior_active_versions(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeBody:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    class FakeS3Client:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}

        def put_object(self, *, Bucket: str, Key: str, Body: bytes | str, **_: object) -> None:
            self.objects[Key] = Body.encode() if isinstance(Body, str) else Body

        def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            return {"Body": FakeBody(self.objects[Key])}

        def list_objects_v2(self, *, Bucket: str, Prefix: str, **_: object) -> dict[str, object]:
            return {
                "Contents": [
                    {"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)
                ],
                "IsTruncated": False,
            }

        def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> None:
            for item in cast(list[dict[str, object]], Delete["Objects"]):
                self.objects.pop(str(item["Key"]), None)

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        lambda chunks, **kwargs: {
            "enabled": True,
            "status": "ok",
            "count": len(chunks),
        },
    )
    client = FakeS3Client()
    source_store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path, source_store=source_store)

    for content in ("Noi dung mot", "Noi dung hai", "Noi dung ba"):
        provider.upload_text(title="Ghi chu", text=content)

    version_prefixes = {
        key.rsplit("/", 2)[0] for key in client.objects if key.endswith("/chunks/chunks.jsonl")
    }

    assert len(version_prefixes) == 1
    assert source_store.read_chunks("text_doc")[0].text == "Noi dung ba"


def test_local_pdf_provider_serializes_concurrent_s3_replacements(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeBody:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    class FakeS3Client:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}
            self.objects_guard = threading.Lock()

        def put_object(self, *, Bucket: str, Key: str, Body: bytes | str, **_: object) -> None:
            with self.objects_guard:
                self.objects[Key] = Body.encode() if isinstance(Body, str) else Body

        def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            with self.objects_guard:
                payload = self.objects[Key]
            return {"Body": FakeBody(payload)}

        def list_objects_v2(self, *, Bucket: str, Prefix: str, **_: object) -> dict[str, object]:
            with self.objects_guard:
                keys = [key for key in sorted(self.objects) if key.startswith(Prefix)]
            return {
                "Contents": [{"Key": key} for key in keys],
                "IsTruncated": False,
            }

        def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> None:
            with self.objects_guard:
                for item in cast(list[dict[str, object]], Delete["Objects"]):
                    self.objects.pop(str(item["Key"]), None)

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    successful_upsert_started = threading.Event()
    release_successful_upsert = threading.Event()
    failed_upsert_started = threading.Event()

    def upsert(chunks: list[Chunk], **_: object) -> dict[str, object]:
        text = chunks[0].text
        if text == "Noi dung thanh cong":
            successful_upsert_started.set()
            assert release_successful_upsert.wait(timeout=5)
        elif text == "Noi dung that bai":
            failed_upsert_started.set()
            raise ConnectionError("api_key=secret-token")
        return {"enabled": True, "status": "ok", "count": len(chunks)}

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        upsert,
    )
    client = FakeS3Client()
    first_store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    second_store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    first_provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path / "first",
        source_store=first_store,
    )
    second_provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path / "second",
        source_store=second_store,
    )
    first_provider.upload_text(title="Ghi chu", text="Noi dung ban dau")

    with ThreadPoolExecutor(max_workers=2) as executor:
        successful = executor.submit(
            first_provider.upload_text,
            title="Ghi chu",
            text="Noi dung thanh cong",
        )
        assert successful_upsert_started.wait(timeout=5)
        failed = executor.submit(
            second_provider.upload_text,
            title="Ghi chu",
            text="Noi dung that bai",
        )
        assert not failed_upsert_started.wait(timeout=0.2)
        release_successful_upsert.set()
        successful.result(timeout=5)
        with pytest.raises(
            RuntimeError,
            match="Qdrant upsert failed; existing S3 source storage was restored",
        ):
            failed.result(timeout=5)

    assert failed_upsert_started.is_set()
    assert first_store.read_chunks("text_doc")[0].text == "Noi dung thanh cong"


def test_local_pdf_provider_does_not_restore_stale_s3_snapshot_across_lock_domains(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class PreconditionFailed(Exception):
        def __init__(self) -> None:
            self.response = {"Error": {"Code": "PreconditionFailed"}}

    class FakeBody:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    class FakeS3Client:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}
            self.etags: dict[str, str] = {}
            self.revision = 0
            self.guard = threading.Lock()

        def put_object(
            self,
            *,
            Bucket: str,
            Key: str,
            Body: bytes | str,
            IfMatch: str | None = None,
            **_: object,
        ) -> None:
            with self.guard:
                if IfMatch is not None and self.etags.get(Key) != IfMatch:
                    raise PreconditionFailed
                self.revision += 1
                self.objects[Key] = Body.encode() if isinstance(Body, str) else Body
                self.etags[Key] = f'"revision-{self.revision}"'

        def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            with self.guard:
                payload = self.objects[Key]
                etag = self.etags[Key]
            return {"Body": FakeBody(payload), "ETag": etag}

        def list_objects_v2(self, *, Bucket: str, Prefix: str, **_: object) -> dict[str, object]:
            with self.guard:
                keys = [key for key in sorted(self.objects) if key.startswith(Prefix)]
            return {
                "Contents": [{"Key": key} for key in keys],
                "IsTruncated": False,
            }

        def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> None:
            with self.guard:
                for item in cast(list[dict[str, object]], Delete["Objects"]):
                    key = str(item["Key"])
                    self.objects.pop(key, None)
                    self.etags.pop(key, None)

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    stale_upsert_started = threading.Event()
    release_stale_upsert = threading.Event()

    def upsert(chunks: list[Chunk], **_: object) -> dict[str, object]:
        if chunks[0].text == "Noi dung that bai":
            stale_upsert_started.set()
            assert release_stale_upsert.wait(timeout=5)
            raise ConnectionError("api_key=secret-token")
        return {"enabled": True, "status": "ok", "count": len(chunks)}

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        upsert,
    )
    client = FakeS3Client()
    stale_store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    newer_store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    stale_provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path / "stale",
        source_store=stale_store,
    )
    newer_provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path / "newer",
        source_store=newer_store,
    )
    stale_provider.upload_text(title="Ghi chu", text="Noi dung ban dau")

    monkeypatch.setattr(
        stale_store,
        "document_write_lock",
        lambda document_id: nullcontext(),
    )
    monkeypatch.setattr(
        newer_store,
        "document_write_lock",
        lambda document_id: nullcontext(),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        stale = executor.submit(
            stale_provider.upload_text,
            title="Ghi chu",
            text="Noi dung that bai",
        )
        assert stale_upsert_started.wait(timeout=5)
        newer_provider.upload_text(title="Ghi chu", text="Noi dung moi hon")
        release_stale_upsert.set()
        with pytest.raises(
            RuntimeError,
            match="Qdrant upsert failed; S3 source transaction was superseded",
        ) as raised:
            stale.result(timeout=5)

    assert isinstance(raised.value.__cause__, ConnectionError)
    assert "secret-token" not in str(raised.value)
    assert newer_store.read_chunks("text_doc")[0].text == "Noi dung moi hon"
    manifest = json.loads(client.objects["sources/text_doc/manifest.json"].decode())
    assert manifest["chunks_key"] in client.objects


def test_local_pdf_provider_repairs_dense_index_after_successful_stale_upsert(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class PreconditionFailed(Exception):
        def __init__(self) -> None:
            self.response = {"Error": {"Code": "PreconditionFailed"}}

    class FakeBody:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    class FakeS3Client:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}
            self.etags: dict[str, str] = {}
            self.revision = 0
            self.guard = threading.Lock()

        def put_object(
            self,
            *,
            Bucket: str,
            Key: str,
            Body: bytes | str,
            IfMatch: str | None = None,
            **_: object,
        ) -> None:
            with self.guard:
                if IfMatch is not None and self.etags.get(Key) != IfMatch:
                    raise PreconditionFailed
                self.revision += 1
                self.objects[Key] = Body.encode() if isinstance(Body, str) else Body
                self.etags[Key] = f'"revision-{self.revision}"'

        def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            with self.guard:
                payload = self.objects[Key]
                etag = self.etags[Key]
            return {"Body": FakeBody(payload), "ETag": etag}

        def list_objects_v2(self, *, Bucket: str, Prefix: str, **_: object) -> dict[str, object]:
            with self.guard:
                keys = [key for key in sorted(self.objects) if key.startswith(Prefix)]
            return {
                "Contents": [{"Key": key} for key in keys],
                "IsTruncated": False,
            }

        def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> None:
            with self.guard:
                for item in cast(list[dict[str, object]], Delete["Objects"]):
                    key = str(item["Key"])
                    self.objects.pop(key, None)
                    self.etags.pop(key, None)

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    stale_upsert_started = threading.Event()
    release_stale_upsert = threading.Event()
    dense_state: dict[str, str] = {}

    def upsert(chunks: list[Chunk], **_: object) -> dict[str, object]:
        text = chunks[0].text
        if text == "Noi dung cu hoan tat sau":
            stale_upsert_started.set()
            assert release_stale_upsert.wait(timeout=5)
        dense_state["text_doc"] = text
        return {"enabled": True, "status": "ok", "count": len(chunks)}

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        upsert,
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.delete_qdrant_document_points",
        lambda document_id: dense_state.pop(document_id, None),
    )
    client = FakeS3Client()
    stale_store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    winner_store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    stale_provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path / "stale",
        source_store=stale_store,
    )
    winner_provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path / "winner",
        source_store=winner_store,
    )
    stale_provider.upload_text(title="Ghi chu", text="Noi dung ban dau")

    monkeypatch.setattr(
        stale_store,
        "document_write_lock",
        lambda document_id: nullcontext(),
    )
    monkeypatch.setattr(
        winner_store,
        "document_write_lock",
        lambda document_id: nullcontext(),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        stale = executor.submit(
            stale_provider.upload_text,
            title="Ghi chu",
            text="Noi dung cu hoan tat sau",
        )
        assert stale_upsert_started.wait(timeout=5)
        winner_provider.upload_text(title="Ghi chu", text="Noi dung canonical moi")
        assert dense_state["text_doc"] == "Noi dung canonical moi"
        release_stale_upsert.set()
        with pytest.raises(
            RuntimeError,
            match=(
                "Qdrant upsert succeeded but S3 source transaction was superseded; "
                "dense index was repaired"
            ),
        ):
            stale.result(timeout=5)

    canonical_text = winner_store.read_chunks("text_doc")[0].text
    assert canonical_text == "Noi dung canonical moi"
    assert dense_state["text_doc"] == canonical_text
    manifest = json.loads(client.objects["sources/text_doc/manifest.json"].decode())
    assert manifest["chunks_key"] in client.objects


def test_local_pdf_provider_sanitizes_s3_orphan_marking_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeBody:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    class FakeS3Client:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}
            self.delete_called = False

        def put_object(self, *, Bucket: str, Key: str, Body: bytes | str, **_: object) -> None:
            self.objects[Key] = Body.encode() if isinstance(Body, str) else Body

        def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            return {"Body": FakeBody(self.objects[Key])}

        def list_objects_v2(self, *, Bucket: str, Prefix: str, **_: object) -> dict[str, object]:
            return {
                "Contents": [
                    {"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)
                ],
                "IsTruncated": False,
            }

        def delete_objects(self, *, Bucket: str, Delete: dict[str, object]) -> None:
            self.delete_called = True
            raise AssertionError("S3 rollback must not delete objects")

    raw_qdrant_error = "api_key=secret-token url=https://qdrant.example.test"
    raw_orphan_error = "aws_secret_access_key=secret-token bucket=https://s3.example.test"

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ],
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        lambda chunks, **kwargs: (_ for _ in ()).throw(ConnectionError(raw_qdrant_error)),
    )
    client = FakeS3Client()
    source_store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    def fail_mark_document_orphaned(
        document_id: str,
        *,
        transaction_id: str,
        reason: str,
    ) -> bool:
        raise RuntimeError(raw_orphan_error)

    monkeypatch.setattr(
        source_store,
        "mark_document_orphaned_if_current",
        fail_mark_document_orphaned,
    )
    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        source_store=source_store,
    )

    with pytest.raises(RuntimeError) as raised:
        provider.upload_text(title="Ghi chu", text="Noi dung tu nguoi dung")

    error_message = str(raised.value)
    assert error_message == "Qdrant upsert failed and S3 orphan marking failed."
    assert "secret-token" not in error_message
    assert "api_key" not in error_message
    assert "aws_secret_access_key" not in error_message
    assert "qdrant.example.test" not in error_message
    assert "s3.example.test" not in error_message
    assert raw_qdrant_error not in error_message
    assert raw_orphan_error not in error_message
    assert isinstance(raised.value.__cause__, ConnectionError)
    assert str(raised.value.__cause__) == raw_qdrant_error
    assert client.delete_called is False


@pytest.mark.parametrize("source_type", ["text", "url", "pdf"])
def test_local_pdf_provider_validates_vector_config_before_local_ingestion(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    source_type: str,
) -> None:
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.delenv("VECTOR_STORE_URL", raising=False)

    def fail_loader(*args: object, **kwargs: object) -> object:
        raise AssertionError("loader must not run")

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        fail_loader,
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_url_with_artifacts",
        fail_loader,
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_pdf_with_markdown",
        fail_loader,
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    with pytest.raises(ValueError, match="VECTOR_STORE_URL"):
        if source_type == "text":
            provider.upload_text(title="Ghi chu", text="Noi dung tu nguoi dung")
        elif source_type == "url":
            provider.upload_url(url="https://example.test/source")
        else:
            provider.upload_document(
                filename="source.pdf",
                content=b"%PDF-1.4",
                content_type="application/pdf",
            )

    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_local_pdf_provider_reuses_validated_vector_config_for_indexing(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_load_text_chunks(text: str, **kwargs: object) -> list[Chunk]:
        monkeypatch.delenv("VECTOR_STORE_URL")
        return [
            Chunk(
                chunk_id="text_doc_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ]

    def fake_upsert_dense_embeddings(
        chunks: list[Chunk],
        *,
        vector_config: object,
    ) -> dict[str, object]:
        seen["vector_config"] = vector_config
        return {"enabled": True, "vector_store": "qdrant"}

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        fake_load_text_chunks,
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.upsert_dense_embeddings",
        fake_upsert_dense_embeddings,
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    provider.upload_text(title="Ghi chu", text="Noi dung tu nguoi dung")

    vector_config = cast(VectorStoreConfig, seen["vector_config"])
    assert vector_config.provider == "qdrant"
    url = vector_config.url
    assert url is not None
    assert url.get_secret_value() == "https://qdrant.example.test"


def test_source_store_from_env_prefers_explicit_postgres_connection(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    class FakePostgresLocalSourceStore:
        def __init__(self, *, connection: str, table_prefix: str) -> None:
            seen.update(connection=connection, table_prefix=table_prefix)

    monkeypatch.setenv("LOCAL_SOURCE_STORE", "postgres")
    monkeypatch.setenv("LOCAL_SOURCE_POSTGRES_CONNECTION", "postgresql://source/rag")
    monkeypatch.setenv("DENSE_PGVECTOR_CONNECTION", "postgresql://legacy/rag")
    monkeypatch.setattr(
        providers_module,
        "PostgresLocalSourceStore",
        FakePostgresLocalSourceStore,
    )

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        providers_module._source_store_from_env()

    assert seen == {
        "connection": "postgresql://source/rag",
        "table_prefix": "local_rag",
    }
    assert not caught_warnings


def test_source_store_from_env_uses_pgvector_url_second(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    class FakePostgresLocalSourceStore:
        def __init__(self, *, connection: str, table_prefix: str) -> None:
            seen.update(connection=connection, table_prefix=table_prefix)

    monkeypatch.setenv("LOCAL_SOURCE_STORE", "postgres")
    monkeypatch.delenv("LOCAL_SOURCE_POSTGRES_CONNECTION", raising=False)
    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "pgvector")
    monkeypatch.setenv("VECTOR_STORE_URL", "postgresql://user:secret@db.example/rag")
    monkeypatch.setenv("DENSE_PGVECTOR_CONNECTION", "postgresql://legacy/rag")
    monkeypatch.setattr(
        providers_module,
        "PostgresLocalSourceStore",
        FakePostgresLocalSourceStore,
    )

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        providers_module._source_store_from_env()

    assert seen["connection"] == "postgresql://user:secret@db.example/rag"
    assert not caught_warnings


def test_source_store_from_env_prefers_canonical_url_with_legacy_provider(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    class FakePostgresLocalSourceStore:
        def __init__(self, *, connection: str, table_prefix: str) -> None:
            seen.update(connection=connection, table_prefix=table_prefix)

    monkeypatch.setenv("LOCAL_SOURCE_STORE", "postgres")
    monkeypatch.delenv("LOCAL_SOURCE_POSTGRES_CONNECTION", raising=False)
    monkeypatch.delenv("VECTOR_STORE_PROVIDER", raising=False)
    monkeypatch.setenv("VECTOR_STORE_URL", "postgresql://canonical/rag")
    monkeypatch.setenv("DENSE_VECTOR_STORE", "pgvector")
    monkeypatch.setenv("DENSE_PGVECTOR_CONNECTION", "postgresql://legacy/rag")
    monkeypatch.setattr(
        providers_module,
        "PostgresLocalSourceStore",
        FakePostgresLocalSourceStore,
    )

    providers_module._source_store_from_env()

    assert seen["connection"] == "postgresql://canonical/rag"


def test_source_store_from_env_warns_for_legacy_postgres_fallback(
    monkeypatch: MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    class FakePostgresLocalSourceStore:
        def __init__(self, *, connection: str, table_prefix: str) -> None:
            seen.update(connection=connection, table_prefix=table_prefix)

    monkeypatch.setenv("LOCAL_SOURCE_STORE", "postgres")
    monkeypatch.delenv("LOCAL_SOURCE_POSTGRES_CONNECTION", raising=False)
    monkeypatch.delenv("VECTOR_STORE_PROVIDER", raising=False)
    monkeypatch.delenv("VECTOR_STORE_URL", raising=False)
    monkeypatch.setenv("DENSE_PGVECTOR_CONNECTION", "postgresql://legacy/rag")
    monkeypatch.setattr(
        providers_module,
        "PostgresLocalSourceStore",
        FakePostgresLocalSourceStore,
    )

    with pytest.warns(
        FutureWarning,
        match=(
            "DENSE_PGVECTOR_CONNECTION is deprecated for "
            "LOCAL_SOURCE_STORE=postgres; use "
            "LOCAL_SOURCE_POSTGRES_CONNECTION instead"
        ),
    ):
        providers_module._source_store_from_env()

    assert seen["connection"] == "postgresql://legacy/rag"


def test_source_store_from_env_requires_postgres_connection(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_SOURCE_STORE", "postgres")
    monkeypatch.delenv("LOCAL_SOURCE_POSTGRES_CONNECTION", raising=False)
    monkeypatch.delenv("VECTOR_STORE_PROVIDER", raising=False)
    monkeypatch.delenv("VECTOR_STORE_URL", raising=False)
    monkeypatch.delenv("DENSE_PGVECTOR_CONNECTION", raising=False)

    with pytest.raises(ValueError, match="LOCAL_SOURCE_POSTGRES_CONNECTION"):
        providers_module._source_store_from_env()


def test_local_pdf_provider_hides_orphaned_source_documents(tmp_path: Path) -> None:
    class FakeSourceStore:
        def list_documents(self) -> list[StoredSourceDocument]:
            return [
                StoredSourceDocument(
                    document_id="doc-ready",
                    dataset_id="local_pdf",
                    name="ready.txt",
                    source_type="text",
                    source="ready.txt",
                    total_chunks=1,
                    metadata={"source_index_status": "indexed"},
                ),
                StoredSourceDocument(
                    document_id="doc-orphaned",
                    dataset_id="local_pdf",
                    name="orphaned.txt",
                    source_type="text",
                    source="orphaned.txt",
                    total_chunks=1,
                    metadata={"source_index_status": "orphaned"},
                ),
            ]

    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        source_store=cast(Any, FakeSourceStore()),
    )

    documents = provider.list_documents(include_chunks=False)

    assert [document.document_id for document in documents] == ["doc-ready"]


def test_local_pdf_provider_does_not_delete_source_when_qdrant_document_delete_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeSourceStore:
        deleted = False

        def delete_document(self, document_id: str) -> None:
            self.deleted = True

    source_store = FakeSourceStore()
    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        source_store=cast(Any, source_store),
    )
    raw_qdrant_error = "api_key=secret-token url=https://qdrant.example.test"
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.delete_qdrant_document_points",
        lambda document_id: (_ for _ in ()).throw(ConnectionError(raw_qdrant_error)),
    )

    with pytest.raises(RuntimeError) as raised:
        provider.delete_document(document_id="doc-1")

    assert str(raised.value) == (
        "Qdrant deletion failed for document 'doc-1'; source storage was not deleted."
    )
    assert "secret-token" not in str(raised.value)
    assert raised.value.__cause__ is not None
    assert source_store.deleted is False


def test_local_pdf_provider_does_not_delete_sources_when_qdrant_clear_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeSourceStore:
        deleted = False

        def delete_all_documents(self) -> int:
            self.deleted = True
            return 1

    source_store = FakeSourceStore()
    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        source_store=cast(Any, source_store),
    )
    raw_qdrant_error = "api_key=secret-token url=https://qdrant.example.test"
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.delete_all_qdrant_points",
        lambda: (_ for _ in ()).throw(ConnectionError(raw_qdrant_error)),
    )

    with pytest.raises(RuntimeError) as raised:
        provider.delete_all_documents()

    assert str(raised.value) == (
        "Qdrant deletion failed while clearing sources; source storage was not deleted."
    )
    assert "secret-token" not in str(raised.value)
    assert raised.value.__cause__ is not None
    assert source_store.deleted is False


def test_local_pdf_provider_retrieves_matching_chunks(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANK_PROVIDER", "score")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    _mock_openai_client(monkeypatch)
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_pdf_with_markdown",
        lambda path, **kwargs: LoadedPdfDocument(
            markdown="# Warranty\nPin VF8 duoc bao hanh 8 nam.",
            chunks=[
                Chunk(
                    chunk_id="pdf_doc_c0001",
                    text="Pin VF8 duoc bao hanh 8 nam.",
                    metadata={"chunk_index": 1},
                ),
                Chunk(
                    chunk_id="pdf_doc_c0002",
                    text="Lich bao duong lop xe.",
                    metadata={"chunk_index": 2},
                ),
            ],
        ),
    )

    def fake_dense_search(self: Store, query: str, top_k: int = 10) -> list[SearchResult]:
        return [
            SearchResult(
                chunk=self._chunks[0],
                score=0.95,
                rank=1,
                retriever="dense",
            )
        ][:top_k]

    monkeypatch.setattr(Store, "dense_search", fake_dense_search)
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    uploaded = provider.upload_document(
        filename="warranty.pdf",
        content=b"%PDF-1.4",
        content_type="application/pdf",
    )

    results = provider.retrieve(
        RetrievalInput(
            question="pin bao hanh bao lau",
            document_ids=[uploaded.document_id],
        )
    ).results

    assert len(results) >= 1
    assert results[0].chunk.chunk_id == "pdf_doc_c0001"
    assert results[0].retriever == "hybrid"
    assert results[0].rank == 1
    assert (
        results[0].chunk.metadata["retrieval_pipeline"] == "source_ingestion -> bm25 + dense -> rrf"
    )
    assert results[0].chunk.metadata["bm25"] is not None
    assert results[0].chunk.metadata["dense"] is not None
    assert results[0].chunk.metadata["dense_error"] is None
    assert results[0].chunk.metadata["rrf"] is not None
    pipeline_trace = cast(dict[str, Any], results[0].chunk.metadata["pipeline_trace"])
    assert pipeline_trace["preprocess_query"]["input"]["query"] == "pin bao hanh bao lau"
    assert isinstance(pipeline_trace["preprocess_query"]["latency_ms"], int)
    assert pipeline_trace["preprocess_query"]["output"]["normalized"] == "pin bao hanh bao lau"
    assert pipeline_trace["bm25_search"]["input"]["query"] == "pin bao hanh bao lau"
    assert pipeline_trace["bm25_search"]["output"][0]["retriever"] == "bm25"
    assert pipeline_trace["dense_search"]["tech"]["model"] == "text-embedding-3-small"
    assert pipeline_trace["dense_search"]["output"]["results"][0]["retriever"] == "dense"
    assert pipeline_trace["rrf_fusion"]["tech"]["method"] == "reciprocal_rank_fusion"
    assert pipeline_trace["rrf_fusion"]["tech"]["rrf_k"] == 60
    assert pipeline_trace["rrf_fusion"]["input"]["bm25_results"][0]["retriever"] == "bm25"
    assert pipeline_trace["rrf_fusion"]["output"][0]["retriever"] == "hybrid"
    rrf_contributions = pipeline_trace["rrf_fusion"]["output"][0]["contributions"]
    assert rrf_contributions["bm25"]["retriever"] == "bm25"
    assert rrf_contributions["dense"]["retriever"] == "dense"
    assert rrf_contributions["total_rrf_score"] > 0
    assert pipeline_trace["thresholds"]["pre_fusion"]["bm25_original_count"] >= 1
    assert isinstance(pipeline_trace["thresholds"]["pre_fusion"]["thresholds_applied"], bool)
    assert pipeline_trace["thresholds"]["fusion"]["fusion_min_score"] is None
    assert results[0].chunk.metadata["rrf_contributions"]["total_rrf_score"] > 0
    assert pipeline_trace["rerank"]["tech"]["provider"] == "skipped"
    assert pipeline_trace["rerank"]["tech"]["reason"] == "agent_reranks"
    assert pipeline_trace["rerank"]["input"]["candidates"][0]["retriever"] == "hybrid"
    assert pipeline_trace["rerank"]["output"][0]["retriever"] == "hybrid"


def test_local_pdf_provider_uses_qdrant_retrieval_without_loading_source_chunks(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeCloudSourceStore:
        def read_all_chunks(self) -> list[Chunk]:
            raise AssertionError("cloud retrieval should not rebuild BM25 from stored chunks")

        def read_chunks_for_documents(self, document_ids: list[str]) -> list[Chunk]:
            raise AssertionError("cloud retrieval should not load selected chunks from S3")

    expected = [
        SearchResult(
            chunk=Chunk(
                chunk_id="c1",
                text="Pin VF8 duoc bao hanh",
                metadata={"document_id": "doc-1"},
            ),
            score=0.91,
            rank=1,
            retriever="hybrid",
        )
    ]
    seen: dict[str, object] = {}

    def fake_qdrant_hybrid_search(
        question: str,
        *,
        document_ids: list[str] | None = None,
        top_k: int = 10,
    ) -> list[SearchResult]:
        seen["question"] = question
        seen["document_ids"] = document_ids
        seen["top_k"] = top_k
        return expected

    monkeypatch.setenv("VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_STORE_URL", "https://qdrant.example.test")
    monkeypatch.setenv("LOCAL_PDF_RETRIEVAL_TOP_K", "3")
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.qdrant_hybrid_search",
        fake_qdrant_hybrid_search,
    )
    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        source_store=cast(Any, FakeCloudSourceStore()),
    )

    results = provider.retrieve(RetrievalInput(question="pin vf8", document_ids=["doc-1"])).results

    assert results == expected
    assert seen == {"question": "pin vf8", "document_ids": ["doc-1"], "top_k": 3}


def test_local_pdf_provider_reads_raw_source_from_cloud_store(tmp_path: Path) -> None:
    class FakeCloudSourceStore:
        def read_raw(self, document_id: str) -> StoredRawSource:
            return StoredRawSource(
                content=b"%PDF-1.4",
                content_type="application/pdf",
                name=f"{document_id}.pdf",
            )

    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        source_store=cast(Any, FakeCloudSourceStore()),
    )

    raw = provider.document_raw_content(document_id="doc-1")

    assert raw.content == b"%PDF-1.4"
    assert raw.content_type == "application/pdf"


def test_local_pdf_provider_rejects_non_pdf_upload(tmp_path: Path) -> None:
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    try:
        provider.upload_document(
            filename="notes.txt",
            content=b"hello",
            content_type="text/plain",
        )
    except ValueError as exc:
        assert "only supports PDF" in str(exc)
    else:
        raise AssertionError("Expected non-PDF upload to be rejected.")
