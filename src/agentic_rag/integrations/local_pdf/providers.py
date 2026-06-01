"""Local PDF ingestion and retrieval provider.

This provider lets the API run the same Module 5 generation/citation flow
without RAGFlow for PDF documents. It is intentionally lightweight: PDF parsing
uses the existing ingestion module, chunks are stored as JSONL, and retrieval is
hybrid. Dense retrieval is traced when OpenAI embeddings are configured, and the
provider falls back to BM25-only fusion when embeddings are unavailable.
"""

from __future__ import annotations

import os
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_rag.core.contracts import Chunk, SearchResult
from agentic_rag.ingestion.pdf import load_pdf_chunks
from agentic_rag.retrieval.fusion import RRF_K, rerank_with_metadata, rrf_fusion
from agentic_rag.retrieval.search import Store, dense_embedding_metadata


@dataclass(frozen=True)
class LocalPdfUploadedDocument:
    """Normalized upload result returned to the UI/API layer."""

    document_id: str
    name: str
    dataset_id: str
    parse_started: bool
    trace: dict[str, object]


@dataclass(frozen=True)
class LocalPdfDocumentChunks:
    """One page of local PDF chunks plus the full chunk count."""

    chunks: list[Chunk]
    total_chunks: int


class LocalPdfEvidenceProvider:
    """Use internal PDF ingestion plus retrieval/fusion/rerank modules."""

    dataset_id = "local_pdf"

    def __init__(self, *, store_dir: Path) -> None:
        self._store_dir = store_dir
        self._files_dir = store_dir / "files"
        self._chunks_dir = store_dir / "chunks"
        self._files_dir.mkdir(parents=True, exist_ok=True)
        self._chunks_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> LocalPdfEvidenceProvider:
        """Create a local PDF provider from environment variables."""

        store_dir = Path(os.getenv("LOCAL_PDF_STORE_DIR", "storage/local_pdf"))
        return cls(store_dir=store_dir)

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
        document_id = f"local_pdf_{uuid.uuid4().hex}"
        safe_filename = _safe_filename(filename)
        pdf_path = self._files_dir / f"{document_id}.pdf"
        pdf_path.write_bytes(content)

        parse_started_at = time.perf_counter()
        chunks = load_pdf_chunks(str(pdf_path)) if start_parse else []
        parse_latency_ms = _latency_ms(parse_started_at)
        chunk_started_at = time.perf_counter()
        chunks = [
            _chunk_with_local_metadata(
                chunk=chunk,
                document_id=document_id,
                filename=safe_filename,
            )
            for chunk in chunks
        ]
        chunk_latency_ms = _latency_ms(chunk_started_at)
        write_started_at = time.perf_counter()
        self._write_chunks(document_id=document_id, chunks=chunks)
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
                    "stored_path": str(pdf_path),
                },
                "parse": {
                    "parser": "docling",
                    "started": start_parse,
                    "latency_ms": parse_latency_ms,
                },
                "chunking": {
                    "chunk_count": len(chunks),
                    "chunk_ids": [chunk.chunk_id for chunk in chunks],
                    "chunks": [_trace_chunk(chunk) for chunk in chunks],
                    "latency_ms": chunk_latency_ms,
                },
                "index_write": {
                    "type": "jsonl",
                    "path": str(self._chunk_path(document_id)),
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

    def retrieve(
        self,
        *,
        question: str,
        document_ids: list[str] | None = None,
        page_size: int | None = None,
    ) -> list[SearchResult]:
        """Run PDF chunks through BM25, dense retrieval, RRF, and rerank."""

        chunks = self._chunks_for_documents(document_ids)
        if not chunks:
            return []

        store = Store(chunks)
        preprocess_started_at = time.perf_counter()
        preprocessed_query = store.preprocess_query(question)
        preprocess_latency_ms = _latency_ms(preprocess_started_at)
        normalized_query = preprocessed_query["normalized"]
        if not normalized_query:
            return []

        top_k = page_size or _default_page_size()
        candidate_k = max(_default_candidate_count(), top_k)
        bm25_started_at = time.perf_counter()
        bm25_results = store.bm25_search(normalized_query, top_k=candidate_k)
        bm25_latency_ms = _latency_ms(bm25_started_at)
        dense_started_at = time.perf_counter()
        dense_results, dense_error = _dense_search_safely(
            store,
            normalized_query,
            top_k=candidate_k,
        )
        dense_latency_ms = _latency_ms(dense_started_at)
        fusion_started_at = time.perf_counter()
        fused_results = rrf_fusion(
            bm25_results=bm25_results,
            dense_results=dense_results,
            top_k=candidate_k,
        )
        fusion_latency_ms = _latency_ms(fusion_started_at)
        rerank_started_at = time.perf_counter()
        final_results, rerank_trace = rerank_with_metadata(
            query=normalized_query,
            candidates=fused_results,
            top_k=top_k,
        )
        rerank_latency_ms = _latency_ms(rerank_started_at)
        return _with_pipeline_metadata(
            results=final_results,
            question=question,
            chunks=chunks,
            top_k=top_k,
            candidate_k=candidate_k,
            preprocess_latency_ms=preprocess_latency_ms,
            bm25_latency_ms=bm25_latency_ms,
            dense_latency_ms=dense_latency_ms,
            fusion_latency_ms=fusion_latency_ms,
            rerank_latency_ms=rerank_latency_ms,
            rerank_trace=rerank_trace,
            preprocessed_query=preprocessed_query,
            bm25_results=bm25_results,
            dense_results=dense_results,
            fused_results=fused_results,
            dense_error=dense_error,
        )

    def _write_chunks(self, *, document_id: str, chunks: list[Chunk]) -> None:
        chunk_path = self._chunk_path(document_id)
        payload = "\n".join(chunk.model_dump_json() for chunk in chunks)
        chunk_path.write_text(f"{payload}\n" if payload else "", encoding="utf-8")

    def _read_chunks(self, document_id: str) -> list[Chunk]:
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
            chunks: list[Chunk] = []
            for document_id in document_ids:
                chunks.extend(self._read_chunks(document_id))
            return chunks

        chunks = []
        for chunk_path in sorted(self._chunks_dir.glob("*.jsonl")):
            chunks.extend(self._read_chunks(chunk_path.stem))
        return chunks

    def _chunk_path(self, document_id: str) -> Path:
        safe_document_id = _safe_document_id(document_id)
        return self._chunks_dir / f"{safe_document_id}.jsonl"


def _validate_pdf_upload(*, filename: str, content_type: str | None) -> None:
    is_pdf_name = filename.lower().endswith(".pdf")
    is_pdf_content = content_type in {None, "", "application/pdf"}
    if not is_pdf_name or not is_pdf_content:
        raise ValueError("Local PDF provider only supports PDF uploads.")


def _chunk_with_local_metadata(
    *,
    chunk: Chunk,
    document_id: str,
    filename: str,
) -> Chunk:
    metadata = {
        **chunk.metadata,
        "document_id": document_id,
        "dataset_id": LocalPdfEvidenceProvider.dataset_id,
        "source": filename,
        "document_name": filename,
        "file_name": filename,
        "source_type": "pdf",
        "provider": "local_pdf",
    }
    return Chunk(chunk_id=chunk.chunk_id, text=chunk.text, metadata=metadata)


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
                "method": "reciprocal_rank_fusion",
                "rrf_k": RRF_K,
                "candidate_k": candidate_k,
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
            "retrieval_pipeline": "pdf_ingestion -> bm25 + dense -> rrf -> rerank",
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


def _preview(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _latency_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    return name if name else "document.pdf"


def _safe_document_id(document_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", document_id.strip()).strip("_")
    if not safe:
        raise ValueError("document_id cannot be empty.")
    return safe
