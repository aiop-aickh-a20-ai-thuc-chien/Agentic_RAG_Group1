"""Local source ingestion and retrieval provider.

This provider lets the API run the same Module 5 generation/citation flow
without RAGFlow for PDF, URL, and text documents. It is intentionally
lightweight: source-specific ingestion modules produce shared chunks, chunks are
stored as JSONL, and retrieval is hybrid. Dense retrieval is traced when OpenAI
embeddings are configured, and the provider falls back to BM25-only fusion when
embeddings are unavailable.
"""

from __future__ import annotations

import json
import logging
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
from agentic_rag.ingestion.dedup_detect import (
    DEDUP_METADATA_KEY,
    DedupConfig,
    DedupReport,
    DuplicateMatch,
    add_duplicate_metadata_to_chunks,
    detect_duplicates,
    documents_from_chunks,
    hamming_distance,
    remove_duplicate_metadata_from_chunks,
    sha256_fingerprint,
    simhash_fingerprint,
)
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
    embed_chunk_texts,
    qdrant_hybrid_search,
    qdrant_similar_by_vectors,
    upsert_dense_embeddings,
)

logger = logging.getLogger(__name__)


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
        dedup_started_at = time.perf_counter()
        chunks, dedup_trace, dedup_dense_vectors = self._apply_dedup_to_new_chunks(
            document_id=document_id,
            chunks=chunks,
        )
        dedup_trace["latency_ms"] = _latency_ms(dedup_started_at)
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
                precomputed_dense_vectors=dedup_dense_vectors,
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
                "deduplication": dedup_trace,
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
        dedup_started_at = time.perf_counter()
        chunks, dedup_trace, dedup_dense_vectors = self._apply_dedup_to_new_chunks(
            document_id=document_id,
            chunks=chunks,
        )
        dedup_trace["latency_ms"] = _latency_ms(dedup_started_at)
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
                precomputed_dense_vectors=dedup_dense_vectors,
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
                "deduplication": dedup_trace,
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
        dedup_started_at = time.perf_counter()
        chunks, dedup_trace, dedup_dense_vectors = self._apply_dedup_to_new_chunks(
            document_id=document_id,
            chunks=chunks,
        )
        dedup_trace["latency_ms"] = _latency_ms(dedup_started_at)
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
                precomputed_dense_vectors=dedup_dense_vectors,
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
                "deduplication": dedup_trace,
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

    def backfill_dedup(
        self,
        *,
        strict_embedding: bool = False,
        dry_run: bool = False,
    ) -> dict[str, object]:
        """Backfill duplicate metadata across all already-stored chunks."""

        started_at = time.perf_counter()
        chunks = self._chunks_for_documents(None)
        cleaned_chunks = remove_duplicate_metadata_from_chunks(chunks)
        if not cleaned_chunks:
            return {
                "enabled": _dedup_enabled(),
                "dry_run": dry_run,
                "chunk_count": 0,
                "updated_chunk_count": 0,
                "updated_document_count": 0,
                "deduplication": _empty_dedup_trace(reason="no_chunks"),
                "dense_index": {"enabled": False, "reason": "no_chunks"},
                "latency_ms": _latency_ms(started_at),
            }

        eval_reference_ids, eval_reference_error = _load_eval_reference_ids()
        document_metadata = self._dedup_document_sort_metadata()
        canonical_chunks = _canonical_sorted_chunks(
            cleaned_chunks,
            document_metadata=document_metadata,
            eval_reference_ids=eval_reference_ids,
        )
        enriched_canonical_chunks, dedup_trace = _dedup_enrich_chunks(
            corpus_chunks=canonical_chunks,
            target_chunks=canonical_chunks,
            strict_embedding=strict_embedding,
        )
        dedup_trace["canonical_policy"] = _dedup_canonical_policy_trace(
            mode="backfill",
            eval_reference_ids=eval_reference_ids,
            eval_reference_error=eval_reference_error,
            document_metadata_count=len(document_metadata),
        )
        enriched_by_chunk_id = {chunk.chunk_id: chunk for chunk in enriched_canonical_chunks}
        enriched_chunks = [
            enriched_by_chunk_id.get(chunk.chunk_id, chunk) for chunk in cleaned_chunks
        ]
        changed_chunks = [
            enriched
            for original, enriched in zip(cleaned_chunks, enriched_chunks, strict=True)
            if original.metadata != enriched.metadata
        ]
        grouped = _chunks_by_document(enriched_chunks)
        updated_document_ids = sorted(
            {
                str(chunk.metadata.get("document_id") or "")
                for chunk in changed_chunks
                if chunk.metadata.get("document_id")
            }
        )
        dense_index_trace: dict[str, object]
        index_trace: dict[str, object]
        if dry_run:
            dense_index_trace = {"enabled": False, "dry_run": True}
            index_trace = {"enabled": False, "dry_run": True}
        else:
            for document_id, document_chunks in grouped.items():
                self._replace_document_chunks(document_id=document_id, chunks=document_chunks)
            dense_index_trace = _upsert_dense_embeddings_safely(enriched_chunks)
            index_trace = _replace_all_candidate_index(enriched_chunks)
            from agentic_rag.autodata_eval import dedup_store as _dedup_store
            _dedup_store.upsert_corpus_stats(
                chunk_count=len(chunks),
                document_count=len(grouped),
            )

        return {
            "enabled": _dedup_enabled(),
            "dry_run": dry_run,
            "chunk_count": len(chunks),
            "updated_chunk_count": len(changed_chunks),
            "document_count": len(grouped),
            "updated_document_count": len(updated_document_ids),
            "updated_document_ids": updated_document_ids,
            "deduplication": dedup_trace,
            "dense_index": dense_index_trace,
            "candidate_index": index_trace,
            "latency_ms": _latency_ms(started_at),
        }

    def rebuild_dedup_index(self, *, refresh: bool = True) -> dict[str, object]:
        """Rebuild the Neon candidate index from current chunk metadata.

        Reads chunks once (from the TTL cache, or S3 when ``refresh=True``) and
        replaces the whole ``dedup_candidates`` table — no re-detection, no
        re-embedding. This is the slow-but-occasional path; normal page loads
        read straight from Neon.
        """

        from agentic_rag.autodata_eval import dedup_store

        started_at = time.perf_counter()
        chunks = self._cached_all_chunks(refresh=refresh)
        document_count = len({c.metadata.get("document_id") for c in chunks if c.metadata.get("document_id")})
        rows = _dedup_candidate_rows(chunks)
        written = dedup_store.replace_all_candidates(rows)
        dedup_store.upsert_corpus_stats(chunk_count=len(chunks), document_count=document_count)
        return {
            "chunk_count": len(chunks),
            "document_count": document_count,
            "candidate_rows": written,
            "latency_ms": _latency_ms(started_at),
        }

    def dedup_review_items(
        self,
        *,
        layer: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
        q: str | None = None,
        limit: int = 500,
        refresh: bool = False,
    ) -> list[dict[str, object]]:
        """Build duplicate candidates straight from chunk metadata (no Neon).

        Used by the rebuild path and tests; the live review endpoint reads from
        the Neon index instead. Chunks come from the in-memory TTL cache.
        """

        chunks = self._cached_all_chunks(refresh=refresh)
        return _dedup_review_items(
            chunks,
            layer=layer,
            status=status,
            source_type=source_type,
            q=q,
            limit=limit,
        )

    def delete_all_documents(self) -> int:
        """Delete all source documents, chunks, files and vectors."""
        import shutil

        count = 0
        self._invalidate_dedup_chunk_cache()
        _replace_all_candidate_index([], rows=[])
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

        self._invalidate_dedup_chunk_cache()
        _delete_document_candidate_index(document_id)
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
                    exclude_dedup_layers=request.exclude_dedup_layers or None,
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

    def _replace_document_chunks(self, *, document_id: str, chunks: list[Chunk]) -> None:
        self._invalidate_dedup_chunk_cache()
        if self._source_store is not None:
            self._source_store.replace_document_chunks(document_id, chunks)
            return
        self._write_chunks(document_id=document_id, chunks=chunks)

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
        precomputed_dense_vectors: list[list[float]] | None = None,
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
            dense_index_trace = _upsert_dense_embeddings_safely(
                chunks,
                precomputed_dense_vectors=precomputed_dense_vectors,
            )
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
        finally:
            self._invalidate_dedup_chunk_cache()
        return source_store_trace, dense_index_trace

    def _apply_dedup_to_new_chunks(
        self,
        *,
        document_id: str,
        chunks: list[Chunk],
    ) -> tuple[list[Chunk], dict[str, object], list[list[float]] | None]:
        """Mark duplicate candidates among the new chunks (new-vs-existing scope).

        Layers 1+2 compare fingerprints of the new chunks against the existing
        corpus only — never existing-vs-existing, which the backfill already
        covered. Layer 3 embeds the new chunks once, queries Qdrant (HNSW) for
        semantically similar indexed chunks, and returns those vectors so the
        subsequent upsert skips its own embedding pass.
        """
        clean_chunks = remove_duplicate_metadata_from_chunks(chunks)
        if not _dedup_enabled():
            return clean_chunks, _empty_dedup_trace(reason="disabled"), None
        if not clean_chunks:
            return clean_chunks, _empty_dedup_trace(reason="no_chunks"), None

        existing_chunks = [
            chunk
            for chunk in self._cached_all_chunks()
            if str(chunk.metadata.get("document_id") or "") != document_id
        ]
        existing_clean_chunks = remove_duplicate_metadata_from_chunks(existing_chunks)
        sorted_existing = _canonical_sorted_chunks(
            existing_clean_chunks,
            document_metadata={},
            eval_reference_ids=set(),
        )

        config = _dedup_config()
        exact_matches, simhash_matches, flagged_chunk_ids = _scoped_exact_and_simhash_matches(
            new_chunks=clean_chunks,
            existing_chunks=sorted_existing,
            config=config,
        )
        matched_pairs = {
            _dedup_pair_key(match.document_id, match.duplicate_document_id)
            for match in [*exact_matches, *simhash_matches]
        }
        embedding_matches, dense_vectors, embedding_status, embedding_error = (
            _scoped_embedding_matches(
                new_chunks=clean_chunks,
                document_id=document_id,
                config=config,
                has_existing_corpus=bool(sorted_existing),
                exclude_pairs=matched_pairs,
                exclude_chunk_ids=flagged_chunk_ids,
            )
        )
        report = DedupReport(
            document_count=len(sorted_existing) + len(clean_chunks),
            exact_matches=exact_matches,
            simhash_matches=simhash_matches,
            embedding_matches=embedding_matches,
        )
        enriched_chunks = add_duplicate_metadata_to_chunks(
            clean_chunks,
            report,
            reference_chunks=[*sorted_existing, *clean_chunks],
        )
        candidate_chunk_ids = [
            chunk.chunk_id for chunk in enriched_chunks if DEDUP_METADATA_KEY in chunk.metadata
        ]
        _replace_document_candidate_index(
            document_id,
            new_chunks=enriched_chunks,
            resolver_chunks=[*sorted_existing, *enriched_chunks],
        )
        dedup_trace: dict[str, object] = {
            "enabled": True,
            "comparison_scope": "new_vs_existing",
            "target_chunk_count": len(clean_chunks),
            "corpus_chunk_count": len(sorted_existing) + len(clean_chunks),
            "match_count": len(report.matches),
            "candidate_count": len(candidate_chunk_ids),
            "candidate_chunk_ids": candidate_chunk_ids,
            "exact_matches": len(exact_matches),
            "simhash_matches": len(simhash_matches),
            "embedding_matches": len(embedding_matches),
            "embedding_enabled": config.enable_embedding,
            "embedding_status": embedding_status,
            "embedding_error": embedding_error,
            "embedding_method": "qdrant_query",
            "simhash_hamming_threshold": config.simhash_hamming_threshold,
            "embedding_similarity_threshold": config.embedding_similarity_threshold,
        }
        dedup_trace["canonical_policy"] = _dedup_canonical_policy_trace(
            mode="existing_before_new",
            eval_reference_ids=set(),
            eval_reference_error=None,
            document_metadata_count=0,
        )
        return enriched_chunks, dedup_trace, dense_vectors

    def _dedup_document_sort_metadata(self) -> dict[str, dict[str, object]]:
        documents = self.list_documents(include_chunks=False)
        return {document.document_id: document.metadata for document in documents}

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

    def _dedup_cache_key(self) -> str:
        store_label = type(self._source_store).__name__ if self._source_store else "jsonl"
        return f"{store_label}|{self._store_dir}"

    def _cached_all_chunks(self, *, refresh: bool = False) -> list[Chunk]:
        key = self._dedup_cache_key()
        ttl = _dedup_chunk_cache_ttl_seconds()
        now = time.monotonic()
        if not refresh and ttl > 0:
            cached = _DEDUP_CHUNK_CACHE.get(key)
            if cached is not None and now - cached[0] <= ttl:
                return cached[1]
        chunks = self._chunks_for_documents(None)
        _DEDUP_CHUNK_CACHE[key] = (now, chunks)
        return chunks

    def _invalidate_dedup_chunk_cache(self) -> None:
        _DEDUP_CHUNK_CACHE.pop(self._dedup_cache_key(), None)

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


def _dedup_enrich_chunks(
    *,
    corpus_chunks: list[Chunk],
    target_chunks: list[Chunk],
    strict_embedding: bool,
) -> tuple[list[Chunk], dict[str, object]]:
    if not _dedup_enabled():
        return target_chunks, _empty_dedup_trace(reason="disabled")
    if not target_chunks or not corpus_chunks:
        return target_chunks, _empty_dedup_trace(reason="no_chunks")

    config = _dedup_config()
    embedding_error = None
    embedding_status = "disabled"
    resolved_config = config
    try:
        report = detect_duplicates(
            documents_from_chunks(corpus_chunks),
            config=config,
        )
        embedding_status = "completed" if config.enable_embedding else "disabled"
    except Exception as exc:
        if strict_embedding or not config.enable_embedding:
            raise
        embedding_error = str(exc)
        resolved_config = config.model_copy(update={"enable_embedding": False})
        report = detect_duplicates(
            documents_from_chunks(corpus_chunks),
            config=resolved_config,
        )
        embedding_status = "fallback_without_embedding"

    enriched = add_duplicate_metadata_to_chunks(
        target_chunks,
        report,
        reference_chunks=corpus_chunks,
    )
    candidate_chunk_ids = [
        chunk.chunk_id for chunk in enriched if DEDUP_METADATA_KEY in chunk.metadata
    ]
    trace = {
        "enabled": True,
        "target_chunk_count": len(target_chunks),
        "corpus_chunk_count": len(corpus_chunks),
        "match_count": len(report.matches),
        "candidate_count": len(candidate_chunk_ids),
        "candidate_chunk_ids": candidate_chunk_ids,
        "exact_matches": len(report.exact_matches),
        "simhash_matches": len(report.simhash_matches),
        "embedding_matches": len(report.embedding_matches),
        "embedding_enabled": resolved_config.enable_embedding,
        "embedding_status": embedding_status,
        "embedding_error": embedding_error,
        "simhash_hamming_threshold": resolved_config.simhash_hamming_threshold,
        "embedding_similarity_threshold": resolved_config.embedding_similarity_threshold,
    }
    return enriched, trace


def _scoped_exact_and_simhash_matches(
    *,
    new_chunks: list[Chunk],
    existing_chunks: list[Chunk],
    config: DedupConfig,
) -> tuple[list[DuplicateMatch], list[DuplicateMatch], set[str]]:
    """Find Layer 1+2 matches comparing new chunks against existing (+ earlier new) only.

    Returns ``(exact_matches, simhash_matches, flagged_new_chunk_ids)``.
    ``flagged_new_chunk_ids`` contains every new-chunk id caught by L1 OR L2 so
    that the caller can skip those chunks entirely in Layer 3 (chunk-level cascade).

    O(new x corpus) instead of the O(corpus^2) full-pairwise scan in
    ``detect_duplicates`` — existing-vs-existing pairs were already reported when
    those chunks themselves were uploaded (or by the backfill).
    """
    exact_matches: list[DuplicateMatch] = []
    simhash_matches: list[DuplicateMatch] = []
    bits = config.simhash_bits
    shingle_size = config.simhash_shingle_size

    existing_by_hash: dict[str, str] = {}
    existing_simhash: list[tuple[str, int]] = []
    for chunk in existing_chunks:
        if config.enable_exact:
            existing_by_hash.setdefault(sha256_fingerprint(chunk.text), chunk.chunk_id)
        if config.enable_simhash:
            simhash_value = simhash_fingerprint(chunk.text, bits=bits, shingle_size=shingle_size)
            existing_simhash.append((chunk.chunk_id, simhash_value))

    matched_pairs: set[tuple[str, str]] = set()
    flagged_new_chunk_ids: set[str] = set()
    seen_new_by_hash: dict[str, str] = {}
    new_simhash: list[tuple[str, int]] = []

    for chunk in new_chunks:
        if config.enable_exact:
            fingerprint = sha256_fingerprint(chunk.text)
            canonical_id = existing_by_hash.get(fingerprint) or seen_new_by_hash.get(fingerprint)
            if canonical_id and canonical_id != chunk.chunk_id:
                exact_matches.append(
                    DuplicateMatch(
                        layer="exact_sha256",
                        document_id=canonical_id,
                        duplicate_document_id=chunk.chunk_id,
                        score=1.0,
                        distance=0,
                        fingerprint=fingerprint,
                        reason="same normalized text SHA-256",
                    )
                )
                matched_pairs.add(_dedup_pair_key(canonical_id, chunk.chunk_id))
                flagged_new_chunk_ids.add(chunk.chunk_id)
            seen_new_by_hash.setdefault(fingerprint, chunk.chunk_id)

        # Chunk-level cascade: skip L2 if this chunk was already caught by L1.
        if config.enable_simhash and chunk.chunk_id not in flagged_new_chunk_ids:
            chunk_hash = simhash_fingerprint(chunk.text, bits=bits, shingle_size=shingle_size)
            for canonical_id, canonical_hash in (*existing_simhash, *new_simhash):
                pair = _dedup_pair_key(canonical_id, chunk.chunk_id)
                if pair in matched_pairs:
                    continue
                distance = hamming_distance(canonical_hash, chunk_hash)
                if distance > config.simhash_hamming_threshold:
                    continue
                simhash_matches.append(
                    DuplicateMatch(
                        layer="simhash",
                        document_id=canonical_id,
                        duplicate_document_id=chunk.chunk_id,
                        score=round(1.0 - (distance / bits), 6),
                        distance=distance,
                        fingerprint=f"{canonical_hash:0{bits // 4}x}:{chunk_hash:0{bits // 4}x}",
                        reason="SimHash Hamming distance within threshold",
                        metadata={
                            "bits": bits,
                            "shingle_size": shingle_size,
                            "hamming_threshold": config.simhash_hamming_threshold,
                        },
                    )
                )
                matched_pairs.add(pair)
                flagged_new_chunk_ids.add(chunk.chunk_id)
                break  # one match per chunk is enough; stop checking other canonicals
            new_simhash.append((chunk.chunk_id, chunk_hash))

    return exact_matches, simhash_matches, flagged_new_chunk_ids


def _scoped_embedding_matches(
    *,
    new_chunks: list[Chunk],
    document_id: str,
    config: DedupConfig,
    has_existing_corpus: bool,
    exclude_pairs: set[tuple[str, str]],
    exclude_chunk_ids: set[str] | None = None,
) -> tuple[list[DuplicateMatch], list[list[float]] | None, str, str | None]:
    """Layer 3 via Qdrant: embed new chunks once, HNSW-query indexed chunks.

    Returns ``(matches, dense_vectors, status, error)``. Vectors come back even
    when the query step fails so the caller can still reuse them for indexing.
    The new chunks are not in Qdrant yet at this point, and re-uploaded versions
    of the same document are excluded by document_id filter — no self matches.
    Chunks in ``exclude_chunk_ids`` (already flagged by L1/L2) are skipped entirely.
    """
    if not config.enable_embedding:
        return [], None, "disabled", None
    if not _qdrant_vector_store_enabled():
        return [], None, "skipped_no_qdrant", None

    excluded_chunks = exclude_chunk_ids or set()
    eligible_chunks = [c for c in new_chunks if c.chunk_id not in excluded_chunks]
    if not eligible_chunks:
        return [], None, "all_chunks_already_flagged", None

    try:
        vectors = embed_chunk_texts([chunk.text for chunk in eligible_chunks])
    except Exception as exc:
        return [], None, "embed_failed", str(exc)
    if not has_existing_corpus:
        return [], vectors, "no_existing_corpus", None

    try:
        hits_per_chunk = qdrant_similar_by_vectors(
            vectors,
            exclude_document_id=document_id,
            score_threshold=config.embedding_similarity_threshold,
            top_k=5,
        )
    except Exception as exc:
        return [], vectors, "query_failed", str(exc)

    matches: list[DuplicateMatch] = []
    for chunk, hits in zip(eligible_chunks, hits_per_chunk, strict=True):
        for hit in hits:
            canonical_id = str(hit.get("chunk_id") or "")
            if not canonical_id or canonical_id == chunk.chunk_id:
                continue
            pair = _dedup_pair_key(canonical_id, chunk.chunk_id)
            if pair in exclude_pairs:
                continue
            raw_score = hit.get("score")
            score_value = float(raw_score) if isinstance(raw_score, int | float) else 0.0
            score = min(max(score_value, 0.0), 1.0)
            if score < config.embedding_similarity_threshold:
                continue
            matches.append(
                DuplicateMatch(
                    layer="embedding_similarity",
                    document_id=canonical_id,
                    duplicate_document_id=chunk.chunk_id,
                    score=round(score, 6),
                    reason="embedding cosine similarity above threshold",
                    metadata={
                        "similarity_threshold": config.embedding_similarity_threshold,
                        "method": "qdrant_query",
                        "canonical_document_id": hit.get("document_id"),
                    },
                )
            )
            exclude_pairs.add(pair)
    return matches, vectors, "completed", None


def _dedup_pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def _canonical_sorted_chunks(
    chunks: list[Chunk],
    *,
    document_metadata: dict[str, dict[str, object]],
    eval_reference_ids: set[str],
) -> list[Chunk]:
    return sorted(
        chunks,
        key=lambda chunk: _canonical_chunk_sort_key(
            chunk,
            document_metadata=document_metadata,
            eval_reference_ids=eval_reference_ids,
        ),
    )


def _canonical_chunk_sort_key(
    chunk: Chunk,
    *,
    document_metadata: dict[str, dict[str, object]],
    eval_reference_ids: set[str],
) -> tuple[int, int, str, str, int, str]:
    metadata = chunk.metadata
    document_id = str(metadata.get("document_id") or "")
    doc_metadata = document_metadata.get(document_id, {})
    created_at = _first_metadata_text(
        metadata,
        doc_metadata,
        keys=("created_at", "ingested_at", "uploaded_at", "created", "timestamp"),
    )
    return (
        0
        if _chunk_has_eval_reference(
            chunk,
            doc_metadata=doc_metadata,
            eval_reference_ids=eval_reference_ids,
        )
        else 1,
        0 if created_at else 1,
        created_at,
        document_id,
        _chunk_index_sort_value(metadata),
        chunk.chunk_id,
    )


def _chunk_has_eval_reference(
    chunk: Chunk,
    *,
    doc_metadata: dict[str, object],
    eval_reference_ids: set[str],
) -> bool:
    document_id = str(chunk.metadata.get("document_id") or "")
    if chunk.chunk_id in eval_reference_ids or document_id in eval_reference_ids:
        return True

    for metadata in (chunk.metadata, doc_metadata):
        for key in (
            "has_eval_reference",
            "is_eval_reference",
            "eval_reference_count",
            "eval_question_count",
            "source_question_count",
            "approved_question_count",
            "question_count",
        ):
            if _truthy_metadata_value(metadata.get(key)):
                return True
    return False


def _truthy_metadata_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value > 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized not in {"", "0", "false", "no", "none", "null"}
    return value is not None


def _first_metadata_text(
    *metadata_sources: dict[str, object],
    keys: tuple[str, ...],
) -> str:
    for metadata in metadata_sources:
        for key in keys:
            value = metadata.get(key)
            if value is None or value == "":
                continue
            return str(value)
    return ""


def _chunk_index_sort_value(metadata: dict[str, object]) -> int:
    direct = _metadata_int(metadata, "chunk_index")
    if direct is not None:
        return direct
    for key in ("storage_chunk_id", "chunk_id"):
        raw = str(metadata.get(key) or "")
        match = re.search(r"(?::|_c)(\d+)$", raw)
        if match:
            return int(match.group(1))
    return 1_000_000


def _load_eval_reference_ids() -> tuple[set[str], str | None]:
    if not os.getenv("NEON_CONNECTION", "").strip():
        return set(), None

    queries = (
        """
        SELECT document_id, source_chunk_ids
        FROM eval_questions
        WHERE deleted_at IS NULL
        """,
        """
        SELECT document_id, source_chunk_ids
        FROM eval_questions
        """,
    )
    last_error: str | None = None
    for query in queries:
        try:
            from agentic_rag.autodata_eval.db import get_conn

            with get_conn() as conn, conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
        except Exception as exc:
            last_error = str(exc)
            continue

        reference_ids: set[str] = set()
        for row in rows:
            _add_eval_reference_value(reference_ids, row.get("document_id"))
            _add_eval_reference_value(reference_ids, row.get("source_chunk_ids"))
        return reference_ids, None

    return set(), last_error


def _add_eval_reference_value(reference_ids: set[str], value: object) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        for nested in value.values():
            _add_eval_reference_value(reference_ids, nested)
        return
    if isinstance(value, list | tuple | set):
        for nested in value:
            _add_eval_reference_value(reference_ids, nested)
        return
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return
        if stripped.startswith("[") or stripped.startswith("{"):
            with suppress(ValueError, TypeError):
                parsed = json.loads(stripped)
                if parsed != stripped:
                    _add_eval_reference_value(reference_ids, parsed)
                    return
        parts = [
            part.strip().strip("\"'")
            for part in re.split(r",|\s+", stripped.strip("{}[]"))
            if part.strip().strip("\"'")
        ]
        if len(parts) > 1:
            for part in parts:
                reference_ids.add(part)
            return
        reference_ids.add(stripped.strip("\"'"))
        return
    reference_ids.add(str(value))


def _dedup_canonical_policy_trace(
    *,
    mode: str,
    eval_reference_ids: set[str],
    eval_reference_error: str | None,
    document_metadata_count: int,
) -> dict[str, object]:
    trace: dict[str, object] = {
        "mode": mode,
        "priority": [
            "eval_referenced_document_or_chunk",
            "older_created_at",
            "document_id",
            "chunk_index",
            "chunk_id",
        ],
        "eval_reference_count": len(eval_reference_ids),
        "document_metadata_count": document_metadata_count,
    }
    if eval_reference_error:
        trace["eval_reference_error"] = eval_reference_error
    return trace


# Module-level chunk cache for the dedup review endpoint + upload-time dedup.
# Reading every chunk from S3 takes minutes; mutations invalidate the entry so
# the cache never serves data older than the last write from this process.
_DEDUP_CHUNK_CACHE: dict[str, tuple[float, list[Chunk]]] = {}


def _dedup_chunk_cache_ttl_seconds() -> float:
    raw = os.getenv("DEDUP_REVIEW_CACHE_TTL_SECONDS", "300")
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return 300.0


def _dedup_config() -> DedupConfig:
    return DedupConfig(
        enable_exact=_env_flag_default("DEDUP_ENABLE_EXACT", True),
        enable_simhash=_env_flag_default("DEDUP_ENABLE_SIMHASH", True),
        enable_embedding=_env_flag_default("DEDUP_ENABLE_EMBEDDING", True),
        simhash_bits=_env_int("DEDUP_SIMHASH_BITS", 64),
        simhash_shingle_size=_env_int("DEDUP_SIMHASH_SHINGLE_SIZE", 4),
        simhash_hamming_threshold=_env_int("DEDUP_SIMHASH_HAMMING_THRESHOLD", 6),
        embedding_similarity_threshold=_env_float("DEDUP_EMBEDDING_SIMILARITY_THRESHOLD", 0.92),
        embedding_method=os.getenv("DEDUP_EMBEDDING_METHOD") or None,
    )


def _empty_dedup_trace(*, reason: str) -> dict[str, object]:
    return {
        "enabled": _dedup_enabled(),
        "reason": reason,
        "target_chunk_count": 0,
        "corpus_chunk_count": 0,
        "match_count": 0,
        "candidate_count": 0,
        "candidate_chunk_ids": [],
        "exact_matches": 0,
        "simhash_matches": 0,
        "embedding_matches": 0,
        "embedding_enabled": False,
        "embedding_status": "skipped",
        "embedding_error": None,
    }


def _chunks_by_document(chunks: list[Chunk]) -> dict[str, list[Chunk]]:
    grouped: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        document_id = str(chunk.metadata.get("document_id") or "")
        if not document_id:
            document_id = _document_id_from_chunks([chunk], fallback="document")
        grouped.setdefault(document_id, []).append(chunk)
    return grouped


def _dedup_review_items(
    chunks: list[Chunk],
    *,
    layer: str | None,
    status: str | None,
    source_type: str | None,
    q: str | None,
    limit: int,
) -> list[dict[str, object]]:
    resolved_limit = max(min(limit, 2000), 1)
    normalized_layer = layer.strip().lower() if layer else None
    normalized_status = status.strip().lower() if status else None
    normalized_source_type = source_type.strip().lower() if source_type else None
    normalized_query = _normalize_text(q) if q else ""
    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    items: list[dict[str, object]] = []

    for duplicate_chunk in chunks:
        dedup_metadata = duplicate_chunk.metadata.get(DEDUP_METADATA_KEY)
        if not isinstance(dedup_metadata, dict):
            continue
        review_status = str(dedup_metadata.get("review_status") or "pending")
        duplicate_status = str(dedup_metadata.get("status") or "duplicate_candidate")
        if normalized_status and normalized_status not in {
            review_status.lower(),
            duplicate_status.lower(),
        }:
            continue
        if normalized_source_type:
            duplicate_source_type = str(duplicate_chunk.metadata.get("source_type") or "").lower()
            if duplicate_source_type != normalized_source_type:
                continue

        matches = dedup_metadata.get("matches")
        if not isinstance(matches, list):
            continue
        for match in matches:
            if not isinstance(match, dict):
                continue
            detected_layer = str(match.get("detected_layer") or "")
            if normalized_layer and detected_layer.lower() != normalized_layer:
                continue
            canonical_chunk_id = str(match.get("canonical_chunk_id") or "")
            canonical_chunk = chunk_by_id.get(canonical_chunk_id)
            item = {
                "id": "::".join(
                    [
                        canonical_chunk_id or "missing",
                        duplicate_chunk.chunk_id,
                        detected_layer or "unknown",
                    ]
                ),
                "status": duplicate_status,
                "review_status": review_status,
                "layer": detected_layer,
                "score": match.get("score"),
                "distance": match.get("distance"),
                "reason": match.get("reason"),
                "group_id": dedup_metadata.get("group_id"),
                "canonical": _dedup_chunk_summary(canonical_chunk),
                "duplicate": _dedup_chunk_summary(duplicate_chunk),
            }
            if normalized_query and normalized_query not in _normalize_text(str(item)):
                continue
            items.append(item)
            if len(items) >= resolved_limit:
                return items
    return items


def _dedup_chunk_summary(chunk: Chunk | None) -> dict[str, object] | None:
    if chunk is None:
        return None
    metadata = chunk.metadata
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": metadata.get("document_id"),
        "document_name": metadata.get("document_name") or metadata.get("file_name"),
        "source_type": metadata.get("source_type"),
        "source": metadata.get("source") or metadata.get("url"),
        "page": metadata.get("page"),
        "section": metadata.get("section"),
        "text": chunk.text,
        "metadata": metadata,
    }


def _dedup_candidate_rows(
    chunks: list[Chunk],
    *,
    resolver_chunks: list[Chunk] | None = None,
) -> list[dict[str, object]]:
    """Flatten duplicate-candidate chunk metadata into Neon-index rows.

    Iterates the duplicate (flagged) chunks; ``resolver_chunks`` supplies the
    wider set used to resolve each canonical chunk's text/source (the canonical
    side may live outside ``chunks`` during an incremental upload).
    """
    chunk_by_id = {chunk.chunk_id: chunk for chunk in (resolver_chunks or chunks)}
    rows: list[dict[str, object]] = []
    for duplicate_chunk in chunks:
        dedup_metadata = duplicate_chunk.metadata.get(DEDUP_METADATA_KEY)
        if not isinstance(dedup_metadata, dict):
            continue
        matches = dedup_metadata.get("matches")
        if not isinstance(matches, list):
            continue
        review_status = str(dedup_metadata.get("review_status") or "pending")
        status = str(dedup_metadata.get("status") or "duplicate_candidate")
        group_id = _coerce_text(dedup_metadata.get("group_id"))
        duplicate = _dedup_chunk_summary(duplicate_chunk) or {}
        for match in matches:
            if not isinstance(match, dict):
                continue
            layer = str(match.get("detected_layer") or "")
            canonical_chunk_id = str(match.get("canonical_chunk_id") or "")
            canonical = _dedup_chunk_summary(chunk_by_id.get(canonical_chunk_id)) or {}
            rows.append(
                {
                    "id": "::".join(
                        [
                            canonical_chunk_id or "missing",
                            duplicate_chunk.chunk_id,
                            layer or "unknown",
                        ]
                    ),
                    "layer": layer,
                    "score": _coerce_float(match.get("score")),
                    "distance": _coerce_int(match.get("distance")),
                    "reason": _coerce_text(match.get("reason")),
                    "group_id": group_id,
                    "status": status,
                    "review_status": review_status,
                    "duplicate_chunk_id": duplicate_chunk.chunk_id,
                    "duplicate_document_id": _coerce_text(duplicate.get("document_id")),
                    "duplicate_document_name": _coerce_text(duplicate.get("document_name")),
                    "duplicate_source_type": _coerce_text(duplicate.get("source_type")),
                    "duplicate_source": _coerce_text(duplicate.get("source")),
                    "duplicate_section": _coerce_text(duplicate.get("section")),
                    "duplicate_page": _coerce_text(duplicate.get("page")),
                    "duplicate_text": str(duplicate.get("text") or ""),
                    "canonical_chunk_id": _coerce_text(canonical.get("chunk_id")),
                    "canonical_document_id": _coerce_text(canonical.get("document_id")),
                    "canonical_document_name": _coerce_text(canonical.get("document_name")),
                    "canonical_source_type": _coerce_text(canonical.get("source_type")),
                    "canonical_source": _coerce_text(canonical.get("source")),
                    "canonical_section": _coerce_text(canonical.get("section")),
                    "canonical_page": _coerce_text(canonical.get("page")),
                    "canonical_text": str(canonical.get("text") or ""),
                }
            )
    return rows


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _coerce_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _replace_all_candidate_index(
    chunks: list[Chunk],
    *,
    rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Mirror every candidate into the Neon index (non-fatal on failure)."""
    try:
        from agentic_rag.autodata_eval import dedup_store

        candidate_rows = rows if rows is not None else _dedup_candidate_rows(chunks)
        written = dedup_store.replace_all_candidates(candidate_rows)
        return {"enabled": True, "candidate_rows": written}
    except Exception as exc:
        logger.exception("Failed to rebuild dedup candidate index in Neon")
        return {"enabled": False, "error": str(exc)}


def _replace_document_candidate_index(
    document_id: str,
    *,
    new_chunks: list[Chunk],
    resolver_chunks: list[Chunk],
) -> None:
    """Sync one document's candidate rows in Neon (non-fatal on failure)."""
    try:
        from agentic_rag.autodata_eval import dedup_store

        rows = _dedup_candidate_rows(new_chunks, resolver_chunks=resolver_chunks)
        dedup_store.replace_document_candidates(document_id, rows)
    except Exception:
        logger.exception("Failed to sync dedup candidate index for %s", document_id)


def _delete_document_candidate_index(document_id: str) -> None:
    """Drop a deleted document's candidate rows from Neon (non-fatal)."""
    try:
        from agentic_rag.autodata_eval import dedup_store

        dedup_store.delete_document_candidates(document_id)
    except Exception:
        logger.exception("Failed to delete dedup candidate index for %s", document_id)


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


def _upsert_dense_embeddings_safely(
    chunks: list[Chunk],
    *,
    precomputed_dense_vectors: list[list[float]] | None = None,
) -> dict[str, object]:
    started_at = time.perf_counter()

    def _upsert(target_chunks: list[Chunk]) -> dict[str, object]:
        # Only pass the kwarg when vectors are actually supplied — keeps the
        # single-positional-argument signature for callers and test doubles.
        if precomputed_dense_vectors is not None and len(precomputed_dense_vectors) == len(
            target_chunks
        ):
            return upsert_dense_embeddings(
                target_chunks,
                precomputed_dense_vectors=precomputed_dense_vectors,
            )
        return upsert_dense_embeddings(target_chunks)

    if _qdrant_vector_store_enabled():
        trace = _upsert(chunks)
        return {**trace, "latency_ms": _latency_ms(started_at)}

    embedding_metadata = dense_embedding_metadata()
    try:
        trace = _upsert(chunks)
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


def _env_flag_default(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _dedup_enabled() -> bool:
    return _env_flag_default("INGESTION_DEDUP_ENABLED", True)


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
