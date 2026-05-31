"""HTTP API for the generation/UI slice of the RAG demo."""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agentic_rag.core.contracts import Answer, SearchResult
from agentic_rag.generation.answering import (
    AnswerDelta,
    AnswerDone,
    format_evidence_context,
    generate_answer,
    stream_answer,
)
from agentic_rag.testing.fixtures import sample_search_results


class AnswerRequest(BaseModel):
    """Request body for the answer endpoint."""

    question: str = Field(min_length=1)
    evidence_context: str | None = None
    evidence_chunks: list[SearchResult] | None = None
    use_mock_evidence: bool = True


api = FastAPI(title="Agentic RAG Generation API")
api.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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
    return StreamingResponse(
        _stream_answer_events(
            question=request.question,
            evidence_context=evidence_context,
            evidence_chunks=evidence_chunks,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


def _answer_for_request(request: AnswerRequest) -> Answer:
    evidence_chunks, evidence_context = _evidence_for_request(request)
    return generate_answer(
        question=request.question,
        evidence_context=evidence_context,
        evidence_chunks=evidence_chunks,
    )


def _evidence_for_request(request: AnswerRequest) -> tuple[list[SearchResult], str]:
    evidence_chunks = request.evidence_chunks
    if evidence_chunks is None and request.use_mock_evidence:
        evidence_chunks = sample_search_results()
    if evidence_chunks is None:
        evidence_chunks = []

    evidence_context = request.evidence_context
    if evidence_context is None:
        evidence_context = format_evidence_context(evidence_chunks)

    return evidence_chunks, evidence_context


def _stream_answer_events(
    *,
    question: str,
    evidence_context: str,
    evidence_chunks: list[SearchResult],
) -> Iterator[str]:
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


def _sse_event(event: str, data: dict[str, object]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
