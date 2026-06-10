"""HTTP API for the generation/UI slice of the RAG demo."""

from __future__ import annotations

import json
import logging
import os
import re
import time
import warnings
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError as UrlHTTPError
from urllib.error import URLError
from urllib.parse import quote, urlparse
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from agentic_rag.agent.graph import run_agent
from agentic_rag.autodata_eval.router import router as autodata_eval_router
from agentic_rag.core.contracts import (
    Answer,
    Chunk,
    ConversationMessage,
    EvidenceResolutionInput,
    SearchResult,
    SourceDocumentChunks,
    WorkflowRunInput,
)
from agentic_rag.core.ports import SourceEvidenceProvider
from agentic_rag.eval_review import router as eval_review_router
from agentic_rag.generation.answering import (
    AnswerDelta,
    AnswerDone,
    generate_answer_with_trace,
    stream_answer,
)
from agentic_rag.generation.evidence import (
    EvidenceProviderName,
    configured_evidence_provider_name,
    evidence_for_question,
    ragflow_provider_from_env,
    source_provider_from_env,
)
from agentic_rag.integrations.local_pdf.providers import (
    LocalPdfEvidenceProvider,
    local_pdf_backend_status,
)
from agentic_rag.integrations.ragflow.client import RAGFlowClientError
from agentic_rag.integrations.ragflow.config import RAGFlowConfigurationError
from agentic_rag.model_runtime.factory import preload_configured_models
from agentic_rag.observability.trace import (
    new_run_id,
    write_rag_trace,
    write_source_trace,
)
from agentic_rag.retrieval.fusion import (
    build_evidence_context as _build_evidence_context,
)
from agentic_rag.runtime_env import load_local_env

load_dotenv()
load_local_env()
warnings.filterwarnings("ignore", message=".*CollectionStore.*", category=Warning)

UPLOAD_FILE = File(...)
LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def _api_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Warm optional heavyweight models before the first user request."""
    from agentic_rag.autodata_eval.router import recover_stuck_runs

    _preload_configured_models()
    recover_stuck_runs()
    yield


def _preload_configured_models() -> None:
    result = preload_configured_models()
    reranker_result = result.get("reranker", {})
    if not isinstance(reranker_result, dict):
        return
    status = reranker_result.get("status")
    if status == "loaded":
        LOGGER.info(
            "Preloaded reranker model %s.",
            reranker_result.get("model"),
        )
    elif status == "failed":
        LOGGER.warning(
            "Reranker preload failed; falling back at request time: %s",
            reranker_result.get("fallback_reason"),
        )


class AnswerRequest(BaseModel):
    """Request body for the answer endpoint."""

    question: str = Field(min_length=1)
    history: list[ConversationMessage] | None = Field(
        default=None,
        description=(
            "Conversation history for context-aware query rewriting. "
            'Each entry: {"role": "user" | "assistant", "content": "..."}. '
            "Only used when AGENT_MODE=true."
        ),
    )
    evidence_context: str | None = None
    evidence_chunks: list[SearchResult] | None = None
    evidence_provider: EvidenceProviderName | None = None
    document_ids: list[str] | None = None
    use_mock_evidence: bool = Field(
        default=False,
        description=(
            "Return sample fixture data instead of real retrieval. "
            "Intended for local development and demos only. "
            "Never set this in production."
        ),
    )


class SourceUploadResponse(BaseModel):
    """Response for a document uploaded through the configured evidence provider."""

    provider: str
    dataset_id: str
    document_id: str
    name: str
    parse_started: bool
    source_type: str | None = None
    source: str | None = None


class SourceUrlRequest(BaseModel):
    """Request body for importing a URL as a RAGFlow source document."""

    url: str = Field(min_length=1, max_length=2048)


class SourceTextRequest(BaseModel):
    """Request body for importing raw text as a RAGFlow source document."""

    title: str | None = Field(default=None, max_length=160)
    text: str = Field(min_length=1)


class SourceChunksResponse(BaseModel):
    """Normalized chunks for one uploaded source."""

    provider: str
    document_id: str
    total_chunks: int
    chunks: list[SearchResult]


class SourceListItem(BaseModel):
    """One persisted source document for frontend hydration."""

    provider: str
    dataset_id: str
    document_id: str
    name: str
    source_type: str
    source: str
    total_chunks: int
    chunks: list[SearchResult]
    metadata: dict[str, object]


class SourceListResponse(BaseModel):
    """Persisted source documents available to the current provider."""

    provider: str
    sources: list[SourceListItem]


class SourceDebugResponse(BaseModel):
    """Debug payload for one uploaded source."""

    provider: str
    document_id: str
    name: str
    source_type: str
    source: str
    metadata: dict[str, object]
    markdown: str
    chunk_input: str
    chunk_input_type: str
    total_chunks: int
    chunks: list[SearchResult]


def _allowed_cors_origins() -> list[str]:
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    extra = os.getenv("CORS_ALLOW_ORIGINS", "")
    origins.extend(origin.strip().rstrip("/") for origin in extra.split(",") if origin.strip())
    return list(dict.fromkeys(origins))


api = FastAPI(title="Agentic RAG Generation API", lifespan=_api_lifespan)
api.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@api.middleware("http")
async def private_network_access(request: Request, call_next: Any) -> Any:
    """Handle Chrome Private Network Access preflight."""
    if request.method == "OPTIONS" and "access-control-request-private-network" in request.headers:
        from starlette.responses import Response as StarletteResponse

        origin = request.headers.get("origin", "*")
        return StarletteResponse(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Private-Network": "true",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Max-Age": "3600",
            },
        )
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


api.include_router(eval_review_router, prefix="/eval-review")
api.include_router(autodata_eval_router, prefix="/internal")


@api.get("/health")
def health() -> dict[str, str]:
    """Return API health and active configuration for the frontend."""

    provider_name = configured_evidence_provider_name()
    payload = {
        "status": "ok",
        "evidence_provider": provider_name,
    }
    if provider_name == "local_pdf":
        payload.update(local_pdf_backend_status())
    return payload


@api.post("/answer", response_model=Answer)
def answer_question(request: AnswerRequest) -> Answer:
    """Generate an answer grounded in retrieved evidence.

    Returns ``status="not_found"`` when no evidence is available rather than
    fabricating an answer.  Set ``use_mock_evidence=true`` only for local demos.
    """

    return _answer_for_request(request)


@api.post("/answer/stream")
def stream_answer_question(request: AnswerRequest) -> StreamingResponse:
    """Stream generated answer text and citations as server-sent events."""

    small_talk_answer = _small_talk_answer(request.question)
    if small_talk_answer is not None:
        return StreamingResponse(
            _stream_direct_answer_events(
                question=request.question,
                answer=small_talk_answer,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    if _agent_mode_enabled():
        provider = source_provider_from_env()
        result = run_agent(
            provider=provider,
            request=WorkflowRunInput(
                question=request.question,
                document_ids=request.document_ids,
                history=request.history or [],
            ),
        )
        return StreamingResponse(
            _stream_direct_answer_events(
                question=request.question,
                answer=result.answer,
                provider="agentic",
                evidence_chunks=result.evidence_chunks,
                generation_trace={
                    "queries_tried": result.queries_tried,
                    "agent_steps": result.steps,
                },
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    evidence_chunks, evidence_context = _evidence_for_request(request)
    provider_name = _provider_name(request)
    return StreamingResponse(
        _stream_answer_events(
            question=request.question,
            evidence_context=evidence_context,
            evidence_chunks=evidence_chunks,
            provider=provider_name,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@api.post("/sources/upload", response_model=SourceUploadResponse)
async def upload_source(file: UploadFile = UPLOAD_FILE) -> SourceUploadResponse:
    """Upload a real PDF/source file to RAGFlow and start parsing/chunking."""

    started_at = time.perf_counter()
    run_id = new_run_id()
    content = await file.read()
    try:
        provider_name = configured_evidence_provider_name()
        provider = source_provider_from_env()
        uploaded = provider.upload_document(
            filename=file.filename or "document.pdf",
            content=content,
            content_type=file.content_type,
        )
    except RAGFlowConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RAGFlowClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    provider_label = _source_provider_label(provider_name)
    write_source_trace(
        run_id=run_id,
        provider=provider_label,
        source_type="pdf",
        trace=uploaded.trace or {},
        latency_ms=_latency_ms(started_at),
    )
    return SourceUploadResponse(
        provider=provider_label,
        dataset_id=uploaded.dataset_id,
        document_id=uploaded.document_id,
        name=uploaded.name,
        parse_started=uploaded.parse_started,
        source_type="pdf",
        source=file.filename or uploaded.name,
    )


@api.post("/sources/url", response_model=SourceUploadResponse)
def upload_url_source(request: SourceUrlRequest) -> SourceUploadResponse:
    """Ingest one URL through the configured source provider."""

    url = _validated_http_url(request.url)
    if configured_evidence_provider_name() == "local_pdf":
        return _upload_local_url_document(url)

    try:
        html = _fetch_url_text(url)
    except (UrlHTTPError, URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"Cannot fetch URL: {exc}") from exc

    text = _html_to_text(html)
    if not text:
        raise HTTPException(status_code=422, detail="URL did not contain readable text.")

    filename = _filename_for_url(url)
    content = f"Source URL: {url}\n\n{text}".encode()
    return _upload_text_document(
        filename=filename,
        content=content,
        content_type="text/plain; charset=utf-8",
    )


@api.post("/sources/text", response_model=SourceUploadResponse)
def upload_text_source(request: SourceTextRequest) -> SourceUploadResponse:
    """Ingest raw user-provided text through the configured source provider."""

    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Text source cannot be empty.")

    title = request.title.strip() if request.title else "van-ban-nguoi-dung"
    if configured_evidence_provider_name() == "local_pdf":
        return _upload_local_text_document(title=title, text=text)

    filename = _safe_text_filename(title)
    return _upload_text_document(
        filename=filename,
        content=text.encode(),
        content_type="text/plain; charset=utf-8",
    )


@api.get("/sources", response_model=SourceListResponse)
def list_sources(
    include_chunks: bool = False,
) -> SourceListResponse:
    """Return persisted sources for frontend hydration after reload."""

    try:
        provider_name = configured_evidence_provider_name()
        provider = source_provider_from_env()
    except RAGFlowConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    provider_label = _source_provider_label(provider_name)
    if not isinstance(provider, LocalPdfEvidenceProvider):
        return SourceListResponse(provider=provider_label, sources=[])

    sources = [
        SourceListItem(
            provider=provider_label,
            dataset_id=document.dataset_id,
            document_id=document.document_id,
            name=document.name,
            source_type=document.source_type,
            source=document.source,
            total_chunks=document.total_chunks,
            chunks=(
                _search_results_for_chunks(document.chunks, provider_label)
                if include_chunks
                else []
            ),
            metadata=document.metadata,
        )
        for document in provider.list_documents(include_chunks=include_chunks)
    ]
    return SourceListResponse(provider=provider_label, sources=sources)


@api.get("/sources/{document_id}/chunks", response_model=SourceChunksResponse)
def source_chunks(document_id: str) -> SourceChunksResponse:
    """Return normalized chunks for one uploaded document."""

    try:
        provider_name = configured_evidence_provider_name()
        provider = source_provider_from_env()
    except RAGFlowConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    provider_label = _source_provider_label(provider_name)
    document_chunks = _document_chunks(provider, document_id)
    chunks = [
        SearchResult(chunk=chunk, score=1.0 / rank, rank=rank, retriever=provider_label)
        for rank, chunk in enumerate(
            document_chunks.chunks,
            start=1,
        )
    ]
    return SourceChunksResponse(
        provider=provider_label,
        document_id=document_id,
        total_chunks=document_chunks.total_chunks,
        chunks=chunks,
    )


@api.get("/sources/{document_id}/debug", response_model=SourceDebugResponse)
def source_debug(document_id: str) -> SourceDebugResponse:
    """Return source metadata, parsed Markdown, and chunks for debugging ingestion."""

    try:
        provider_name = configured_evidence_provider_name()
        provider = source_provider_from_env()
    except RAGFlowConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    provider_label = _source_provider_label(provider_name)
    if isinstance(provider, LocalPdfEvidenceProvider):
        try:
            debug = provider.document_debug(document_id=document_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        chunks = _search_results_for_chunks(debug.chunks, provider_label)
        return SourceDebugResponse(
            provider=provider_label,
            document_id=debug.document_id,
            name=debug.name,
            source_type=debug.source_type,
            source=debug.source,
            metadata=debug.metadata,
            markdown=debug.markdown,
            chunk_input=debug.chunk_input,
            chunk_input_type=debug.chunk_input_type,
            total_chunks=debug.total_chunks,
            chunks=chunks,
        )

    document_chunks = _document_chunks(provider, document_id)
    chunks = _search_results_for_chunks(document_chunks.chunks, provider_label)
    metadata = dict(document_chunks.chunks[0].metadata) if document_chunks.chunks else {}
    name = str(metadata.get("document_name") or metadata.get("file_name") or document_id)
    source_type = str(metadata.get("source_type") or provider_label)
    source = str(metadata.get("source") or metadata.get("url") or name)
    return SourceDebugResponse(
        provider=provider_label,
        document_id=document_id,
        name=name,
        source_type=source_type,
        source=source,
        metadata=metadata,
        markdown="",
        chunk_input="",
        chunk_input_type="unknown",
        total_chunks=document_chunks.total_chunks,
        chunks=chunks,
    )


@api.get("/sources/{document_id}/raw", response_model=None)
def source_raw(document_id: str) -> Response:
    """Return the original uploaded PDF file for local debug previews."""

    try:
        provider = source_provider_from_env()
    except RAGFlowConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not isinstance(provider, LocalPdfEvidenceProvider):
        raise HTTPException(
            status_code=404,
            detail="Raw source file is only available for local PDF sources.",
        )

    try:
        raw = provider.document_raw_content(document_id=document_id)
    except ValueError:
        raw = None
    if raw is not None:
        return Response(
            content=raw.content,
            media_type=raw.content_type,
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": _inline_content_disposition(raw.name),
            },
        )

    try:
        raw_path = provider.document_raw_path(document_id=document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        raw_path,
        media_type="application/pdf",
        headers={"Cache-Control": "no-store", "Content-Disposition": "inline"},
    )


def _inline_content_disposition(filename: str) -> str:
    encoded_filename = quote(filename)
    if encoded_filename != filename:
        return f"inline; filename*=utf-8''{encoded_filename}"
    return f'inline; filename="{filename}"'


@api.delete("/sources")
def delete_all_sources() -> dict[str, object]:
    """Delete all local source documents, chunks, files and vectors."""

    try:
        provider = source_provider_from_env()
    except RAGFlowConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not isinstance(provider, LocalPdfEvidenceProvider):
        raise HTTPException(
            status_code=404,
            detail="Delete all is only supported for local PDF sources.",
        )

    try:
        count = provider.delete_all_documents()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "deleted", "deleted_count": count}


@api.delete("/sources/{document_id}")
def delete_source(document_id: str) -> dict[str, str]:
    """Delete a local source document and all its chunks from storage and disk."""

    try:
        provider = source_provider_from_env()
    except RAGFlowConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not isinstance(provider, LocalPdfEvidenceProvider):
        raise HTTPException(
            status_code=404,
            detail="Delete is only supported for local PDF sources.",
        )

    try:
        provider.delete_document(document_id=document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"status": "deleted", "document_id": document_id}


def _search_results_for_chunks(chunks: list[Chunk], provider_label: str) -> list[SearchResult]:
    return [
        SearchResult(chunk=chunk, score=1.0 / rank, rank=rank, retriever=provider_label)
        for rank, chunk in enumerate(chunks, start=1)
    ]


def _document_chunks(
    provider: SourceEvidenceProvider,
    document_id: str,
) -> SourceDocumentChunks:
    try:
        return provider.document_chunks(document_id=document_id)
    except RAGFlowClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _source_provider_label(provider_name: str) -> str:
    return "local_pdf" if provider_name == "local_pdf" else "ragflow"


def _upload_text_document(
    *,
    filename: str,
    content: bytes,
    content_type: str,
) -> SourceUploadResponse:
    try:
        provider = ragflow_provider_from_env()
        uploaded = provider.upload_document(
            filename=filename,
            content=content,
            content_type=content_type,
        )
    except RAGFlowConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RAGFlowClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return SourceUploadResponse(
        provider="ragflow",
        dataset_id=uploaded.dataset_id,
        document_id=uploaded.document_id,
        name=uploaded.name,
        parse_started=uploaded.parse_started,
        source_type="text",
        source=filename,
    )


def _upload_local_url_document(url: str) -> SourceUploadResponse:
    started_at = time.perf_counter()
    run_id = new_run_id()
    try:
        provider = source_provider_from_env()
        if not isinstance(provider, LocalPdfEvidenceProvider):
            raise RuntimeError("Configured provider does not support local URL ingestion.")
        uploaded = provider.upload_url(url=url)
    except RAGFlowConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    write_source_trace(
        run_id=run_id,
        provider="local_pdf",
        source_type="url",
        trace=uploaded.trace or {},
        latency_ms=_latency_ms(started_at),
    )
    return SourceUploadResponse(
        provider="local_pdf",
        dataset_id=uploaded.dataset_id,
        document_id=uploaded.document_id,
        name=uploaded.name,
        parse_started=uploaded.parse_started,
        source_type="url",
        source=url,
    )


def _upload_local_text_document(*, title: str, text: str) -> SourceUploadResponse:
    started_at = time.perf_counter()
    run_id = new_run_id()
    try:
        provider = source_provider_from_env()
        if not isinstance(provider, LocalPdfEvidenceProvider):
            raise RuntimeError("Configured provider does not support local text ingestion.")
        uploaded = provider.upload_text(title=title, text=text)
    except RAGFlowConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    write_source_trace(
        run_id=run_id,
        provider="local_pdf",
        source_type="text",
        trace=uploaded.trace or {},
        latency_ms=_latency_ms(started_at),
    )
    return SourceUploadResponse(
        provider="local_pdf",
        dataset_id=uploaded.dataset_id,
        document_id=uploaded.document_id,
        name=uploaded.name,
        parse_started=uploaded.parse_started,
        source_type="text",
        source=title,
    )


def _answer_for_request(request: AnswerRequest) -> Answer:
    started_at = time.perf_counter()
    run_id = new_run_id()
    small_talk_answer = _small_talk_answer(request.question)
    if small_talk_answer is not None:
        write_rag_trace(
            run_id=run_id,
            provider="small_talk",
            question=request.question,
            evidence_chunks=[],
            evidence_context="",
            answer=small_talk_answer,
            latency_ms=_latency_ms(started_at),
        )
        return small_talk_answer

    if _agent_mode_enabled():
        provider = source_provider_from_env()
        result = run_agent(
            provider=provider,
            request=WorkflowRunInput(
                question=request.question,
                document_ids=request.document_ids,
                history=request.history or [],
            ),
        )
        write_rag_trace(
            run_id=run_id,
            provider="agentic",
            question=request.question,
            evidence_chunks=result.evidence_chunks,
            evidence_context=_build_evidence_context(result.evidence_chunks),
            answer=result.answer,
            latency_ms=_latency_ms(started_at),
            generation_trace={
                "queries_tried": result.queries_tried,
                "agent_steps": result.steps,
                "retrieve_count": len([s for s in result.steps if s.get("node") == "retrieve"]),
            },
        )
        return result.answer

    evidence_chunks, evidence_context = _evidence_for_request(request)
    generation = generate_answer_with_trace(
        question=request.question,
        evidence_context=evidence_context,
        evidence_chunks=evidence_chunks,
    )
    write_rag_trace(
        run_id=run_id,
        provider=_provider_name(request),
        question=request.question,
        evidence_chunks=evidence_chunks,
        evidence_context=evidence_context,
        answer=generation.answer,
        latency_ms=_latency_ms(started_at),
        generation_trace=generation.trace,
    )
    return generation.answer


def _agent_mode_enabled() -> bool:
    return os.getenv("AGENT_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}


def _small_talk_answer(question: str) -> Answer | None:
    normalized = _normalized_small_talk_text(question)
    if not normalized:
        return None

    greeting_phrases = {
        "alo",
        "chao",
        "chao ban",
        "hello",
        "hey",
        "hi",
        "xin chao",
        "xin chao ban",
    }
    thanks_phrases = {
        "cam on",
        "cam on ban",
        "ok cam on",
        "thanks",
        "thank you",
    }
    help_phrases = {
        "ban co the lam gi",
        "ban giup duoc gi",
        "ban la ai",
        "help",
        "huong dan",
        "tro giup",
    }

    if normalized in greeting_phrases:
        return Answer(
            answer=(
                "Xin chào! Bạn có thể tải tài liệu lên, chọn nguồn rồi đặt câu hỏi. "
                "Mình sẽ trả lời dựa trên tài liệu và kèm trích dẫn khi có bằng chứng."
            ),
            citations=[],
            status="answered",
        )

    if normalized in thanks_phrases:
        return Answer(
            answer="Rất vui được hỗ trợ. Khi cần, bạn cứ đặt câu hỏi về tài liệu đã chọn.",
            citations=[],
            status="answered",
        )

    if normalized in help_phrases:
        return Answer(
            answer=(
                "Mình là trợ lý hỏi đáp tài liệu. Bạn có thể tải PDF, nhập URL hoặc văn bản, "
                "sau đó hỏi về nội dung nguồn đã chọn để nhận câu trả lời có trích dẫn."
            ),
            citations=[],
            status="answered",
        )

    return None


def _normalized_small_talk_text(text: str) -> str:
    replacements = str.maketrans(
        {
            "à": "a",
            "á": "a",
            "ả": "a",
            "ã": "a",
            "ạ": "a",
            "ă": "a",
            "ằ": "a",
            "ắ": "a",
            "ẳ": "a",
            "ẵ": "a",
            "ặ": "a",
            "â": "a",
            "ầ": "a",
            "ấ": "a",
            "ẩ": "a",
            "ẫ": "a",
            "ậ": "a",
            "è": "e",
            "é": "e",
            "ẻ": "e",
            "ẽ": "e",
            "ẹ": "e",
            "ê": "e",
            "ề": "e",
            "ế": "e",
            "ể": "e",
            "ễ": "e",
            "ệ": "e",
            "ì": "i",
            "í": "i",
            "ỉ": "i",
            "ĩ": "i",
            "ị": "i",
            "ò": "o",
            "ó": "o",
            "ỏ": "o",
            "õ": "o",
            "ọ": "o",
            "ô": "o",
            "ồ": "o",
            "ố": "o",
            "ổ": "o",
            "ỗ": "o",
            "ộ": "o",
            "ơ": "o",
            "ờ": "o",
            "ớ": "o",
            "ở": "o",
            "ỡ": "o",
            "ợ": "o",
            "ù": "u",
            "ú": "u",
            "ủ": "u",
            "ũ": "u",
            "ụ": "u",
            "ư": "u",
            "ừ": "u",
            "ứ": "u",
            "ử": "u",
            "ữ": "u",
            "ự": "u",
            "ỳ": "y",
            "ý": "y",
            "ỷ": "y",
            "ỹ": "y",
            "ỵ": "y",
            "đ": "d",
        }
    )
    normalized = text.strip().lower().translate(replacements)
    normalized = re.sub(r"[^a-z0-9\s]+", " ", normalized)
    return _collapse_whitespace(normalized)


def _evidence_for_request(request: AnswerRequest) -> tuple[list[SearchResult], str]:
    resolved = evidence_for_question(
        EvidenceResolutionInput(
            question=request.question,
            evidence_context=request.evidence_context,
            evidence_chunks=request.evidence_chunks,
            provider=request.evidence_provider,
            document_ids=request.document_ids,
            use_mock_evidence=request.use_mock_evidence,
        )
    )
    return resolved.chunks, resolved.context


def _provider_name(request: AnswerRequest) -> str:
    return request.evidence_provider or configured_evidence_provider_name()


def _stream_answer_events(
    *,
    question: str,
    evidence_context: str,
    evidence_chunks: list[SearchResult],
    provider: str,
) -> Iterator[str]:
    started_at = time.perf_counter()
    run_id = new_run_id()
    for stream_event in stream_answer(
        question=question,
        evidence_context=evidence_context,
        evidence_chunks=evidence_chunks,
    ):
        if isinstance(stream_event, AnswerDelta):
            yield _sse_event("answer_delta", {"text": stream_event.text})
            continue

        if isinstance(stream_event, AnswerDone):
            answer = stream_event.answer
            for index, citation in enumerate(answer.citations, start=1):
                citation_payload = citation.model_dump()
                citation_payload["index"] = index
                yield _sse_event("citation", citation_payload)

            yield _sse_event(
                "done",
                {
                    **answer.model_dump(),
                    "evidence_chunks": [chunk.model_dump(mode="json") for chunk in evidence_chunks],
                },
            )
            write_rag_trace(
                run_id=run_id,
                provider=provider,
                question=question,
                evidence_chunks=evidence_chunks,
                evidence_context=evidence_context,
                answer=answer,
                latency_ms=_latency_ms(started_at),
                generation_trace=stream_event.trace,
            )


def _stream_direct_answer_events(
    *,
    question: str,
    answer: Answer,
    provider: str = "small_talk",
    evidence_chunks: list[SearchResult] | None = None,
    generation_trace: dict[str, object] | None = None,
) -> Iterator[str]:
    started_at = time.perf_counter()
    run_id = new_run_id()
    chunks = evidence_chunks or []
    yield _sse_event("answer_delta", {"text": answer.answer})
    yield _sse_event(
        "done",
        {
            **answer.model_dump(),
            "evidence_chunks": [chunk.model_dump(mode="json") for chunk in chunks],
        },
    )
    write_rag_trace(
        run_id=run_id,
        provider=provider,
        question=question,
        evidence_chunks=chunks,
        evidence_context=_build_evidence_context(chunks),
        answer=answer,
        latency_ms=_latency_ms(started_at),
        generation_trace=generation_trace,
    )


def _sse_event(event: str, data: dict[str, object]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _latency_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _validated_http_url(raw_url: str) -> str:
    url = raw_url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="URL must start with http:// or https://")
    return url


def _fetch_url_text(url: str) -> str:
    request = UrlRequest(
        url,
        headers={
            "User-Agent": "AgenticRAG/1.0 (+https://local.agentic-rag)",
            "Accept": "text/html,text/plain;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    with urlopen(request, timeout=20) as response:
        raw: bytes = response.read()
        content_type: str = response.headers.get_content_charset() or "utf-8"
    return raw.decode(content_type, errors="replace")


def _html_to_text(raw: str) -> str:
    parser = _ReadableHTMLParser()
    parser.feed(raw)
    text = parser.text()
    return text or _collapse_whitespace(raw)


def _filename_for_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.replace(":", "-")
    path = parsed.path.strip("/").replace("/", "-")
    stem = f"{host}-{path}" if path else host
    return _safe_text_filename(stem)


def _safe_text_filename(title: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", title.strip()).strip("-._")
    if not stem:
        stem = "source"
    return f"{stem[:96]}.txt"


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class _ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        if tag in {"p", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        stripped = _collapse_whitespace(data)
        if stripped:
            self._parts.append(stripped)
            self._parts.append(" ")

    def text(self) -> str:
        lines = [_collapse_whitespace(line) for line in "".join(self._parts).splitlines()]
        return "\n".join(line for line in lines if line)
