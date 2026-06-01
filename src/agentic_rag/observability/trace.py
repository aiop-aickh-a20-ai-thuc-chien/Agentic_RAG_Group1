"""Optional JSONL traces for RAG runs."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from agentic_rag.core.contracts import Answer, SearchResult
from agentic_rag.runtime_env import load_local_env


def trace_enabled() -> bool:
    """Return whether JSONL trace logging is enabled."""

    load_local_env()
    return os.getenv("RAG_TRACE_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def new_run_id() -> str:
    """Create a compact trace run id."""

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{uuid.uuid4().hex[:8]}"


def write_rag_trace(
    *,
    run_id: str,
    provider: str,
    question: str,
    evidence_chunks: list[SearchResult],
    evidence_context: str,
    answer: Answer,
    latency_ms: int,
) -> None:
    """Append one RAG run to the configured JSONL trace file."""

    if not trace_enabled():
        return

    load_local_env()
    path = Path(os.getenv("RAG_TRACE_PATH", "logs/rag_runs.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "run_id": run_id,
        "provider": provider,
        "inputs": {
            "question": question,
            "evidence_context_preview": _preview(evidence_context, 2000),
        },
        "retrieval": {
            "chunk_count": len(evidence_chunks),
            "evidence_chunk_ids": [result.chunk.chunk_id for result in evidence_chunks],
            "scores": [result.score for result in evidence_chunks],
            "chunks": [_trace_search_result(result) for result in evidence_chunks],
        },
        "generation": {
            "answer": answer.answer,
            "status": answer.status,
        },
        "citations": [citation.model_dump() for citation in answer.citations],
        "latency_ms": latency_ms,
    }
    with path.open("a", encoding="utf-8") as trace_file:
        trace_file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _trace_search_result(result: SearchResult) -> dict[str, Any]:
    chunk = result.chunk
    return {
        "rank": result.rank,
        "score": result.score,
        "retriever": result.retriever,
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
        "metadata": chunk.metadata,
    }


def _preview(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."
