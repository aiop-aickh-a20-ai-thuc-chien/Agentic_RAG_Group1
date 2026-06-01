"""HTTP API for the generation/UI slice of the RAG demo."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agentic_rag.core.contracts import Answer, Chunk, SearchResult
from agentic_rag.generation.answering import (
    AnswerDelta,
    AnswerDone,
    generate_answer,
    stream_answer,
)
from agentic_rag.generation.evidence import (
    EvidenceProviderName,
    configured_evidence_provider_name,
    evidence_for_question,
    ragflow_provider_from_env,
)
from agentic_rag.integrations.ragflow.client import RAGFlowClientError
from agentic_rag.integrations.ragflow.config import RAGFlowConfigurationError
from agentic_rag.integrations.ragflow.providers import RAGFlowEvidenceProvider
from agentic_rag.observability.trace import new_run_id, write_rag_trace
from agentic_rag.runtime_env import load_local_env

load_local_env()

UPLOAD_FILE = File(...)


class AnswerRequest(BaseModel):
    """Request body for the answer endpoint."""

    question: str = Field(min_length=1)
    evidence_context: str | None = None
    evidence_chunks: list[SearchResult] | None = None
    evidence_provider: EvidenceProviderName | None = None
    document_ids: list[str] | None = None
    use_mock_evidence: bool = True


class SourceUploadResponse(BaseModel):
    """Response for a document uploaded through the configured evidence provider."""

    provider: str
    dataset_id: str
    document_id: str
    name: str
    parse_started: bool


class SourceChunksResponse(BaseModel):
    """Normalized chunks for one uploaded source."""

    provider: str
    document_id: str
    chunks: list[SearchResult]


api = FastAPI(title="Agentic RAG Generation API")
api.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@api.get("/health")
def health() -> dict[str, str]:
    """Return API health for the frontend."""

    return {"status": "ok"}


@api.post("/answer", response_model=Answer)
def answer_question(request: AnswerRequest) -> Answer:
    """Generate an answer using provided evidence or mock evidence."""

    return _answer_for_request(request)


@api.post("/answer/stream")
def stream_answer_question(request: AnswerRequest) -> StreamingResponse:
    """Stream generated answer text and citations as server-sent events."""

    evidence_chunks, evidence_context = _evidence_for_request(request)
    provider = _provider_name(request)
    return StreamingResponse(
        _stream_answer_events(
            question=request.question,
            evidence_context=evidence_context,
            evidence_chunks=evidence_chunks,
            provider=provider,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@api.post("/sources/upload", response_model=SourceUploadResponse)
async def upload_source(file: UploadFile = UPLOAD_FILE) -> SourceUploadResponse:
    """Upload a real PDF/source file to RAGFlow and start parsing/chunking."""

    content = await file.read()
    try:
        provider = ragflow_provider_from_env()
        uploaded = provider.upload_document(
            filename=file.filename or "document.pdf",
            content=content,
            content_type=file.content_type,
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
    )


@api.get("/sources/{document_id}/chunks", response_model=SourceChunksResponse)
def source_chunks(document_id: str) -> SourceChunksResponse:
    """Return normalized RAGFlow chunks for one uploaded document."""

    try:
        provider = ragflow_provider_from_env()
    except RAGFlowConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    chunks = [
        SearchResult(chunk=chunk, score=1.0 / rank, rank=rank, retriever="ragflow")
        for rank, chunk in enumerate(
            _list_document_chunks(provider, document_id),
            start=1,
        )
    ]
    return SourceChunksResponse(provider="ragflow", document_id=document_id, chunks=chunks)


def _list_document_chunks(
    provider: RAGFlowEvidenceProvider,
    document_id: str,
) -> list[Chunk]:
    try:
        return provider.list_document_chunks(document_id=document_id)
    except RAGFlowClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _answer_for_request(request: AnswerRequest) -> Answer:
    started_at = time.perf_counter()
    run_id = new_run_id()
    evidence_chunks, evidence_context = _evidence_for_request(request)
    answer = generate_answer(
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
        answer=answer,
        latency_ms=_latency_ms(started_at),
    )
    return answer


def _evidence_for_request(request: AnswerRequest) -> tuple[list[SearchResult], str]:
    return evidence_for_question(
        question=request.question,
        evidence_context=request.evidence_context,
        evidence_chunks=request.evidence_chunks,
        provider=request.evidence_provider,
        document_ids=request.document_ids,
        use_mock_evidence=request.use_mock_evidence,
    )


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

            yield _sse_event("done", answer.model_dump())
            write_rag_trace(
                run_id=run_id,
                provider=provider,
                question=question,
                evidence_chunks=evidence_chunks,
                evidence_context=evidence_context,
                answer=answer,
                latency_ms=_latency_ms(started_at),
            )


def _sse_event(event: str, data: dict[str, object]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _latency_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)
