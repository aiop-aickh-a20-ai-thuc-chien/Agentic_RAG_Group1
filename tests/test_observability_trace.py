from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pytest import MonkeyPatch

from agentic_rag.core.contracts import Answer, Chunk, Citation, SearchResult
from agentic_rag.observability.trace import (
    build_rag_trace_payload,
    build_source_trace_payload,
    configured_trace_provider,
    write_rag_trace,
    write_source_trace,
)


def test_build_rag_trace_payload_includes_chunks_and_citations() -> None:
    chunk = Chunk(
        chunk_id="c1",
        text="Pin VF8 duoc bao hanh 8 nam.",
        metadata={
            "source": "vinfast.pdf",
            "page": 12,
            "retrieval_pipeline": "pdf_ingestion -> bm25 + dense -> rrf -> rerank",
            "bm25": {"rank": 1, "score": 1.2, "retriever": "bm25"},
            "dense": {"rank": 2, "score": 0.8, "retriever": "dense"},
            "dense_error": None,
            "rrf": {"rank": 1, "score": 0.03, "retriever": "hybrid"},
            "final": {"rank": 1, "score": 0.03, "retriever": "rerank"},
            "pipeline_trace": {
                "preprocess_query": {
                    "tech": {"method": "normalize"},
                    "latency_ms": 2,
                    "input": {"query": "Bao hanh pin?"},
                    "output": {"normalized": "bao hanh pin"},
                },
                "bm25_search": {
                    "tech": {"library": "rank-bm25"},
                    "latency_ms": 3,
                    "input": {"query": "bao hanh pin"},
                    "output": [{"chunk_id": "c1", "rank": 1}],
                },
                "dense_search": {
                    "tech": {"model": "text-embedding-3-small"},
                    "latency_ms": 4,
                    "input": {"query": "bao hanh pin"},
                    "output": {"results": [{"chunk_id": "c1", "rank": 1}], "error": None},
                },
                "rrf_fusion": {
                    "tech": {"method": "reciprocal_rank_fusion"},
                    "latency_ms": 5,
                    "input": {"bm25_results": [{"chunk_id": "c1", "rank": 1}]},
                    "output": [{"chunk_id": "c1", "rank": 1}],
                },
                "rerank": {
                    "tech": {"provider": "score"},
                    "latency_ms": 6,
                    "input": {"candidates": [{"chunk_id": "c1", "rank": 1}]},
                    "output": [{"chunk_id": "c1", "rank": 1}],
                },
            },
        },
    )
    result = SearchResult(chunk=chunk, score=0.9, rank=1, retriever="bm25")
    answer = Answer(
        answer="Pin VF8 duoc bao hanh 8 nam. [1]",
        status="answered",
        citations=[Citation(source="vinfast.pdf", page=12, chunk_id="c1")],
    )

    payload = build_rag_trace_payload(
        run_id="run_1",
        provider="local_pdf",
        question="Bao hanh pin VF8 bao lau?",
        evidence_chunks=[result],
        evidence_context="context",
        answer=answer,
        latency_ms=42,
    )

    assert payload["run_id"] == "run_1"
    assert payload["provider"] == "local_pdf"
    assert payload["retrieval"]["chunk_count"] == 1
    assert payload["retrieval"]["chunks"][0]["metadata"]["page"] == 12
    assert payload["pipeline"]["trace"]["preprocess_query"]["output"]["normalized"] == (
        "bao hanh pin"
    )
    assert payload["pipeline"]["trace"]["bm25_search"]["output"][0]["chunk_id"] == "c1"
    assert payload["pipeline"]["stages"][0]["bm25"]["retriever"] == "bm25"
    assert payload["pipeline"]["stages"][0]["dense_error"] is None
    assert payload["pipeline"]["stages"][0]["rrf"]["retriever"] == "hybrid"
    assert payload["generation"]["trace"]["prompt_build"]["input"]["question"] == (
        "Bao hanh pin VF8 bao lau?"
    )
    assert payload["generation"]["trace"]["llm_call"]["output"]["status"] == "answered"
    assert payload["generation"]["trace"]["answer_parse"]["output"]["citation_count"] == 1
    assert payload["generation"]["trace"]["guardrail_decision"]["output"]["status"] == "answered"
    assert payload["generation"]["trace"]["citation_validation"]["output"]["valid"] is True
    assert payload["citations"][0]["chunk_id"] == "c1"


def test_write_rag_trace_jsonl(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    trace_path = tmp_path / "rag_runs.jsonl"
    monkeypatch.setenv("RAG_TRACE_ENABLED", "true")
    monkeypatch.setenv("RAG_TRACE_PROVIDER", "jsonl")
    monkeypatch.setenv("RAG_TRACE_PATH", str(trace_path))

    write_rag_trace(
        run_id="run_jsonl",
        provider="mock",
        question="xin chao",
        evidence_chunks=[],
        evidence_context="",
        answer=Answer(answer="Xin chao!", status="answered"),
        latency_ms=7,
    )

    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run_jsonl"
    assert payload["generation"]["answer"] == "Xin chao!"


def test_build_source_trace_payload_includes_upload_parse_chunking_and_index() -> None:
    payload = build_source_trace_payload(
        run_id="source_1",
        provider="local_pdf",
        source_type="pdf",
        trace={
            "source_upload": {
                "filename": "warranty.pdf",
                "size_bytes": 123,
            },
            "parse": {
                "parser": "docling",
                "latency_ms": 10,
            },
            "chunking": {
                "chunk_count": 2,
                "chunks": [{"chunk_id": "c1", "text": "A"}],
            },
            "index_write": {
                "type": "jsonl",
                "path": "storage/local_pdf/chunks/doc.jsonl",
            },
        },
        latency_ms=20,
    )

    assert payload["event_type"] == "source_ingestion"
    assert payload["source_upload"]["filename"] == "warranty.pdf"
    assert payload["parse"]["parser"] == "docling"
    assert payload["chunking"]["chunk_count"] == 2
    assert payload["index_write"]["type"] == "jsonl"


def test_write_source_trace_jsonl(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    trace_path = tmp_path / "rag_runs.jsonl"
    monkeypatch.setenv("RAG_TRACE_ENABLED", "true")
    monkeypatch.setenv("RAG_TRACE_PROVIDER", "jsonl")
    monkeypatch.setenv("RAG_TRACE_PATH", str(trace_path))

    write_source_trace(
        run_id="source_jsonl",
        provider="local_pdf",
        source_type="pdf",
        trace={"source_upload": {"filename": "document.pdf"}},
        latency_ms=5,
    )

    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "source_jsonl"
    assert payload["event_type"] == "source_ingestion"
    assert payload["source_upload"]["filename"] == "document.pdf"


def test_configured_trace_provider_defaults_to_jsonl(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_TRACE_PROVIDER", "unknown")

    assert configured_trace_provider() == "jsonl"


def test_write_rag_trace_langsmith_exporter(monkeypatch: MonkeyPatch) -> None:
    fake_client = _FakeLangSmithClient()
    fake_module = _FakeLangSmithModule(fake_client)

    def fake_import_module(name: str) -> object:
        assert name == "langsmith"
        return fake_module

    monkeypatch.setenv("RAG_TRACE_ENABLED", "true")
    monkeypatch.setenv("RAG_TRACE_PROVIDER", "langsmith")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2-test")
    monkeypatch.setenv("LANGSMITH_PROJECT", "agentic-rag-test")
    monkeypatch.setattr(
        "agentic_rag.observability.trace.importlib.import_module",
        fake_import_module,
    )
    chunk = Chunk(
        chunk_id="c1",
        text="Tai lieu noi ve bao hanh.",
        metadata={
            "pipeline_trace": {
                "preprocess_query": {
                    "tech": {"method": "normalize"},
                    "latency_ms": 2,
                    "input": {"query": "Tai lieu noi gi?"},
                    "output": {"normalized": "tai lieu noi gi"},
                },
                "bm25_search": {
                    "tech": {"library": "rank-bm25"},
                    "latency_ms": 3,
                    "input": {"query": "tai lieu noi gi"},
                    "output": [{"chunk_id": "c1", "rank": 1}],
                },
                "dense_search": {
                    "tech": {"model": "text-embedding-3-small"},
                    "latency_ms": 4,
                    "input": {"query": "tai lieu noi gi"},
                    "output": {"results": [], "error": "missing key"},
                },
                "rrf_fusion": {
                    "tech": {"method": "reciprocal_rank_fusion"},
                    "latency_ms": 5,
                    "input": {
                        "bm25_results": [{"chunk_id": "c1", "rank": 1}],
                        "dense_results": [],
                    },
                    "output": [{"chunk_id": "c1", "rank": 1}],
                },
                "rerank": {
                    "tech": {"provider": "score"},
                    "latency_ms": 6,
                    "input": {"candidates": [{"chunk_id": "c1", "rank": 1}]},
                    "output": [{"chunk_id": "c1", "rank": 1}],
                },
            }
        },
    )

    write_rag_trace(
        run_id="run_langsmith",
        provider="local_pdf",
        question="Tai lieu noi gi?",
        evidence_chunks=[SearchResult(chunk=chunk, score=0.1, rank=1, retriever="rerank")],
        evidence_context="",
        answer=Answer(answer="Chua co bang chung.", status="not_found"),
        latency_ms=10,
    )

    assert fake_client.flushed is True
    assert [run["name"] for run in fake_client.runs] == [
        "rag-answer",
        "query-preprocess",
        "bm25-search",
        "dense-search",
        "rrf-fusion",
        "rerank",
        "retrieve-evidence",
        "generate-grounded-answer",
        "build-grounded-prompt",
        "llm-call",
        "answer-parse",
        "guardrail-decision",
        "citation-validation",
    ]
    assert fake_client.runs[0]["project_name"] == "agentic-rag-test"
    assert fake_client.runs[0]["extra"]["run_id"] == "run_langsmith"
    bm25_run = next(run for run in fake_client.runs if run["name"] == "bm25-search")
    dense_run = next(run for run in fake_client.runs if run["name"] == "dense-search")
    rrf_run = next(run for run in fake_client.runs if run["name"] == "rrf-fusion")
    rerank_run = next(run for run in fake_client.runs if run["name"] == "rerank")
    llm_run = next(run for run in fake_client.runs if run["name"] == "llm-call")
    citation_run = next(run for run in fake_client.runs if run["name"] == "citation-validation")
    guardrail_run = next(run for run in fake_client.runs if run["name"] == "guardrail-decision")
    assert bm25_run["inputs"]["query"] == "tai lieu noi gi"
    assert bm25_run["outputs"]["results"][0]["chunk_id"] == "c1"
    assert bm25_run["extra"]["latency_ms"] == 3
    assert dense_run["extra"]["tech"]["model"] == "text-embedding-3-small"
    assert dense_run["outputs"]["error"] == "missing key"
    assert rrf_run["inputs"]["bm25_results"][0]["chunk_id"] == "c1"
    assert rerank_run["inputs"]["candidates"][0]["chunk_id"] == "c1"
    assert llm_run["extra"]["tech"]["model"] == "gpt-4o-mini"
    assert guardrail_run["outputs"]["status"] == "not_found"
    assert citation_run["outputs"]["valid"] is True


def test_write_source_trace_langsmith_exporter(monkeypatch: MonkeyPatch) -> None:
    fake_client = _FakeLangSmithClient()
    fake_module = _FakeLangSmithModule(fake_client)

    def fake_import_module(name: str) -> object:
        assert name == "langsmith"
        return fake_module

    monkeypatch.setenv("RAG_TRACE_ENABLED", "true")
    monkeypatch.setenv("RAG_TRACE_PROVIDER", "langsmith")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2-test")
    monkeypatch.setenv("LANGSMITH_PROJECT", "agentic-rag-test")
    monkeypatch.setattr(
        "agentic_rag.observability.trace.importlib.import_module",
        fake_import_module,
    )

    write_source_trace(
        run_id="source_langsmith",
        provider="local_pdf",
        source_type="pdf",
        trace={
            "source_upload": {"filename": "document.pdf"},
            "parse": {"parser": "docling"},
            "chunking": {"chunk_count": 1},
            "index_write": {"type": "jsonl"},
        },
        latency_ms=30,
    )

    assert fake_client.flushed is True
    assert [run["name"] for run in fake_client.runs] == [
        "source-ingestion",
        "parse-document",
        "chunk-document",
        "write-local-index",
    ]
    assert fake_client.runs[0]["extra"]["run_id"] == "source_langsmith"


class _FakeLangSmithModule:
    def __init__(self, client: _FakeLangSmithClient) -> None:
        self._client = client

    def Client(self, **_kwargs: Any) -> _FakeLangSmithClient:
        return self._client


class _FakeLangSmithClient:
    def __init__(self) -> None:
        self.runs: list[dict[str, Any]] = []
        self.flushed = False

    def create_run(self, **kwargs: Any) -> None:
        self.runs.append(kwargs)

    def flush(self) -> None:
        self.flushed = True
