"""Optional JSONL and LangSmith traces for RAG runs."""

from __future__ import annotations

import importlib
import json
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from agentic_rag.core.contracts import Answer, SearchResult
from agentic_rag.model_runtime.config import LLMProfileConfig, resolve_llm_profile
from agentic_rag.model_runtime.errors import ModelRuntimeConfigurationError
from agentic_rag.runtime_env import load_local_env

TRACE_PROVIDER_JSONL = "jsonl"
TRACE_PROVIDER_LANGSMITH = "langsmith"
TRACE_PROVIDER_BOTH = "both"

LANGSMITH_TRACE_MODE_CUSTOM = "custom"
LANGSMITH_TRACE_MODE_LANGGRAPH = "langgraph"


def trace_enabled() -> bool:
    """Return whether RAG trace logging is enabled."""

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
    generation_trace: dict[str, Any] | None = None,
) -> None:
    """Write one RAG run to the configured trace sink."""

    if not trace_enabled():
        return

    load_local_env()
    payload = build_rag_trace_payload(
        run_id=run_id,
        provider=provider,
        question=question,
        evidence_chunks=evidence_chunks,
        evidence_context=evidence_context,
        answer=answer,
        latency_ms=latency_ms,
        generation_trace=generation_trace,
    )

    trace_provider = configured_trace_provider()
    if trace_provider in {TRACE_PROVIDER_JSONL, TRACE_PROVIDER_BOTH}:
        _write_jsonl_trace(payload)
    if (
        trace_provider in {TRACE_PROVIDER_LANGSMITH, TRACE_PROVIDER_BOTH}
        and _langsmith_mode() != LANGSMITH_TRACE_MODE_LANGGRAPH
    ):
        _write_langsmith_trace(payload)


def write_source_trace(
    *,
    run_id: str,
    provider: str,
    source_type: str,
    trace: dict[str, object],
    latency_ms: int,
) -> None:
    """Write one source ingestion run to the configured trace sink."""

    if not trace_enabled():
        return

    load_local_env()
    payload = build_source_trace_payload(
        run_id=run_id,
        provider=provider,
        source_type=source_type,
        trace=trace,
        latency_ms=latency_ms,
    )

    trace_provider = configured_trace_provider()
    if trace_provider in {TRACE_PROVIDER_JSONL, TRACE_PROVIDER_BOTH}:
        _write_jsonl_trace(payload)
    if trace_provider in {TRACE_PROVIDER_LANGSMITH, TRACE_PROVIDER_BOTH}:
        _write_langsmith_trace(payload)


def configured_trace_provider() -> str:
    """Return the configured trace sink."""

    raw_provider = os.getenv("RAG_TRACE_PROVIDER", TRACE_PROVIDER_JSONL).strip().lower()
    if raw_provider in {TRACE_PROVIDER_LANGSMITH, TRACE_PROVIDER_BOTH}:
        return raw_provider
    return TRACE_PROVIDER_JSONL


def build_rag_trace_payload(
    *,
    run_id: str,
    provider: str,
    question: str,
    evidence_chunks: list[SearchResult],
    evidence_context: str,
    answer: Answer,
    latency_ms: int,
    generation_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a serializable RAG trace payload shared by JSONL and LangSmith."""

    return {
        "event_type": "rag_answer",
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
        "pipeline": {
            "trace": _trace_pipeline(evidence_chunks),
            "stages": _trace_pipeline_stages(evidence_chunks),
        },
        "generation": {
            "answer": answer.answer,
            "status": answer.status,
            "trace": generation_trace
            or _generation_trace(
                question=question,
                evidence_chunks=evidence_chunks,
                evidence_context=evidence_context,
                answer=answer,
                latency_ms=latency_ms,
            ),
        },
        "citations": [citation.model_dump() for citation in answer.citations],
        "latency_ms": latency_ms,
    }


def build_source_trace_payload(
    *,
    run_id: str,
    provider: str,
    source_type: str,
    trace: dict[str, object],
    latency_ms: int,
) -> dict[str, Any]:
    """Build a serializable source ingestion trace payload."""

    return {
        "event_type": "source_ingestion",
        "run_id": run_id,
        "provider": provider,
        "source_type": source_type,
        "source_upload": trace.get("source_upload", {}),
        "parse": trace.get("parse", {}),
        "chunking": trace.get("chunking", {}),
        "index_write": trace.get("index_write", {}),
        "latency_ms": latency_ms,
    }


def _write_jsonl_trace(payload: dict[str, Any]) -> None:
    path = Path(os.getenv("RAG_TRACE_PATH", "logs/rag_runs.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as trace_file:
        trace_file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_langsmith_trace(payload: dict[str, Any]) -> None:
    if not _langsmith_configured():
        return

    try:
        langsmith_module = importlib.import_module("langsmith")
        client_class = langsmith_module.Client
        client = client_class(
            api_key=os.getenv("LANGSMITH_API_KEY"),
            api_url=os.getenv("LANGSMITH_ENDPOINT") or None,
        )
        _emit_langsmith_runs(client=client, payload=payload)

        flush = getattr(client, "flush", None)
        if callable(flush):
            flush()

    except (
        ImportError,
        AttributeError,
        RuntimeError,
        OSError,
        TypeError,
        ValueError,
        Exception,
    ):
        return


def _emit_langsmith_runs(*, client: Any, payload: dict[str, Any]) -> None:
    if payload.get("event_type") == "source_ingestion":
        _emit_langsmith_source_ingestion(client=client, payload=payload)
        return

    project_name = os.getenv("LANGSMITH_PROJECT", "agentic-rag-group1")
    started_at = datetime.now(UTC)

    latency_ms = _rag_root_latency_ms(payload)
    root_end_time = started_at + timedelta(milliseconds=max(latency_ms, 150))

    root_run_id = _stable_run_uuid(str(payload["run_id"]))
    question = str(payload["inputs"]["question"])
    status = str(payload["generation"]["status"])

    client.create_run(
        id=root_run_id,
        project_name=project_name,
        name="rag-answer",
        run_type="chain",
        inputs={"question": question},
        outputs={
            "answer": payload["generation"]["answer"],
            "status": status,
            "citations": payload["citations"],
        },
        start_time=started_at,
        end_time=root_end_time,
        extra={
            "run_id": payload["run_id"],
            "provider": payload["provider"],
            "latency_ms": payload["latency_ms"],
        },
    )

    next_timestamp = _emit_langsmith_pipeline_stages(
        client=client,
        payload=payload,
        parent_run_id=root_run_id,
        project_name=project_name,
        timestamp=started_at + timedelta(milliseconds=10),
    )

    _emit_langsmith_retrieval(
        client=client,
        payload=payload,
        parent_run_id=root_run_id,
        project_name=project_name,
        timestamp=started_at + timedelta(milliseconds=10),
    )

    _emit_langsmith_generation(
        client=client,
        payload=payload,
        parent_run_id=root_run_id,
        project_name=project_name,
        timestamp=next_timestamp + timedelta(milliseconds=15),
    )

    _emit_langsmith_citations(
        client=client,
        payload=payload,
        parent_run_id=root_run_id,
        project_name=project_name,
        timestamp=root_end_time - timedelta(milliseconds=10),
    )


def _emit_langsmith_source_ingestion(*, client: Any, payload: dict[str, Any]) -> None:
    project_name = os.getenv("LANGSMITH_PROJECT", "agentic-rag-group1")
    timestamp = datetime.now(UTC)
    latency_ms = _source_root_latency_ms(payload)
    root_run_id = _stable_run_uuid(str(payload["run_id"]))

    client.create_run(
        id=root_run_id,
        project_name=project_name,
        name="source-ingestion",
        run_type="chain",
        inputs=_as_langsmith_outputs(payload["source_upload"]),
        outputs={
            "parse": payload["parse"],
            "chunking": payload["chunking"],
            "index_write": payload["index_write"],
        },
        start_time=timestamp,
        end_time=timestamp + timedelta(milliseconds=max(latency_ms, 100)),
        extra={
            "run_id": payload["run_id"],
            "provider": payload["provider"],
            "source_type": payload["source_type"],
            "latency_ms": payload["latency_ms"],
        },
    )

    next_timestamp = _emit_langsmith_source_stage(
        client=client,
        payload=payload,
        parent_run_id=root_run_id,
        project_name=project_name,
        timestamp=timestamp + timedelta(milliseconds=10),
        name="parse-document",
        stage_key="parse",
    )

    next_timestamp = _emit_langsmith_source_stage(
        client=client,
        payload=payload,
        parent_run_id=root_run_id,
        project_name=project_name,
        timestamp=next_timestamp + timedelta(milliseconds=5),
        name="chunk-document",
        stage_key="chunking",
    )

    _emit_langsmith_source_stage(
        client=client,
        payload=payload,
        parent_run_id=root_run_id,
        project_name=project_name,
        timestamp=next_timestamp + timedelta(milliseconds=5),
        name="write-local-index",
        stage_key="index_write",
    )


def _emit_langsmith_source_stage(
    *,
    client: Any,
    payload: dict[str, Any],
    parent_run_id: uuid.UUID,
    project_name: str,
    timestamp: datetime,
    name: str,
    stage_key: str,
) -> datetime:
    stage_output = _as_langsmith_outputs(payload.get(stage_key))
    stage_latency_ms = _source_stage_latency_ms(payload.get(stage_key))

    client.create_run(
        id=_stable_run_uuid(f"{payload['run_id']}:{stage_key}"),
        project_name=project_name,
        parent_run_id=parent_run_id,
        name=name,
        run_type="tool",
        inputs=_as_langsmith_outputs(payload.get("source_upload")),
        outputs=stage_output,
        start_time=timestamp,
        end_time=timestamp + timedelta(milliseconds=max(stage_latency_ms, 1)),
        extra={"stage": stage_key, "latency_ms": stage_latency_ms},
    )
    return timestamp + timedelta(milliseconds=max(stage_latency_ms, 1))


def _emit_langsmith_retrieval(
    *,
    client: Any,
    payload: dict[str, Any],
    parent_run_id: uuid.UUID,
    project_name: str,
    timestamp: datetime,
) -> None:
    retrieval = payload["retrieval"]
    latency_ms = max(_pipeline_latency_ms(payload), 5)

    client.create_run(
        id=_stable_run_uuid(f"{payload['run_id']}:retrieval"),
        project_name=project_name,
        parent_run_id=parent_run_id,
        name="retrieve-evidence",
        run_type="retriever",
        inputs={"question": payload["inputs"]["question"]},
        outputs={"chunks": retrieval["chunks"]},
        start_time=timestamp,
        end_time=timestamp + timedelta(milliseconds=latency_ms),
        extra={
            "provider": payload["provider"],
            "chunk_count": retrieval["chunk_count"],
            "scores": retrieval["scores"],
            "latency_ms": latency_ms,
        },
    )


def _emit_langsmith_pipeline_stages(
    *,
    client: Any,
    payload: dict[str, Any],
    parent_run_id: uuid.UUID,
    project_name: str,
    timestamp: datetime,
) -> datetime:
    pipeline_trace = payload.get("pipeline", {}).get("trace")
    if not isinstance(pipeline_trace, dict):
        return timestamp

    next_timestamp = timestamp
    for name, stage_key, run_type in [
        ("query-preprocess", "preprocess_query", "tool"),
        ("bm25-search", "bm25_search", "retriever"),
        ("dense-search", "dense_search", "retriever"),
        ("rrf-fusion", "rrf_fusion", "tool"),
        ("rerank", "rerank", "tool"),
    ]:
        next_timestamp = _emit_langsmith_pipeline_stage(
            client=client,
            payload=payload,
            parent_run_id=parent_run_id,
            project_name=project_name,
            timestamp=next_timestamp,
            name=name,
            stage_key=stage_key,
            stage_payload=pipeline_trace.get(stage_key),
            run_type=run_type,
        ) + timedelta(milliseconds=2)
    return next_timestamp


def _emit_langsmith_pipeline_stage(
    *,
    client: Any,
    payload: dict[str, Any],
    parent_run_id: uuid.UUID,
    project_name: str,
    timestamp: datetime,
    name: str,
    stage_key: str,
    stage_payload: object,
    run_type: str,
) -> datetime:
    if stage_payload is None:
        return timestamp

    stage_inputs: object = {"question": payload["inputs"]["question"]}
    stage_outputs: object = stage_payload
    stage_extra: dict[str, Any] = {"stage": stage_key}
    stage_latency_ms = 5
    if isinstance(stage_payload, dict):
        stage_inputs = stage_payload.get("input", stage_inputs)
        stage_outputs = stage_payload.get("output", stage_outputs)
        stage_latency_ms = _stage_latency_ms(stage_payload)
        tech = stage_payload.get("tech")
        if tech is not None:
            stage_extra["tech"] = tech
        stage_extra["latency_ms"] = stage_latency_ms

    client.create_run(
        id=_stable_run_uuid(f"{payload['run_id']}:{stage_key}"),
        project_name=project_name,
        parent_run_id=parent_run_id,
        name=name,
        run_type=run_type,
        inputs=_as_langsmith_outputs(stage_inputs),
        outputs=_as_langsmith_outputs(stage_outputs),
        start_time=timestamp,
        end_time=timestamp + timedelta(milliseconds=max(stage_latency_ms, 1)),
        extra=stage_extra,
    )
    return timestamp + timedelta(milliseconds=max(stage_latency_ms, 1))


def _emit_langsmith_generation(
    *,
    client: Any,
    payload: dict[str, Any],
    parent_run_id: uuid.UUID,
    project_name: str,
    timestamp: datetime,
) -> None:
    generation = payload["generation"]
    generation_trace = generation.get("trace")
    if not isinstance(generation_trace, dict):
        generation_trace = {}
    latency_ms = _generation_latency_ms(payload)
    stage_timestamp = timestamp

    client.create_run(
        id=_stable_run_uuid(f"{payload['run_id']}:generation"),
        project_name=project_name,
        parent_run_id=parent_run_id,
        name="generate-grounded-answer",
        run_type="chain",
        inputs={
            "question": payload["inputs"]["question"],
            "evidence_context_preview": payload["inputs"]["evidence_context_preview"],
        },
        outputs={"answer": generation["answer"]},
        start_time=timestamp,
        end_time=timestamp + timedelta(milliseconds=max(latency_ms, 1)),
        extra={
            "model": _configured_generation_model(),
            "status": generation["status"],
            "latency_ms": latency_ms,
        },
    )

    for name, stage_key, run_type in [
        ("build-grounded-prompt", "prompt_build", "tool"),
        ("llm-call", "llm_call", "llm"),
        ("answer-parse", "answer_parse", "tool"),
        ("guardrail-decision", "guardrail_decision", "tool"),
    ]:
        stage_timestamp = _emit_langsmith_generation_stage(
            client=client,
            payload=payload,
            parent_run_id=_stable_run_uuid(f"{payload['run_id']}:generation"),
            project_name=project_name,
            timestamp=stage_timestamp,
            name=name,
            stage_key=stage_key,
            stage_payload=generation_trace.get(stage_key),
            run_type=run_type,
        ) + timedelta(milliseconds=2)


def _emit_langsmith_citations(
    *,
    client: Any,
    payload: dict[str, Any],
    parent_run_id: uuid.UUID,
    project_name: str,
    timestamp: datetime,
) -> None:
    generation_trace = payload.get("generation", {}).get("trace")
    citation_trace: object = None
    if isinstance(generation_trace, dict):
        citation_trace = generation_trace.get("citation_validation")
    citation_inputs: object = {"citations": payload["citations"]}
    citation_outputs: object = {"citations": payload["citations"]}
    citation_latency_ms = 5
    if isinstance(citation_trace, dict):
        citation_inputs = citation_trace.get("input", citation_inputs)
        citation_outputs = citation_trace.get("output", citation_outputs)
        citation_latency_ms = _stage_latency_ms(citation_trace)

    client.create_run(
        id=_stable_run_uuid(f"{payload['run_id']}:citations"),
        project_name=project_name,
        parent_run_id=parent_run_id,
        name="citation-validation",
        run_type="tool",
        inputs=_as_langsmith_outputs(citation_inputs),
        outputs=_as_langsmith_outputs(citation_outputs),
        start_time=timestamp,
        end_time=timestamp + timedelta(milliseconds=max(citation_latency_ms, 1)),
        extra={
            "citation_count": len(payload["citations"]),
            "latency_ms": citation_latency_ms,
        },
    )


def _emit_langsmith_generation_stage(
    *,
    client: Any,
    payload: dict[str, Any],
    parent_run_id: uuid.UUID,
    project_name: str,
    timestamp: datetime,
    name: str,
    stage_key: str,
    stage_payload: object,
    run_type: str,
) -> datetime:
    if stage_payload is None:
        return timestamp

    stage_inputs: object = {}
    stage_outputs: object = stage_payload
    stage_extra: dict[str, Any] = {"stage": stage_key}
    stage_latency_ms = 5
    if isinstance(stage_payload, dict):
        stage_inputs = stage_payload.get("input", stage_inputs)
        stage_outputs = stage_payload.get("output", stage_outputs)
        stage_latency_ms = _stage_latency_ms(stage_payload)
        tech = stage_payload.get("tech")
        if tech is not None:
            stage_extra["tech"] = tech
        stage_extra["latency_ms"] = stage_latency_ms

    client.create_run(
        id=_stable_run_uuid(f"{payload['run_id']}:{stage_key}"),
        project_name=project_name,
        parent_run_id=parent_run_id,
        name=name,
        run_type=run_type,
        inputs=_as_langsmith_outputs(stage_inputs),
        outputs=_as_langsmith_outputs(stage_outputs),
        start_time=timestamp,
        end_time=timestamp + timedelta(milliseconds=max(stage_latency_ms, 1)),
        extra=stage_extra,
    )
    return timestamp + timedelta(milliseconds=max(stage_latency_ms, 1))


def _as_langsmith_outputs(value: Any) -> dict[str, Any]:
    """LangSmith create_run expects inputs/outputs to be dict-like objects."""

    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"results": value}
    return {"output": value}


def _stage_latency_ms(stage_payload: dict[str, Any]) -> int:
    latency = stage_payload.get("latency_ms")
    if isinstance(latency, bool):
        return 5
    if isinstance(latency, int | float):
        return max(int(latency), 0)
    return 5


def _source_stage_latency_ms(stage_payload: object) -> int:
    if not isinstance(stage_payload, dict):
        return 5
    return _stage_latency_ms(stage_payload)


def _source_root_latency_ms(payload: dict[str, Any]) -> int:
    latency_ms = _coerce_latency_ms(payload.get("latency_ms"), default=100)
    stage_total = sum(
        _source_stage_latency_ms(payload.get(stage_key))
        for stage_key in ("parse", "chunking", "index_write")
    )
    return max(latency_ms, stage_total + 20, 100)


def _rag_root_latency_ms(payload: dict[str, Any]) -> int:
    latency_ms = _coerce_latency_ms(payload.get("latency_ms"), default=150)
    pipeline_total = _pipeline_latency_ms(payload)
    return max(latency_ms, pipeline_total + _generation_latency_ms(payload) + 40, 150)


def _pipeline_latency_ms(payload: dict[str, Any]) -> int:
    pipeline_trace = payload.get("pipeline", {}).get("trace")
    if not isinstance(pipeline_trace, dict):
        return 0
    return sum(
        _source_stage_latency_ms(pipeline_trace.get(stage_key))
        for stage_key in (
            "preprocess_query",
            "bm25_search",
            "dense_search",
            "rrf_fusion",
            "rerank",
        )
    )


def _generation_latency_ms(payload: dict[str, Any]) -> int:
    latency_ms = _coerce_latency_ms(payload.get("latency_ms"), default=20)
    pipeline_total = _pipeline_latency_ms(payload)
    if pipeline_total:
        return max(latency_ms - pipeline_total, 20)
    return max(latency_ms, 20)


def _coerce_latency_ms(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return max(int(value), 0)
    return default


def _langsmith_configured() -> bool:
    return bool(os.getenv("LANGSMITH_API_KEY"))


def _langsmith_mode() -> str:
    """Return configured LangSmith trace mode: 'langgraph' or 'custom' (default)."""
    raw = os.getenv("LANGSMITH_TRACE_MODE", LANGSMITH_TRACE_MODE_CUSTOM).strip().lower()
    if raw == LANGSMITH_TRACE_MODE_LANGGRAPH:
        return LANGSMITH_TRACE_MODE_LANGGRAPH
    return LANGSMITH_TRACE_MODE_CUSTOM


def _configured_generation_model() -> str:
    return _generation_profile().model or ""


def _stable_run_uuid(value: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, value)


def _trace_search_result(result: SearchResult) -> dict[str, Any]:
    chunk = result.chunk
    return {
        "rank": result.rank,
        "score": result.score,
        "retriever": result.retriever,
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
        "metadata": (
            chunk.metadata.model_dump() if hasattr(chunk.metadata, "model_dump") else chunk.metadata
        ),
    }


def _trace_pipeline(results: list[SearchResult]) -> object:
    for result in results:
        pipeline_trace = result.chunk.metadata.get("pipeline_trace")
        if pipeline_trace is not None:
            return pipeline_trace
    return None


def _trace_pipeline_stages(results: list[SearchResult]) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    for result in results:
        metadata = result.chunk.metadata
        stages.append(
            {
                "chunk_id": result.chunk.chunk_id,
                "pipeline": metadata.get("retrieval_pipeline"),
                "preprocessed_query": metadata.get("preprocessed_query"),
                "bm25": metadata.get("bm25"),
                "dense": metadata.get("dense"),
                "dense_error": metadata.get("dense_error"),
                "rrf": metadata.get("rrf"),
                "final": metadata.get("final"),
            }
        )
    return stages


def _generation_trace(
    *,
    question: str,
    evidence_chunks: list[SearchResult],
    evidence_context: str,
    answer: Answer,
    latency_ms: int,
) -> dict[str, Any]:
    evidence_ids = [result.chunk.chunk_id for result in evidence_chunks]
    generation_latency = max(latency_ms - _metadata_pipeline_latency_ms(evidence_chunks), 0)
    llm_latency_ms = max(generation_latency - 10, 1)
    citations = [citation.model_dump() for citation in answer.citations]
    return {
        "prompt_build": {
            "tech": {
                "prompt": "grounded_evidence_prompt",
                "citation_style": "inline_numeric_markers",
            },
            "latency_ms": 1,
            "input": {
                "question": question,
                "evidence_chunk_ids": evidence_ids,
                "evidence_context_chars": len(evidence_context),
            },
            "output": {
                "evidence_context_preview": _preview(evidence_context, 2000),
                "instruction_summary": [
                    "answer in same language with the user's question",
                    "use only evidence context",
                    "do not invent facts or citations",
                    "place citation markers next to supported claims",
                    "return not_found when evidence is insufficient",
                ],
            },
        },
        "llm_call": {
            "tech": {
                "provider": _configured_llm_provider(),
                "model": _configured_generation_model(),
                "temperature": 0,
                "streaming": False,
            },
            "latency_ms": llm_latency_ms,
            "input": {
                "prompt_preview": _preview(evidence_context, 2000),
                "question": question,
            },
            "output": {
                "answer_preview": _preview(answer.answer, 2000),
                "status": answer.status,
            },
        },
        "answer_parse": {
            "tech": {
                "steps": [
                    "strip trailing reference list",
                    "detect not_found response",
                    "derive citations from final evidence chunks",
                    "attach inline citation markers",
                ],
            },
            "latency_ms": 5,
            "input": {
                "raw_answer_preview": _preview(answer.answer, 2000),
                "evidence_chunk_ids": evidence_ids,
            },
            "output": {
                "answer": answer.answer,
                "status": answer.status,
                "citation_count": len(answer.citations),
            },
        },
        "guardrail_decision": {
            "tech": {
                "method": "question/evidence/citation grounded boundary checks",
            },
            "latency_ms": 1,
            "input": {
                "has_question": bool(question.strip()),
                "evidence_count": len(evidence_chunks),
                "evidence_context_chars": len(evidence_context),
            },
            "output": {
                "status": answer.status,
                "reason": "answered_with_valid_citations"
                if answer.status == "answered"
                else "not_found",
            },
        },
        "citation_validation": {
            "tech": {
                "method": "validate citation source/page/section/url against retrieved chunks",
            },
            "latency_ms": 5,
            "input": {
                "citations": citations,
                "evidence_chunk_ids": evidence_ids,
            },
            "output": {
                "valid": _citation_trace_valid(answer=answer, evidence_chunks=evidence_chunks),
                "citations": citations,
            },
        },
    }


def _metadata_pipeline_latency_ms(results: list[SearchResult]) -> int:
    pipeline_trace = _trace_pipeline(results)
    if not isinstance(pipeline_trace, dict):
        return 0
    return sum(
        _source_stage_latency_ms(pipeline_trace.get(stage_key))
        for stage_key in (
            "preprocess_query",
            "bm25_search",
            "dense_search",
            "rrf_fusion",
            "rerank",
        )
    )


def _citation_trace_valid(*, answer: Answer, evidence_chunks: list[SearchResult]) -> bool:
    if answer.status == "not_found":
        return not answer.citations
    evidence_chunk_ids = {result.chunk.chunk_id for result in evidence_chunks}
    return bool(answer.citations) and all(
        citation.chunk_id in evidence_chunk_ids for citation in answer.citations
    )


def _configured_llm_provider() -> str:
    return _generation_profile().provider


def _generation_profile() -> LLMProfileConfig:
    try:
        return resolve_llm_profile("generation")
    except ModelRuntimeConfigurationError:
        return LLMProfileConfig(role="generation", provider="invalid", model=None)


def _preview(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."
