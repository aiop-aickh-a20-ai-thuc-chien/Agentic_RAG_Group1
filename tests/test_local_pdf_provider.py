import json
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
from agentic_rag.integrations.local_pdf.providers import (
    LocalPdfDocumentChunks,
    LocalPdfEvidenceProvider,
    LocalPdfUploadedDocument,
)
from agentic_rag.integrations.local_pdf.storage import StoredRawSource, StoredSourceDocument
from agentic_rag.retrieval.search import Store


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
    monkeypatch.setenv("RAG_TRACE_FULL_CONTENT", "false")
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


def test_local_pdf_provider_annotates_quality_against_existing_chunks(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    def fake_load_text_chunks(text: str, **kwargs: str) -> list[Chunk]:
        source_stem = kwargs["source"].removesuffix(".txt").lower()
        return [
            Chunk(
                chunk_id=f"text_{source_stem}_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ]

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        fake_load_text_chunks,
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)

    base = provider.upload_text(title="Base", text="VF8 duoc bao hanh 8 nam.")
    update = provider.upload_text(title="Update", text="VF8 duoc bao hanh 6 nam.")

    base_chunks = provider.document_chunks(document_id=base.document_id).chunks
    update_chunks = provider.document_chunks(document_id=update.document_id).chunks
    assert "knowledge_quality" in update_chunks[0].metadata
    assert update_chunks[0].metadata["knowledge_quality"]["conflict_count"] == 1
    assert update_chunks[0].metadata["knowledge_quality"]["fact_count"] == 1
    assert base_chunks[0].metadata["knowledge_quality"]["conflict_count"] == 0


def test_local_pdf_provider_reports_quality_for_selected_source(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    def fake_load_text_chunks(text: str, **kwargs: str) -> list[Chunk]:
        source_stem = kwargs["source"].removesuffix(".txt").lower()
        return [
            Chunk(
                chunk_id=f"text_{source_stem}_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ]

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        fake_load_text_chunks,
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    base = provider.upload_text(title="Base", text="VF8 duoc bao hanh 8 nam.")
    update = provider.upload_text(title="Update", text="VF8 duoc bao hanh 6 nam.")

    report = provider.knowledge_quality_report(document_ids=[base.document_id])

    assert report.metadata["selected_document_ids"] == [base.document_id]
    assert report.metadata["method"] == "deterministic_v1"
    assert len(report.findings) == 1
    assert report.findings[0].kind == "conflict"
    assert set(report.findings[0].chunk_ids) == {
        f"{base.document_id}_c0001",
        f"{update.document_id}_c0001",
    }
    assert {fact.normalized_value for fact in report.facts} == {72.0, 96.0}


def test_local_pdf_provider_rescans_and_persists_quality_metadata(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    def fake_load_text_chunks(text: str, **kwargs: str) -> list[Chunk]:
        source_stem = kwargs["source"].removesuffix(".txt").lower()
        return [
            Chunk(
                chunk_id=f"text_{source_stem}_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ]

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        fake_load_text_chunks,
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    base = provider.upload_text(title="Base", text="VF8 duoc bao hanh 8 nam.")
    update = provider.upload_text(title="Update", text="VF8 duoc bao hanh 6 nam.")

    report = provider.rescan_knowledge_quality()

    assert len(report.findings) == 1
    for document_id in (base.document_id, update.document_id):
        chunk = provider.document_chunks(document_id=document_id).chunks[0]
        assert chunk.metadata["knowledge_quality"]["conflict_count"] == 1
        assert chunk.metadata["knowledge_quality"]["finding_ids"]


def test_local_pdf_provider_rejects_disabled_model_backed_method(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id=f"text_{kwargs['source'].removesuffix('.txt').lower()}_c0001",
                text=text,
                metadata={"source": kwargs["source"]},
            )
        ],
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    provider.upload_text(
        title="Causal",
        text="VF 8 failures are caused by fast charging.",
    )
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.get_explicit_llm_client",
        lambda role: None,
    )

    with pytest.raises(ValueError, match="INGESTION_LLM"):
        provider.knowledge_quality_report(methods=["semantic_verifier"])


def test_local_pdf_provider_requires_explicit_ingestion_model_profile(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    from agentic_rag.model_runtime.factory import clear_model_runtime_caches

    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "global-paid-model")
    monkeypatch.delenv("INGESTION_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("INGESTION_LLM_MODEL", raising=False)
    monkeypatch.setattr(
        "agentic_rag.model_runtime.config.load_local_env",
        lambda: None,
    )
    clear_model_runtime_caches()

    with pytest.raises(ValueError, match="INGESTION_LLM"):
        provider.knowledge_quality_report(methods=["semantic_verifier"])


def test_local_pdf_provider_model_failure_does_not_persist_partial_annotations(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    from agentic_rag.core.contracts import LLMCompletionOutput
    from agentic_rag.ingestion.knowledge_quality import KnowledgeQualityInvocationError

    class InvalidClient:
        def complete(self, request: object) -> LLMCompletionOutput:
            return LLMCompletionOutput(
                text="not-json",
                provider="test",
                model="small",
            )

        def stream(self, request: object) -> object:
            raise AssertionError

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        lambda text, **kwargs: [
            Chunk(
                chunk_id=f"text_{kwargs['source'].removesuffix('.txt').lower()}_c0001",
                text=text,
                metadata={"source": kwargs["source"]},
            )
        ],
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    provider.upload_text(
        title="Causal A",
        text="VF 8 battery failures are caused by frequent fast charging.",
    )
    provider.upload_text(
        title="Causal B",
        text="VF 8 battery failures are not caused by frequent fast charging.",
    )
    monkeypatch.setenv("INGESTION_LLM_PROVIDER", "openai")
    monkeypatch.setenv("INGESTION_LLM_MODEL", "small")
    persisted = False

    def record_persist(chunks: list[Chunk]) -> None:
        nonlocal persisted
        persisted = True

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.get_explicit_llm_client",
        lambda role: InvalidClient(),
    )
    monkeypatch.setattr(provider, "_persist_quality_annotations", record_persist)

    with pytest.raises(KnowledgeQualityInvocationError):
        provider.rescan_knowledge_quality(methods=["semantic_verifier"])

    assert persisted is False


def test_local_pdf_provider_rolls_back_multi_document_persistence_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    def fake_load_text_chunks(text: str, **kwargs: str) -> list[Chunk]:
        source_stem = kwargs["source"].removesuffix(".txt").lower()
        return [
            Chunk(
                chunk_id=f"text_{source_stem}_c0001",
                text=text,
                metadata={"source": kwargs["source"], "source_type": "text"},
            )
        ]

    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.load_text_chunks",
        fake_load_text_chunks,
    )
    provider = LocalPdfEvidenceProvider(store_dir=tmp_path)
    base = provider.upload_text(title="Base", text="VF8 duoc bao hanh 8 nam.")
    update = provider.upload_text(title="Update", text="VF8 duoc bao hanh 6 nam.")
    original_payloads = {
        document_id: provider._chunk_path(document_id).read_bytes()
        for document_id in (base.document_id, update.document_id)
    }
    original_write = provider._write_chunks
    calls = 0

    def fail_second_write(*, document_id: str, chunks: list[Chunk]) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated persistence failure")
        original_write(document_id=document_id, chunks=chunks)

    monkeypatch.setattr(provider, "_write_chunks", fail_second_write)

    with pytest.raises(OSError, match="simulated persistence failure"):
        provider.rescan_knowledge_quality()

    assert {
        document_id: provider._chunk_path(document_id).read_bytes()
        for document_id in (base.document_id, update.document_id)
    } == original_payloads


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
        lambda chunks: {"enabled": False, "vector_store": "turbovec"},
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
        lambda chunks: {"enabled": False, "vector_store": "turbovec"},
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
        lambda chunks: (_ for _ in ()).throw(ConnectionError("local endpoint unavailable")),
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
        "error": "local endpoint unavailable",
        "requested_provider": "auto",
        "resolved_provider": "local",
        "fallback_reason": "openai_api_key_missing",
        "model": "local-model",
        "latency_ms": trace["index_write"]["dense_index"]["latency_ms"],
    }


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

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
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
        lambda chunks: (_ for _ in ()).throw(ConnectionError("qdrant unavailable")),
    )
    source_store = FakeSourceStore()
    provider = LocalPdfEvidenceProvider(
        store_dir=tmp_path,
        source_store=cast(Any, source_store),
    )

    with pytest.raises(RuntimeError, match="source storage was rolled back"):
        provider.upload_text(title="Ghi chu", text="Noi dung tu nguoi dung")

    assert source_store.documents == {}
    assert len(source_store.deleted) == 1


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
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.delete_qdrant_document_points",
        lambda document_id: (_ for _ in ()).throw(ConnectionError("qdrant unavailable")),
    )

    with pytest.raises(RuntimeError, match=r"Qdrant.*source storage was not deleted"):
        provider.delete_document(document_id="doc-1")

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
    monkeypatch.setattr(
        "agentic_rag.integrations.local_pdf.providers.delete_all_qdrant_points",
        lambda: (_ for _ in ()).throw(ConnectionError("qdrant unavailable")),
    )

    with pytest.raises(RuntimeError, match=r"Qdrant.*source storage was not deleted"):
        provider.delete_all_documents()

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

    monkeypatch.setenv("DENSE_VECTOR_STORE", "qdrant")
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
