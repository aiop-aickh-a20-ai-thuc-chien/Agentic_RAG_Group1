"""Local source ingestion and retrieval provider.

This provider lets the API run the same Module 5 generation/citation flow
without RAGFlow for PDF, URL, and text documents. It is intentionally
lightweight: source-specific ingestion modules produce shared chunks, chunks are
stored as JSONL, and retrieval is hybrid. Dense retrieval is traced when OpenAI
embeddings are configured, and the provider falls back to BM25-only fusion when
embeddings are unavailable.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
import unicodedata
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import (
    Chunk,
    RetrievalInput,
    RetrievalOutput,
    SearchResult,
    SourceDocumentChunks,
    SourceDocumentUpload,
)
from agentic_rag.ingestion.chunking.splitters import short_hash
from agentic_rag.ingestion.pdf import load_pdf_with_markdown
from agentic_rag.ingestion.pdf.config import PdfIngestionConfig
from agentic_rag.ingestion.url import load_text_chunks, load_url_with_artifacts
from agentic_rag.integrations.local_pdf.storage import (
    LocalSourceStore,
    PostgresLocalSourceStore,
    S3LocalSourceStore,
    StoredRawSource,
    StoredSourceDocument,
)
from agentic_rag.retrieval.fusion import (
    RRF_K,
    ThresholdConfig,
    apply_fusion_threshold,
    apply_pre_fusion_thresholds,
    normalized_score_fusion,
    rrf_fusion,
    weighted_rrf_fusion,
)
from agentic_rag.retrieval.search import (
    Store,
    delete_all_qdrant_points,
    delete_qdrant_document_points,
    dense_embedding_metadata,
    qdrant_hybrid_search,
    upsert_dense_embeddings,
)


def _noop_traceable(*, name: str = "", run_type: str = "chain", **_: object) -> Any:
    def _noop(func: Any) -> Any:
        return func

    return _noop


try:
    from langsmith import traceable as _ls_traceable
except ImportError:
    _ls_traceable = _noop_traceable  # type: ignore[assignment]


@_ls_traceable(name="query-normalize", run_type="tool")
def _traced_preprocess(store: Store, question: str) -> dict[str, Any]:
    return store.preprocess_query(question)


@_ls_traceable(name="bm25-search", run_type="retriever")
def _traced_bm25(store: Store, query: str, top_k: int) -> list[SearchResult]:
    return store.bm25_search(query, top_k=top_k)


@_ls_traceable(name="dense-search", run_type="retriever")
def _traced_dense(
    store: Store,
    query: str,
    top_k: int,
) -> tuple[list[SearchResult], str | None]:
    return _dense_search_safely(store, query, top_k=top_k)


@_ls_traceable(name="pre-fusion-threshold", run_type="tool")
def _traced_pre_fusion_threshold(
    bm25_results: list[SearchResult],
    dense_results: list[SearchResult],
    config: ThresholdConfig,
) -> tuple[list[SearchResult], list[SearchResult], dict[str, object]]:
    return apply_pre_fusion_thresholds(
        bm25_results=bm25_results,
        dense_results=dense_results,
        config=config,
    )


@_ls_traceable(name="post-fusion-threshold", run_type="tool")
def _traced_post_fusion_threshold(
    fused_results: list[SearchResult],
    config: ThresholdConfig,
) -> tuple[list[SearchResult], dict[str, object]]:
    return apply_fusion_threshold(fused_results, config=config)


class _LocalPdfProviderModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LocalPdfUploadedDocument(SourceDocumentUpload):
    """Normalized upload result returned to the UI/API layer."""

    trace: dict[str, object]


class LocalPdfDocumentChunks(SourceDocumentChunks):
    """One page of local PDF chunks plus the full chunk count."""


class LocalPdfDocumentDebug(_LocalPdfProviderModel):
    """Debug view of one locally ingested source."""

    document_id: str
    name: str
    source_type: str
    source: str
    markdown: str
    chunk_input: str
    chunk_input_type: str
    chunks: list[Chunk]
    total_chunks: int
    metadata: dict[str, object]


class LocalPdfStoredDocument(_LocalPdfProviderModel):
    """Stored local source document plus chunks for UI hydration."""

    document_id: str
    dataset_id: str
    name: str
    provider: str
    source_type: str
    source: str
    total_chunks: int
    chunks: list[Chunk]
    metadata: dict[str, object]


class LocalPdfEvidenceProvider:
    """Use internal PDF ingestion plus retrieval/fusion/rerank modules."""

    dataset_id = "local_pdf"

    def __init__(
        self,
        *,
        store_dir: Path,
        pdf_config: PdfIngestionConfig | None = None,
        source_store: LocalSourceStore | None = None,
    ) -> None:
        self._store_dir = store_dir
        self._pdf_config = pdf_config or PdfIngestionConfig()
        self._source_store = source_store
        self._files_dir = store_dir / "files"
        self._chunks_dir = store_dir / "chunks"
        self._parsed_dir = store_dir / "parsed"
        self._debug_dir = store_dir / "debug"
        self._artifacts_dir = store_dir / "artifacts"
        if self._source_store is None:
            self._files_dir.mkdir(parents=True, exist_ok=True)
            self._chunks_dir.mkdir(parents=True, exist_ok=True)
            self._parsed_dir.mkdir(parents=True, exist_ok=True)
            self._debug_dir.mkdir(parents=True, exist_ok=True)
            self._artifacts_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> LocalPdfEvidenceProvider:
        """Create a local PDF provider from environment variables."""

        store_dir = Path(os.getenv("LOCAL_PDF_STORE_DIR", "storage/local_pdf"))
        return cls(
            store_dir=store_dir,
            pdf_config=PdfIngestionConfig.from_env(),
            source_store=_source_store_from_env(),
        )

    def upload_document(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        start_parse: bool = True,
    ) -> LocalPdfUploadedDocument:
        """Persist, parse, chunk, and index one PDF document locally."""

        started_at = time.perf_counter()
        _validate_pdf_upload(filename=filename, content_type=content_type)
        run_id = f"pdf_{uuid.uuid4().hex[:8]}"  # temporary id for the local working file
        safe_filename = _safe_filename(filename)
        pdf_path = self._raw_pdf_path(run_id)
        pdf_path.write_bytes(content)

        parse_started_at = time.perf_counter()
        parsed_markdown = ""
        pipeline_name = self._pdf_config.pipeline_name
        strategy_name = self._pdf_config.strategy_name
        parser_name = self._pdf_config.parser_name
        chunker_name = self._pdf_config.chunker_name
        requested_chunker_name = chunker_name
        chunking_fallback_reason = None
        if start_parse:
            try:
                parsed_pdf = load_pdf_with_markdown(
                    str(pdf_path),
                    pipeline_name=pipeline_name,
                    strategy_name=strategy_name,
                    chunker_name=chunker_name,
                )
            except Exception:
                self._delete_temporary_path(pdf_path)
                raise
            parsed_markdown = parsed_pdf.markdown
            chunks = parsed_pdf.chunks
            parser_name = parsed_pdf.parser
            pipeline_name = parsed_pdf.pipeline
            strategy_name = parsed_pdf.strategy
            chunker_name = parsed_pdf.chunker
            requested_chunker_name = parsed_pdf.requested_chunker or chunker_name
            chunking_fallback_reason = parsed_pdf.chunking_fallback_reason
        else:
            chunks = []
        parse_latency_ms = _latency_ms(parse_started_at)
        # Deterministic document_id = chunk prefix so re-uploads overwrite (idempotent).
        document_id = _document_id_from_chunks(chunks, fallback=f"pdf_{short_hash(safe_filename)}")
        if self._source_store is None:
            final_pdf_path = self._files_dir / f"{_safe_document_id(document_id)}.pdf"
            if pdf_path != final_pdf_path:
                pdf_path.replace(final_pdf_path)
                pdf_path = final_pdf_path
        markdown_path = self._write_markdown(
            document_id=document_id,
            markdown=parsed_markdown,
        )
        chunk_started_at = time.perf_counter()
        chunks = _chunks_with_local_metadata(
            chunks=chunks,
            document_id=document_id,
            name=safe_filename,
            source_type="pdf",
        )
        chunk_latency_ms = _latency_ms(chunk_started_at)
        write_started_at = time.perf_counter()
        if self._source_store is None:
            self._write_chunks(document_id=document_id, chunks=chunks)
        try:
            source_store_trace, dense_index_trace = self._write_indexes(
                document_id=document_id,
                name=safe_filename,
                source_type="pdf",
                source=safe_filename,
                raw_path=pdf_path,
                markdown_path=markdown_path,
                metadata={
                    "parser": parser_name,
                    "chunker": chunker_name,
                    "requested_chunker": requested_chunker_name,
                    "fallback_reason": chunking_fallback_reason,
                },
                chunks=chunks,
            )
        finally:
            self._delete_temporary_path(pdf_path)
            self._delete_temporary_path(markdown_path)
        write_latency_ms = _latency_ms(write_started_at)
        return LocalPdfUploadedDocument(
            document_id=document_id,
            name=safe_filename,
            dataset_id=self.dataset_id,
            parse_started=start_parse,
            trace={
                "source_upload": {
                    "provider": self.dataset_id,
                    "document_id": document_id,
                    "filename": safe_filename,
                    "content_type": content_type,
                    "size_bytes": len(content),
                    "stored_path": str(pdf_path) if self._source_store is None else None,
                },
                "parse": {
                    "parser": parser_name,
                    "pipeline": pipeline_name,
                    "strategy": strategy_name,
                    "started": start_parse,
                    "markdown_path": (
                        str(markdown_path)
                        if markdown_path is not None and self._source_store is None
                        else None
                    ),
                    "markdown_chars": len(parsed_markdown),
                    "markdown_preview": _preview(parsed_markdown, _trace_preview_chars()),
                    **_full_trace_content("markdown", parsed_markdown),
                    "latency_ms": parse_latency_ms,
                },
                "chunking": {
                    "chunk_count": len(chunks),
                    "chunk_ids": [chunk.chunk_id for chunk in chunks],
                    "chunker": chunker_name,
                    "requested_chunker": requested_chunker_name,
                    "fallback_reason": chunking_fallback_reason,
                    "chunks": [_trace_chunk(chunk) for chunk in chunks],
                    "latency_ms": chunk_latency_ms,
                },
                "index_write": {
                    "type": "jsonl" if self._source_store is None else "source_store",
                    "path": str(self._chunk_path(document_id))
                    if self._source_store is None
                    else None,
                    "source_store": source_store_trace,
                    "dense_index": dense_index_trace,
                    "latency_ms": write_latency_ms,
                },
                "total_latency_ms": _latency_ms(started_at),
            },
        )

    def upload_url(self, *, url: str) -> LocalPdfUploadedDocument:
        """Fetch, parse, chunk, and index one URL through the URL ingestion module."""

        started_at = time.perf_counter()
        run_id = f"url_{uuid.uuid4().hex[:8]}"  # temporary id for debug artifact naming
        safe_name = _safe_url_filename(url)

        ingest_started_at = time.perf_counter()
        debug_artifact_dir = None if self._source_store is not None else self._debug_dir / run_id
        data_artifact_dir = None if self._source_store is not None else self._artifacts_dir
        loaded_url = load_url_with_artifacts(
            url,
            debug_artifact_dir=debug_artifact_dir,
            data_artifact_dir=data_artifact_dir,
            run_id=run_id,
        )
        chunks = loaded_url.chunks
        if not chunks:
            _record_failed_url(url=url, reason="parsed URL produced no chunks")
            raise ValueError(f"URL parsed but produced no chunks: {url}")
        # Deterministic document_id = chunk prefix (url_<short_hash(final_url)>) so the
        # store key matches chunk_ids and re-uploads overwrite instead of duplicating.
        document_id = _document_id_from_chunks(chunks, fallback=f"url_{short_hash(url)}")
        ingest_latency_ms = _latency_ms(ingest_started_at)
        markdown_path = (
            loaded_url.artifacts.markdown_path if loaded_url.artifacts is not None else None
        )
        local_markdown_path = self._write_markdown(
            document_id=document_id,
            markdown=loaded_url.markdown,
        )

        chunk_started_at = time.perf_counter()
        chunks = _chunks_with_local_metadata(
            chunks=chunks,
            document_id=document_id,
            name=safe_name,
            source_type="url",
            source=url,
        )
        url_trace = _url_ingestion_trace(requested_url=url, chunks=chunks)
        chunk_latency_ms = _latency_ms(chunk_started_at)
        write_started_at = time.perf_counter()
        if self._source_store is None:
            self._write_chunks(document_id=document_id, chunks=chunks)
        try:
            source_store_trace, dense_index_trace = self._write_indexes(
                document_id=document_id,
                name=safe_name,
                source_type="url",
                source=url,
                raw_path=None,
                markdown_path=local_markdown_path,
                metadata={
                    "requested_url": url,
                    "final_url": url_trace["final_url"],
                    "title": url_trace["title"],
                },
                chunks=chunks,
            )
        finally:
            self._delete_temporary_path(local_markdown_path)
        write_latency_ms = _latency_ms(write_started_at)

        return LocalPdfUploadedDocument(
            document_id=document_id,
            name=safe_name,
            dataset_id=self.dataset_id,
            parse_started=True,
            trace={
                "source_upload": {
                    "provider": self.dataset_id,
                    "document_id": document_id,
                    "filename": safe_name,
                    "source": url,
                    "source_type": "url",
                    "requested_url": url,
                    "final_url": url_trace["final_url"],
                },
                "parse": {
                    "parser": "url.load_url_with_artifacts",
                    "started": True,
                    "source_type": "url",
                    "requested_url": url,
                    "final_url": url_trace["final_url"],
                    "title": url_trace["title"],
                    "section_count": url_trace["section_count"],
                    "sections": url_trace["sections"],
                    "markdown_path": (
                        str(local_markdown_path or markdown_path)
                        if (local_markdown_path or markdown_path) is not None
                        and self._source_store is None
                        else None
                    ),
                    "artifact_markdown_path": str(markdown_path)
                    if markdown_path is not None and self._source_store is None
                    else None,
                    "markdown_chars": len(loaded_url.markdown),
                    "markdown_preview": _preview(loaded_url.markdown, _trace_preview_chars()),
                    **_full_trace_content("markdown", loaded_url.markdown),
                    "latency_ms": ingest_latency_ms,
                },
                "chunking": {
                    "chunk_count": len(chunks),
                    "chunk_ids": [chunk.chunk_id for chunk in chunks],
                    "chunking_methods": url_trace["chunking_methods"],
                    "chunking_providers": url_trace["chunking_providers"],
                    "chunking_models": url_trace["chunking_models"],
                    "chunks": [_trace_chunk(chunk) for chunk in chunks],
                    "latency_ms": chunk_latency_ms,
                },
                "index_write": {
                    "type": "jsonl" if self._source_store is None else "source_store",
                    "path": str(self._chunk_path(document_id))
                    if self._source_store is None
                    else None,
                    "source_store": source_store_trace,
                    "dense_index": dense_index_trace,
                    "latency_ms": write_latency_ms,
                },
                "total_latency_ms": _latency_ms(started_at),
            },
        )

    def upload_text(self, *, title: str, text: str) -> LocalPdfUploadedDocument:
        """Chunk and index user-provided text through the URL/text ingestion module."""

        started_at = time.perf_counter()
        run_id = f"text_{uuid.uuid4().hex[:8]}"  # temporary id for debug artifact naming
        safe_name = _safe_text_filename(title)

        ingest_started_at = time.perf_counter()
        chunks = load_text_chunks(
            text,
            source=safe_name,
            debug_artifact_dir=None if self._source_store is not None else self._debug_dir / run_id,
            data_artifact_dir=None if self._source_store is not None else self._artifacts_dir,
            run_id=run_id,
        )
        # Deterministic document_id = chunk prefix so re-uploads overwrite (idempotent).
        document_id = _document_id_from_chunks(chunks, fallback=f"text_{short_hash(safe_name)}")
        markdown_path = self._write_markdown(document_id=document_id, markdown=text)
        ingest_latency_ms = _latency_ms(ingest_started_at)

        chunk_started_at = time.perf_counter()
        chunks = _chunks_with_local_metadata(
            chunks=chunks,
            document_id=document_id,
            name=safe_name,
            source_type="text",
        )
        chunk_latency_ms = _latency_ms(chunk_started_at)
        write_started_at = time.perf_counter()
        if self._source_store is None:
            self._write_chunks(document_id=document_id, chunks=chunks)
        try:
            source_store_trace, dense_index_trace = self._write_indexes(
                document_id=document_id,
                name=safe_name,
                source_type="text",
                source=safe_name,
                raw_path=None,
                markdown_path=markdown_path,
                metadata={"title": title},
                chunks=chunks,
            )
        finally:
            self._delete_temporary_path(markdown_path)
        write_latency_ms = _latency_ms(write_started_at)

        return LocalPdfUploadedDocument(
            document_id=document_id,
            name=safe_name,
            dataset_id=self.dataset_id,
            parse_started=True,
            trace={
                "source_upload": {
                    "provider": self.dataset_id,
                    "document_id": document_id,
                    "filename": safe_name,
                    "source": safe_name,
                    "source_type": "text",
                    "size_chars": len(text),
                },
                "parse": {
                    "parser": "url.load_text_chunks",
                    "started": True,
                    "markdown_path": (
                        str(markdown_path)
                        if markdown_path is not None and self._source_store is None
                        else None
                    ),
                    "markdown_chars": len(text),
                    "markdown_preview": _preview(text, _trace_preview_chars()),
                    "latency_ms": ingest_latency_ms,
                },
                "chunking": {
                    "chunk_count": len(chunks),
                    "chunk_ids": [chunk.chunk_id for chunk in chunks],
                    "chunks": [_trace_chunk(chunk) for chunk in chunks],
                    "latency_ms": chunk_latency_ms,
                },
                "index_write": {
                    "type": "jsonl" if self._source_store is None else "source_store",
                    "path": str(self._chunk_path(document_id))
                    if self._source_store is None
                    else None,
                    "source_store": source_store_trace,
                    "dense_index": dense_index_trace,
                    "latency_ms": write_latency_ms,
                },
                "total_latency_ms": _latency_ms(started_at),
            },
        )

    def document_chunks(
        self,
        *,
        document_id: str,
        page: int = 1,
        page_size: int | None = None,
        keywords: str | None = None,
    ) -> LocalPdfDocumentChunks:
        """Return stored chunks for one local PDF document."""

        chunks = self._read_chunks(document_id)
        if keywords:
            keyword_terms = set(_tokenize(keywords))
            chunks = [
                chunk for chunk in chunks if keyword_terms.intersection(set(_tokenize(chunk.text)))
            ]

        total_chunks = len(chunks)
        if page_size is not None:
            start = max(page - 1, 0) * page_size
            chunks = chunks[start : start + page_size]

        return LocalPdfDocumentChunks(chunks=chunks, total_chunks=total_chunks)

    def list_documents(self, *, include_chunks: bool = True) -> list[LocalPdfStoredDocument]:
        """Return stored documents for frontend hydration."""

        if self._source_store is not None:
            return [
                self._stored_document_from_source_store(item, include_chunks=include_chunks)
                for item in self._source_store.list_documents()
            ]

        documents: list[LocalPdfStoredDocument] = []
        for chunk_path in sorted(
            self._chunks_dir.glob("*.jsonl"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        ):
            chunks = self._read_chunks(chunk_path.stem)
            if chunks:
                documents.append(self._stored_document_from_chunks(chunk_path.stem, chunks))
        return documents

    def delete_all_documents(self) -> int:
        """Delete all source documents, chunks, files and vectors."""
        import shutil

        count = 0
        _delete_all_dense_embeddings()
        if self._source_store is not None:
            count = self._source_store.delete_all_documents()

        for path in list(self._chunks_dir.glob("*.jsonl")):
            path.unlink(missing_ok=True)
            count = max(count, 1)
        for path in list(self._parsed_dir.glob("*.md")):
            path.unlink(missing_ok=True)
        for path in list(self._files_dir.iterdir()):
            path.unlink(missing_ok=True)
        for path in list(self._debug_dir.iterdir()):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)

        return count

    def delete_document(self, *, document_id: str) -> None:
        """Delete one source document and all its chunks from store and disk."""
        import shutil

        _delete_dense_document(document_id)
        if self._source_store is not None:
            self._source_store.delete_document(document_id)

        safe_id = _safe_document_id(document_id)
        for path in (
            self._chunk_path(document_id),
            self._markdown_path(document_id),
            self._files_dir / f"{safe_id}.pdf",
            self._files_dir / f"{safe_id}.txt",
        ):
            path.unlink(missing_ok=True)

        debug_dir = self._debug_dir / safe_id
        if debug_dir.is_dir():
            shutil.rmtree(debug_dir, ignore_errors=True)

    def document_debug(self, *, document_id: str) -> LocalPdfDocumentDebug:
        """Return source metadata, parsed Markdown, and chunks for one local document."""

        chunks = self._read_chunks(document_id)
        if not chunks:
            raise ValueError(f"Document not found or has no chunks: {document_id}")

        first_chunk = chunks[0]
        metadata = dict(first_chunk.metadata)
        name = str(metadata.get("document_name") or metadata.get("file_name") or document_id)
        source_type = str(metadata.get("source_type") or "unknown")
        source = str(metadata.get("source") or metadata.get("url") or name)
        markdown_path = self._markdown_path(document_id)
        markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
        if not markdown and self._source_store is not None:
            read_markdown = getattr(self._source_store, "read_markdown", None)
            if callable(read_markdown):
                markdown = str(read_markdown(document_id))
        chunk_input, chunk_input_type = self._debug_chunk_input(
            document_id=document_id,
            source_type=source_type,
            markdown=markdown,
            chunks=chunks,
        )
        return LocalPdfDocumentDebug(
            document_id=document_id,
            name=name,
            source_type=source_type,
            source=source,
            markdown=markdown,
            chunk_input=chunk_input,
            chunk_input_type=chunk_input_type,
            chunks=chunks,
            total_chunks=len(chunks),
            metadata=metadata,
        )

    def _stored_document_from_source_store(
        self,
        stored: StoredSourceDocument,
        *,
        include_chunks: bool,
    ) -> LocalPdfStoredDocument:
        chunks = self._read_chunks(stored.document_id) if include_chunks else []
        return LocalPdfStoredDocument(
            document_id=stored.document_id,
            dataset_id=stored.dataset_id,
            name=stored.name,
            provider=self.dataset_id,
            source_type=stored.source_type,
            source=stored.source,
            total_chunks=stored.total_chunks,
            chunks=chunks,
            metadata=stored.metadata,
        )

    def _stored_document_from_chunks(
        self,
        document_id: str,
        chunks: list[Chunk],
    ) -> LocalPdfStoredDocument:
        first_chunk = chunks[0]
        metadata = dict(first_chunk.metadata)
        name = str(metadata.get("document_name") or metadata.get("file_name") or document_id)
        source_type = str(metadata.get("source_type") or "unknown")
        source = str(metadata.get("source") or metadata.get("url") or name)
        dataset_id = str(metadata.get("dataset_id") or self.dataset_id)
        provider = str(metadata.get("provider") or self.dataset_id)
        return LocalPdfStoredDocument(
            document_id=document_id,
            dataset_id=dataset_id,
            name=name,
            provider=provider,
            source_type=source_type,
            source=source,
            total_chunks=len(chunks),
            chunks=chunks,
            metadata=metadata,
        )

    def document_raw_path(self, *, document_id: str) -> Path:
        """Return the locally stored raw PDF path for one document."""

        safe_document_id = _safe_document_id(document_id)
        raw_path = self._files_dir / f"{safe_document_id}.pdf"
        if not raw_path.exists():
            raise ValueError(f"Raw source file is not available: {document_id}")
        return raw_path

    def document_raw_content(self, *, document_id: str) -> StoredRawSource:
        """Return cloud-backed raw source content when the source store supports it."""

        if self._source_store is not None:
            read_raw = getattr(self._source_store, "read_raw", None)
            if callable(read_raw):
                raw = read_raw(document_id)
                if isinstance(raw, StoredRawSource):
                    return raw
        raise ValueError(f"Raw source file is not available: {document_id}")

    def retrieve(
        self,
        request: RetrievalInput,
    ) -> RetrievalOutput:
        """Run PDF chunks through BM25, dense retrieval, RRF, and rerank."""

        if _qdrant_vector_store_enabled():
            return RetrievalOutput(
                results=qdrant_hybrid_search(
                    request.question,
                    document_ids=request.document_ids,
                    top_k=request.page_size or _default_page_size(),
                )
            )

        chunks = self._chunks_for_documents(request.document_ids)
        if not chunks:
            return RetrievalOutput()

        store = Store(chunks)
        preprocess_started_at = time.perf_counter()
        preprocessed_query = _traced_preprocess(store, request.question)
        preprocess_latency_ms = _latency_ms(preprocess_started_at)
        normalized_query = preprocessed_query["normalized"]
        if not normalized_query:
            return RetrievalOutput()

        top_k = request.page_size or _default_page_size()
        candidate_k = max(_default_candidate_count(), top_k)
        bm25_started_at = time.perf_counter()
        bm25_results = _traced_bm25(store, normalized_query, candidate_k)
        bm25_latency_ms = _latency_ms(bm25_started_at)
        dense_started_at = time.perf_counter()
        # Dense uses original question (with diacritics) for better embedding quality
        dense_results, dense_error = _traced_dense(store, request.question, candidate_k)
        dense_latency_ms = _latency_ms(dense_started_at)
        threshold_config = _threshold_config_from_env()
        bm25_results, dense_results, pre_fusion_threshold_trace = _traced_pre_fusion_threshold(
            bm25_results, dense_results, threshold_config
        )
        fusion_started_at = time.perf_counter()
        fused_results, fusion_method_trace = _fuse_results(
            bm25_results=bm25_results,
            dense_results=dense_results,
            candidate_k=candidate_k,
        )
        fused_results, fusion_threshold_trace = _traced_post_fusion_threshold(
            fused_results, threshold_config
        )
        fusion_latency_ms = _latency_ms(fusion_started_at)
        # Rerank removed from provider — agent performs one final rerank with original question
        final_results = fused_results[:top_k]
        rerank_trace: dict[str, object] = {"provider": "skipped", "reason": "agent_reranks"}
        rerank_threshold_trace: dict[str, object] = {}
        rerank_latency_ms = 0
        return RetrievalOutput(
            results=_with_pipeline_metadata(
                results=final_results,
                question=request.question,
                chunks=chunks,
                top_k=top_k,
                candidate_k=candidate_k,
                preprocess_latency_ms=preprocess_latency_ms,
                bm25_latency_ms=bm25_latency_ms,
                dense_latency_ms=dense_latency_ms,
                fusion_latency_ms=fusion_latency_ms,
                rerank_latency_ms=rerank_latency_ms,
                pre_fusion_threshold_trace=pre_fusion_threshold_trace,
                fusion_method_trace=fusion_method_trace,
                fusion_threshold_trace=fusion_threshold_trace,
                rerank_threshold_trace=rerank_threshold_trace,
                rerank_trace=rerank_trace,
                preprocessed_query=preprocessed_query,
                bm25_results=bm25_results,
                dense_results=dense_results,
                fused_results=fused_results,
                dense_error=dense_error,
            )
        )

    def _write_chunks(self, *, document_id: str, chunks: list[Chunk]) -> None:
        chunk_path = self._chunk_path(document_id)
        payload = "\n".join(chunk.model_dump_json() for chunk in chunks)
        chunk_path.write_text(f"{payload}\n" if payload else "", encoding="utf-8")

    def _write_source_store(
        self,
        *,
        document_id: str,
        name: str,
        source_type: str,
        source: str,
        raw_path: Path | None,
        markdown_path: Path | None,
        metadata: dict[str, object],
        chunks: list[Chunk],
    ) -> dict[str, object]:
        if self._source_store is None:
            return {"type": "jsonl", "enabled": False}
        self._source_store.write_document(
            document_id=document_id,
            dataset_id=self.dataset_id,
            name=name,
            source_type=source_type,
            source=source,
            raw_path=raw_path,
            markdown_path=markdown_path,
            metadata=metadata,
            chunks=chunks,
        )
        return {
            "type": _source_store_trace_type(self._source_store),
            "enabled": True,
            "document_id": document_id,
            "chunk_count": len(chunks),
        }

    def _write_indexes(
        self,
        *,
        document_id: str,
        name: str,
        source_type: str,
        source: str,
        raw_path: Path | None,
        markdown_path: Path | None,
        metadata: dict[str, object],
        chunks: list[Chunk],
    ) -> tuple[dict[str, object], dict[str, object]]:
        source_store_trace = self._write_source_store(
            document_id=document_id,
            name=name,
            source_type=source_type,
            source=source,
            raw_path=raw_path,
            markdown_path=markdown_path,
            metadata=metadata,
            chunks=chunks,
        )
        try:
            dense_index_trace = _upsert_dense_embeddings_safely(chunks)
        except Exception as exc:
            if _qdrant_vector_store_enabled() and self._source_store is not None:
                try:
                    self._source_store.delete_document(document_id)
                except Exception as rollback_exc:
                    raise RuntimeError(
                        f"Qdrant upsert failed and source storage rollback failed: {rollback_exc}"
                    ) from exc
                raise RuntimeError(
                    f"Qdrant upsert failed; source storage was rolled back: {exc}"
                ) from exc
            raise
        return source_store_trace, dense_index_trace

    def _write_markdown(self, *, document_id: str, markdown: str) -> Path | None:
        if not markdown:
            return None

        markdown_path = (
            self._markdown_path(document_id)
            if self._source_store is None
            else self._temporary_markdown_path(document_id)
        )
        markdown_path.write_text(markdown, encoding="utf-8")
        return markdown_path

    def _temporary_markdown_path(self, document_id: str) -> Path:
        fd, markdown_name = tempfile.mkstemp(
            prefix=f"{_safe_document_id(document_id)}-",
            suffix=".md",
        )
        os.close(fd)
        return Path(markdown_name)

    def _raw_pdf_path(self, document_id: str) -> Path:
        if self._source_store is None:
            safe_document_id = _safe_document_id(document_id)
            return self._files_dir / f"{safe_document_id}.pdf"
        fd, raw_name = tempfile.mkstemp(
            prefix=f"{_safe_document_id(document_id)}-",
            suffix=".pdf",
        )
        os.close(fd)
        return Path(raw_name)

    def _delete_temporary_path(self, path: Path | None) -> None:
        if self._source_store is None or path is None:
            return
        with suppress(OSError):
            path.unlink(missing_ok=True)

    def _read_chunks(self, document_id: str) -> list[Chunk]:
        if self._source_store is not None:
            return self._source_store.read_chunks(document_id)

        chunk_path = self._chunk_path(document_id)
        if not chunk_path.exists():
            return []

        chunks: list[Chunk] = []
        for line in chunk_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                chunks.append(Chunk.model_validate_json(stripped))
        return chunks

    def _chunks_for_documents(self, document_ids: list[str] | None) -> list[Chunk]:
        if document_ids:
            if self._source_store is not None:
                stored = self._source_store.read_chunks_for_documents(document_ids)
                if stored:
                    return stored
            fallback: list[Chunk] = []
            for document_id in document_ids:
                fallback.extend(self._read_chunks(document_id))
            return fallback

        if self._source_store is not None:
            chunks = self._source_store.read_all_chunks()
            if chunks:
                return chunks

        all_chunks: list[Chunk] = []
        for chunk_path in sorted(self._chunks_dir.glob("*.jsonl")):
            all_chunks.extend(self._read_chunks(chunk_path.stem))
        return all_chunks

    def _chunk_path(self, document_id: str) -> Path:
        safe_document_id = _safe_document_id(document_id)
        return self._chunks_dir / f"{safe_document_id}.jsonl"

    def _markdown_path(self, document_id: str) -> Path:
        safe_document_id = _safe_document_id(document_id)
        return self._parsed_dir / f"{safe_document_id}.md"

    def _debug_chunk_input(
        self,
        *,
        document_id: str,
        source_type: str,
        markdown: str,
        chunks: list[Chunk],
    ) -> tuple[str, str]:
        normalized_source_type = source_type.lower()
        if normalized_source_type == "url":
            first_chunk = chunks[0] if chunks else None
            if first_chunk and "section_path" in first_chunk.metadata:
                from agentic_rag.ingestion.url.loader import _clean_markdown_noise

                cleaned = _clean_markdown_noise(markdown) if markdown else ""
                return cleaned or _chunks_as_text(chunks), "markdown_cleaned"
            parsed_sections_path = self._url_parsed_sections_path(document_id)
            if parsed_sections_path is not None:
                return parsed_sections_path.read_text(encoding="utf-8"), "parsed_sections"
            return _chunks_as_text(chunks), "parsed_sections"
        if normalized_source_type == "pdf":
            return markdown, "markdown"
        if normalized_source_type == "text":
            return markdown or _chunks_as_text(chunks), "text"
        return markdown or _chunks_as_text(chunks), "unknown"

    def _url_parsed_sections_path(self, document_id: str) -> Path | None:
        safe_document_id = _safe_document_id(document_id)
        debug_dir = self._debug_dir / safe_document_id
        if not debug_dir.exists():
            return None
        return next(iter(sorted(debug_dir.glob("*_parsed.txt"))), None)


def _validate_pdf_upload(*, filename: str, content_type: str | None) -> None:
    is_pdf_name = filename.lower().endswith(".pdf")
    is_pdf_content = content_type in {None, "", "application/pdf"}
    if not is_pdf_name or not is_pdf_content:
        raise ValueError("Local PDF provider only supports PDF uploads.")


def _chunk_with_local_metadata(
    *,
    chunk: Chunk,
    document_id: str,
    name: str,
    source_type: str,
    storage_chunk_id: str,
    source: str | None = None,
) -> Chunk:
    resolved_source = source or str(chunk.metadata.get("source") or name)
    metadata = {
        **chunk.metadata,
        "storage_chunk_id": storage_chunk_id,
        "document_id": document_id,
        "dataset_id": LocalPdfEvidenceProvider.dataset_id,
        "source": resolved_source,
        "document_name": name,
        "file_name": name,
        "source_type": source_type,
        "provider": "local_pdf",
    }
    if source_type == "url":
        metadata["url"] = source or chunk.metadata.get("url")
    return Chunk(chunk_id=chunk.chunk_id, text=chunk.text, metadata=metadata)


def _document_id_from_chunks(chunks: list[Chunk], *, fallback: str) -> str:
    """Derive a deterministic document_id from the chunk_id prefix.

    chunk_id = "{source_type}_{short_hash(source)}_{slug}_cNNN"; the first two
    underscore-separated parts ("url_<hash>") identify the source document and
    match how /eval-review doc-chunks groups chunks. Using this as the
    document_id makes the store key align with chunk_ids, so re-uploading the
    same source OVERWRITES instead of creating a duplicate. Falls back to a
    deterministic hash of the source when no chunk_id is present.
    """
    for chunk in chunks:
        cid = chunk.metadata.get("chunk_id") or chunk.chunk_id
        if cid:
            parts = str(cid).split("_")
            if len(parts) >= 2:
                return f"{parts[0]}_{parts[1]}"
    return fallback


def _chunks_with_local_metadata(
    *,
    chunks: list[Chunk],
    document_id: str,
    name: str,
    source_type: str,
    source: str | None = None,
) -> list[Chunk]:
    return [
        _chunk_with_local_metadata(
            chunk=chunk,
            document_id=document_id,
            name=name,
            source_type=source_type,
            source=source,
            storage_chunk_id=chunk.metadata.get("chunk_id") or f"{document_id}:{index:04d}",
        )
        for index, chunk in enumerate(chunks, start=1)
    ]


def _source_store_from_env() -> LocalSourceStore | None:
    raw_store = os.getenv("LOCAL_SOURCE_STORE", "jsonl").strip().lower()
    if raw_store == "s3":
        return S3LocalSourceStore.from_env()
    if raw_store not in {"postgres", "postgresql", "pg"}:
        return None

    connection = (
        os.getenv("LOCAL_SOURCE_POSTGRES_CONNECTION", "").strip()
        or os.getenv("DENSE_PGVECTOR_CONNECTION", "").strip()
    )
    if not connection:
        raise ValueError(
            "LOCAL_SOURCE_STORE=postgres requires LOCAL_SOURCE_POSTGRES_CONNECTION "
            "or DENSE_PGVECTOR_CONNECTION."
        )
    table_prefix = os.getenv("LOCAL_SOURCE_POSTGRES_TABLE_PREFIX", "local_rag").strip()
    return PostgresLocalSourceStore(connection=connection, table_prefix=table_prefix)


def _source_store_trace_type(source_store: LocalSourceStore) -> str:
    if isinstance(source_store, S3LocalSourceStore):
        return "s3"
    if isinstance(source_store, PostgresLocalSourceStore):
        return "postgres"
    return source_store.__class__.__name__


def _upsert_dense_embeddings_safely(chunks: list[Chunk]) -> dict[str, object]:
    started_at = time.perf_counter()
    if _qdrant_vector_store_enabled():
        trace = upsert_dense_embeddings(chunks)
        return {**trace, "latency_ms": _latency_ms(started_at)}

    embedding_metadata = dense_embedding_metadata()
    try:
        trace = upsert_dense_embeddings(chunks)
    except Exception as exc:
        return {
            "enabled": True,
            "status": "error",
            "error": str(exc),
            **embedding_metadata,
            "latency_ms": _latency_ms(started_at),
        }
    return {**trace, "latency_ms": _latency_ms(started_at)}


def _delete_dense_document(document_id: str) -> dict[str, object]:
    try:
        return delete_qdrant_document_points(document_id)
    except Exception as exc:
        raise RuntimeError(
            f"Qdrant deletion failed for document {document_id!r}; "
            f"source storage was not deleted: {exc}"
        ) from exc


def _delete_all_dense_embeddings() -> dict[str, object]:
    try:
        return delete_all_qdrant_points()
    except Exception as exc:
        raise RuntimeError(
            f"Qdrant deletion failed while clearing sources; source storage was not deleted: {exc}"
        ) from exc


def _qdrant_vector_store_enabled() -> bool:
    return os.getenv("DENSE_VECTOR_STORE", "turbovec").strip().lower() == "qdrant"


def local_pdf_backend_status() -> dict[str, str]:
    """Return non-secret local PDF storage/vector configuration for health checks."""

    raw_source_store = os.getenv("LOCAL_SOURCE_STORE", "jsonl").strip().lower()
    if raw_source_store == "s3":
        source_store = "s3"
    elif raw_source_store in {"postgres", "postgresql", "pg"}:
        source_store = "postgres"
    else:
        source_store = "jsonl"

    dense_vector_store = os.getenv("DENSE_VECTOR_STORE", "turbovec").strip().lower()
    payload = {
        "source_store": source_store,
        "dense_vector_store": dense_vector_store or "turbovec",
    }
    if source_store == "s3":
        payload["s3_bucket_configured"] = "true" if os.getenv("AWS_S3_BUCKET") else "false"
        payload["s3_prefix"] = os.getenv("AWS_S3_PREFIX", "").strip()
    if payload["dense_vector_store"] == "qdrant":
        payload["qdrant_url_configured"] = "true" if os.getenv("QDRANT_URL") else "false"
        payload["qdrant_collection"] = (
            os.getenv("QDRANT_COLLECTION", "agentic_rag_chunks").strip() or "agentic_rag_chunks"
        )
    return payload


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", _normalize_text(text))


def _normalize_text(text: str) -> str:
    lowered = text.lower().replace("\u0111", "d").replace("\u0110", "d")
    normalized = unicodedata.normalize("NFKD", lowered)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _metadata_int(metadata: dict[str, object], key: str) -> int | None:
    value = metadata.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _default_page_size() -> int:
    raw = os.getenv("LOCAL_PDF_RETRIEVAL_TOP_K", "5")
    try:
        return max(int(raw), 1)
    except ValueError:
        return 5


def _default_candidate_count() -> int:
    raw = os.getenv("LOCAL_PDF_RETRIEVAL_CANDIDATE_K", "20")
    try:
        return max(int(raw), 1)
    except ValueError:
        return 20


@_ls_traceable(name="rrf-fusion", run_type="tool")
def _fuse_results(
    *,
    bm25_results: list[SearchResult],
    dense_results: list[SearchResult],
    candidate_k: int,
) -> tuple[list[SearchResult], dict[str, object]]:
    method = os.getenv("FUSION_METHOD", "rrf").strip().lower()
    if method == "weighted_rrf":
        rrf_k = _env_int("FUSION_RRF_K", RRF_K)
        bm25_weight = _env_float("FUSION_BM25_WEIGHT", 0.55)
        dense_weight = _env_float("FUSION_DENSE_WEIGHT", 0.45)
        return weighted_rrf_fusion(
            bm25_results=bm25_results,
            dense_results=dense_results,
            top_k=candidate_k,
            rrf_k=rrf_k,
            bm25_weight=bm25_weight,
            dense_weight=dense_weight,
        ), {
            "method": "weighted_rrf",
            "rrf_k": rrf_k,
            "bm25_weight": bm25_weight,
            "dense_weight": dense_weight,
        }
    if method == "normalized_score":
        alpha = _env_float("FUSION_NORMALIZED_ALPHA", 0.55)
        return normalized_score_fusion(
            bm25_results=bm25_results,
            dense_results=dense_results,
            top_k=candidate_k,
            alpha=alpha,
        ), {
            "method": "normalized_score_fusion",
            "alpha": alpha,
        }
    rrf_k = _env_int("FUSION_RRF_K", RRF_K)
    return rrf_fusion(
        bm25_results=bm25_results,
        dense_results=dense_results,
        top_k=candidate_k,
        rrf_k=rrf_k,
    ), {
        "method": "reciprocal_rank_fusion",
        "rrf_k": rrf_k,
    }


def _threshold_config_from_env() -> ThresholdConfig:
    return ThresholdConfig(
        bm25_min_score=_env_optional_float("BM25_MIN_SCORE"),
        dense_min_score=_env_optional_float("DENSE_MIN_SCORE"),
        bm25_min_norm_score=_env_optional_float("BM25_MIN_NORM_SCORE"),
        dense_min_norm_score=_env_optional_float("DENSE_MIN_NORM_SCORE"),
        fusion_min_score=_env_optional_float("FUSION_MIN_SCORE"),
        rerank_min_score=_env_optional_float("RERANK_MIN_SCORE"),
        min_evidence_count=_env_int("MIN_EVIDENCE_COUNT", 0),
    )


def _env_optional_float(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _dense_search_safely(
    store: Store,
    query: str,
    *,
    top_k: int,
) -> tuple[list[SearchResult], str | None]:
    try:
        return store.dense_search(query, top_k=top_k), None
    except Exception as exc:
        return [], str(exc)


def _with_pipeline_metadata(
    *,
    results: list[SearchResult],
    question: str,
    chunks: list[Chunk],
    top_k: int,
    candidate_k: int,
    preprocess_latency_ms: int,
    bm25_latency_ms: int,
    dense_latency_ms: int,
    fusion_latency_ms: int,
    rerank_latency_ms: int,
    pre_fusion_threshold_trace: dict[str, object],
    fusion_method_trace: dict[str, object],
    fusion_threshold_trace: dict[str, object],
    rerank_threshold_trace: dict[str, object],
    rerank_trace: dict[str, object],
    preprocessed_query: dict[str, str],
    bm25_results: list[SearchResult],
    dense_results: list[SearchResult],
    fused_results: list[SearchResult],
    dense_error: str | None,
) -> list[SearchResult]:
    bm25_by_chunk_id = _results_by_chunk_id(bm25_results)
    dense_by_chunk_id = _results_by_chunk_id(dense_results)
    fused_by_chunk_id = _results_by_chunk_id(fused_results)
    pipeline_trace = {
        "preprocess_query": {
            "tech": {
                "method": "lowercase_unicode_accent_normalization_tokenization",
                "token_pattern": r"\w+",
            },
            "latency_ms": preprocess_latency_ms,
            "input": {"query": question},
            "output": preprocessed_query,
        },
        "bm25_search": {
            "tech": {
                "library": "rank-bm25",
                "class": "BM25Okapi",
                "index_scope": "selected_documents",
                "candidate_k": candidate_k,
            },
            "latency_ms": bm25_latency_ms,
            "input": {
                "query": preprocessed_query["normalized"],
                "tokens": preprocessed_query["tokens"],
                "chunks": [_trace_chunk_ref(chunk) for chunk in chunks],
            },
            "output": [_trace_search_result(result) for result in bm25_results],
        },
        "dense_search": {
            "tech": {
                **dense_embedding_metadata(),
                "candidate_k": candidate_k,
            },
            "latency_ms": dense_latency_ms,
            "input": {
                "query": preprocessed_query["normalized"],
                "chunks": [_trace_chunk_ref(chunk) for chunk in chunks],
            },
            "output": {
                "results": [_trace_search_result(result) for result in dense_results],
                "error": dense_error,
            },
        },
        "rrf_fusion": {
            "tech": {
                "rrf_k": RRF_K,
                "candidate_k": candidate_k,
                **fusion_method_trace,
            },
            "latency_ms": fusion_latency_ms,
            "input": {
                "bm25_results": [_trace_search_result(result) for result in bm25_results],
                "dense_results": [_trace_search_result(result) for result in dense_results],
            },
            "output": [
                _trace_rrf_result(
                    result=result,
                    bm25_result=bm25_by_chunk_id.get(result.chunk.chunk_id),
                    dense_result=dense_by_chunk_id.get(result.chunk.chunk_id),
                )
                for result in fused_results
            ],
        },
        "thresholds": {
            "pre_fusion": pre_fusion_threshold_trace,
            "fusion": fusion_threshold_trace,
            "rerank": rerank_threshold_trace,
        },
        "rerank": {
            "tech": {
                **rerank_trace,
                "top_k": top_k,
            },
            "latency_ms": rerank_latency_ms,
            "input": {
                "query": preprocessed_query["normalized"],
                "candidates": [_trace_search_result(result) for result in fused_results],
            },
            "output": [_trace_search_result(result) for result in results],
        },
    }

    annotated_results: list[SearchResult] = []
    for result in results:
        chunk_id = result.chunk.chunk_id
        metadata = {
            **result.chunk.metadata,
            "retrieval_pipeline": "source_ingestion -> bm25 + dense -> rrf",
            "pipeline_trace": pipeline_trace,
            "preprocessed_query": preprocessed_query,
            "bm25": _stage_debug(bm25_by_chunk_id.get(chunk_id)),
            "dense": _stage_debug(dense_by_chunk_id.get(chunk_id)),
            "dense_error": dense_error,
            "rrf": _stage_debug(fused_by_chunk_id.get(chunk_id)),
            "rrf_contributions": _rrf_contributions(
                bm25_result=bm25_by_chunk_id.get(chunk_id),
                dense_result=dense_by_chunk_id.get(chunk_id),
            ),
            "final": {
                "rank": result.rank,
                "score": result.score,
                "retriever": result.retriever,
            },
        }
        annotated_chunk = Chunk(
            chunk_id=result.chunk.chunk_id,
            text=result.chunk.text,
            metadata=metadata,
        )
        annotated_results.append(
            SearchResult(
                chunk=annotated_chunk,
                score=result.score,
                rank=result.rank,
                retriever=result.retriever,
            )
        )
    return annotated_results


def _results_by_chunk_id(results: list[SearchResult]) -> dict[str, SearchResult]:
    return {result.chunk.chunk_id: result for result in results}


def _stage_debug(result: SearchResult | None) -> dict[str, object] | None:
    if result is None:
        return None
    return {
        "rank": result.rank,
        "score": result.score,
        "retriever": result.retriever,
    }


def _trace_search_result(result: SearchResult) -> dict[str, object]:
    return {
        "rank": result.rank,
        "score": result.score,
        "retriever": result.retriever,
        "chunk_id": result.chunk.chunk_id,
        "text": result.chunk.text,
        "metadata": result.chunk.metadata,
    }


def _trace_rrf_result(
    *,
    result: SearchResult,
    bm25_result: SearchResult | None,
    dense_result: SearchResult | None,
) -> dict[str, object]:
    return {
        **_trace_search_result(result),
        "contributions": _rrf_contributions(
            bm25_result=bm25_result,
            dense_result=dense_result,
        ),
    }


def _rrf_contributions(
    *,
    bm25_result: SearchResult | None,
    dense_result: SearchResult | None,
) -> dict[str, object]:
    contributions: dict[str, object] = {}
    if bm25_result is not None:
        contributions["bm25"] = _rrf_contribution(bm25_result)
    if dense_result is not None:
        contributions["dense"] = _rrf_contribution(dense_result)
    total_rrf_score = 0.0
    for contribution in contributions.values():
        if isinstance(contribution, dict):
            rrf_score = contribution.get("rrf_score")
            if isinstance(rrf_score, int | float):
                total_rrf_score += float(rrf_score)
    contributions["total_rrf_score"] = total_rrf_score
    return contributions


def _rrf_contribution(result: SearchResult) -> dict[str, object]:
    return {
        "rank": result.rank,
        "score": result.score,
        "retriever": result.retriever,
        "rrf_score": 1.0 / (RRF_K + result.rank),
    }


def _trace_chunk_ref(chunk: Chunk) -> dict[str, object]:
    return {
        "chunk_id": chunk.chunk_id,
        "source": chunk.metadata.get("source"),
        "page": chunk.metadata.get("page"),
        "section": chunk.metadata.get("section"),
        "text_preview": _preview(chunk.text, 240),
    }


def _trace_chunk(chunk: Chunk) -> dict[str, object]:
    return {
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
        "metadata": chunk.metadata,
    }


def _chunks_as_text(chunks: list[Chunk]) -> str:
    return "\n\n".join(chunk.text for chunk in chunks if chunk.text.strip())


def _url_ingestion_trace(*, requested_url: str, chunks: list[Chunk]) -> dict[str, object]:
    return {
        "requested_url": requested_url,
        "final_url": _first_metadata_value(chunks, "url") or requested_url,
        "title": _first_metadata_value(chunks, "title"),
        "section_count": len(_unique_metadata_values(chunks, "section")),
        "sections": _unique_metadata_values(chunks, "section"),
        "chunking_methods": _unique_metadata_values(chunks, "chunking_method"),
        "chunking_providers": _unique_metadata_values(chunks, "chunking_provider"),
        "chunking_models": _unique_metadata_values(chunks, "chunking_model"),
    }


def _first_metadata_value(chunks: list[Chunk], key: str) -> object | None:
    for chunk in chunks:
        value = chunk.metadata.get(key)
        if value not in {None, ""}:
            return value
    return None


def _unique_metadata_values(chunks: list[Chunk], key: str) -> list[object]:
    values: list[object] = []
    for chunk in chunks:
        value = chunk.metadata.get(key)
        if value in {None, ""} or value in values:
            continue
        values.append(value)
    return values


def _preview(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _trace_preview_chars() -> int:
    raw = os.getenv("RAG_TRACE_PREVIEW_CHARS", "4000")
    try:
        return max(int(raw), 0)
    except ValueError:
        return 4000


def _full_trace_content(key: str, value: str) -> dict[str, str]:
    if _env_flag("RAG_TRACE_FULL_CONTENT"):
        return {key: value}
    return {}


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _latency_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    return name if name else "document.pdf"


def _safe_url_filename(url: str) -> str:
    cleaned = re.sub(r"^https?://", "", url.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", cleaned).strip("-._")
    return f"{cleaned[:96] or 'url-source'}.txt"


def _safe_text_filename(title: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", title.strip()).strip("-._")
    return f"{cleaned[:96] or 'text-source'}.txt"


def _safe_document_id(document_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", document_id.strip()).strip("_")
    if not safe:
        raise ValueError("document_id cannot be empty.")
    return safe


def _record_failed_url(*, url: str, reason: str) -> None:
    failed_path = Path("storage/url_ingest_failed_links.txt")
    failed_path.parent.mkdir(parents=True, exist_ok=True)
    with failed_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{url}\t{reason}\n")
