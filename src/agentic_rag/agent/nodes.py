"""LangGraph node functions for the Self-RAG pipeline."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from agentic_rag.agent.grading import (
    preprocess_query,
    transform_query,
)
from agentic_rag.agent.state import AgentState
from agentic_rag.core.contracts import SearchResult
from agentic_rag.core.ports import SourceEvidenceProvider
from agentic_rag.generation.answering import generate_answer_with_trace
from agentic_rag.generation.llm import configured_llm_client
from agentic_rag.retrieval.fusion import (
    build_evidence_context,
    rerank_with_metadata,
    rrf_fusion,
)


def _noop_traceable(*, name: str = "", run_type: str = "chain", **_: object) -> Any:
    def _noop(func: Any) -> Any:
        return func

    return _noop


try:
    from langsmith import traceable as _ls_traceable
except ImportError:
    _ls_traceable = _noop_traceable  # type: ignore[assignment]


AGENT_MAX_STEPS_ENV = "AGENT_MAX_STEPS"
AGENT_RERANK_FINAL_TOP_K_ENV = "AGENT_RERANK_FINAL_TOP_K"
AGENT_RETRIEVE_WORKERS_ENV = "AGENT_RETRIEVE_WORKERS"
_DEFAULT_MAX_STEPS = 3
_DEFAULT_RERANK_FINAL_TOP_K = 8
_DEFAULT_RETRIEVE_WORKERS = 3


# ---------------------------------------------------------------------------
# Traceable sub-functions
# ---------------------------------------------------------------------------


@_ls_traceable(name="rrf-fusion", run_type="tool")
def _fuse(
    bm25_results: list[SearchResult],
    dense_results: list[SearchResult],
) -> list[SearchResult]:
    return rrf_fusion(bm25_results, dense_results)


@_ls_traceable(name="retrieve-query", run_type="retriever")
def _retrieve_query(
    provider: SourceEvidenceProvider,
    query: str,
    document_ids: list[str] | None,
) -> list[SearchResult]:
    bm25, dense = _search_via_provider(provider, query, document_ids)
    if not dense:
        return bm25
    return _fuse(bm25, dense)


@_ls_traceable(name="retrieve-aggregate", run_type="tool")
def _trace_retrieve_aggregation(summary: dict[str, Any]) -> dict[str, Any]:
    return summary


@_ls_traceable(name="rerank", run_type="tool")
def _rerank(
    question: str,
    candidates: list[SearchResult],
    top_k: int = 5,
) -> tuple[list[SearchResult], dict[str, Any]]:
    return rerank_with_metadata(query=question, candidates=candidates, top_k=top_k)


@_ls_traceable(name="generate-answer", run_type="chain")
def _generate(
    question: str,
    evidence_context: str,
    evidence_chunks: list[SearchResult],
) -> Any:
    return generate_answer_with_trace(
        question=question,
        evidence_context=evidence_context,
        evidence_chunks=evidence_chunks,
    )


def _effective_question(state: AgentState) -> str:
    """Use the resolved question for history references, keep multi-intent broad."""
    rewritten = state.get("rewritten_question") or state["question"]
    if rewritten == state["question"]:
        return state["question"]

    for t in reversed(state.get("trace", [])):
        if t.get("node") == "preprocess":
            return rewritten if t.get("type") == "single" else state["question"]

    return rewritten


# ---------------------------------------------------------------------------
# LangGraph nodes
# ---------------------------------------------------------------------------


def preprocess_node(state: AgentState) -> dict[str, Any]:
    """Resolve history context and/or decompose multi-intent queries."""
    question = state["question"]
    history = state.get("history", [])
    llm_client = configured_llm_client()

    result = preprocess_query(question, history, llm_client)

    if result["type"] == "multi":
        questions: list[str] = result.get("questions", [question])
        if len(questions) > 1:
            return {
                "rewritten_question": questions[0],
                "queries_tried": [questions[0]],
                "pending_queries": questions[1:],
                "trace": [{"node": "preprocess", "type": "multi", "questions": questions}],
            }

    rewritten: str = result.get("question", question)
    extra = [rewritten] if rewritten != question else []
    return {
        "rewritten_question": rewritten,
        "queries_tried": extra,
        "trace": [{"node": "preprocess", "type": "single", "question": rewritten}],
    }


def make_retrieve_node(provider: SourceEvidenceProvider) -> Any:
    def retrieve_node(state: AgentState) -> dict[str, Any]:
        current_query = state["queries_tried"][-1] if state["queries_tried"] else state["question"]
        pending = state.get("pending_queries", [])
        queries_this_round = [current_query, *pending]

        document_ids = state.get("document_ids")
        new_fused: list[SearchResult] = []
        extra_tried: list[str] = []
        per_query: list[dict[str, Any]] = []
        worker_count = min(len(queries_this_round), _configured_retrieve_workers())
        query_results = _retrieve_queries_parallel(
            provider=provider,
            queries=queries_this_round,
            document_ids=document_ids,
            worker_count=worker_count,
        )

        for query_index, (query, results) in enumerate(
            zip(queries_this_round, query_results, strict=True)
        ):
            added_chunk_ids: list[str] = []
            for r in results:
                tagged = _with_retrieval_query_metadata(r, query, query_index)
                new_fused.append(tagged)
                if len(added_chunk_ids) < 10:
                    added_chunk_ids.append(r.chunk.chunk_id)
            if query != current_query:
                extra_tried.append(query)
            per_query.append(
                {
                    "query": query,
                    "returned_chunks": len(results),
                    "added_chunks": len(results),
                    "added_chunk_ids": added_chunk_ids,
                }
            )

        aggregate_trace = _trace_retrieve_aggregation(
            {
                "query_count": len(queries_this_round),
                "queries": queries_this_round,
                "parallel": len(queries_this_round) > 1,
                "worker_count": worker_count,
                "returned_chunks_total": sum(item["returned_chunks"] for item in per_query),
                "added_chunks_total": len(new_fused),
                "per_query": per_query,
            }
        )

        return {
            "fused_results": new_fused,
            "queries_tried": extra_tried,
            "pending_queries": [],
            "step_count": state.get("step_count", 0) + 1,
            "retrieval_exhausted": False,
            "trace": [{"node": "retrieve", **aggregate_trace}],
        }

    return retrieve_node


def rerank_node(state: AgentState) -> dict[str, Any]:
    """Rerank all accumulated docs via per-group cross-encoder."""
    raw_docs = state.get("fused_results", [])
    if not raw_docs:
        return {"relevant_docs": [], "trace": [{"node": "rerank", "total": 0, "kept": 0}]}

    query_groups = _group_by_retrieval_query(raw_docs)
    is_multi = len(query_groups) > 1
    top_k = 5 if is_multi else _configured_rerank_final_top_k()

    reranked, rerank_meta = _rerank_per_query_groups(query_groups, top_k_per_group=top_k)
    return {
        "relevant_docs": reranked,
        "trace": [
            {
                "node": "rerank",
                "total": len(raw_docs),
                "kept": len(reranked),
                "kept_chunk_ids": [r.chunk.chunk_id for r in reranked],
                **rerank_meta,
            }
        ],
    }


def transform_query_node(state: AgentState) -> dict[str, Any]:
    """Expand or requery — only runs when truly stuck (no chunks or not_found)."""
    llm_client = configured_llm_client()
    context_docs = state.get("relevant_docs") or _deduped(state.get("fused_results", []))
    effective_question = _effective_question(state)
    queries_tried = state.get("queries_tried", [])
    result = transform_query(
        question=effective_question,
        docs=context_docs,
        queries_tried=queries_tried,
        llm_client=llm_client,
    )

    method = result.get("method", "requery")
    trace_base = {
        "node": "transform_query",
        "method": method,
        "llm_result": result,
        "queries_tried_before": queries_tried,
        "context_doc_count": len(context_docs),
        "has_existing_answer": state.get("answer") is not None,
    }
    skip_next_route = "check_answer" if state.get("answer") is not None else "generate"

    if method == "decompose":
        queries = result.get("queries", [])
        if isinstance(queries, list) and len(queries) > 1:
            fresh = [q for q in queries if q not in queries_tried]
            if fresh:
                return {
                    "queries_tried": [fresh[0]],
                    "pending_queries": list(fresh[1:]),
                    "retrieval_exhausted": False,
                    "trace": [
                        {
                            **trace_base,
                            "queries": queries,
                            "fresh_queries": fresh,
                            "next_route_hint": "retrieve",
                        }
                    ],
                }
            return {
                "relevant_docs": context_docs,
                "retrieval_exhausted": True,
                "trace": [
                    {
                        **trace_base,
                        "skipped": True,
                        "reason": "no_fresh_decomposed_queries",
                        "queries": queries,
                        "next_route_hint": skip_next_route,
                    }
                ],
            }

    query = result.get("query", effective_question)
    if not isinstance(query, str):
        return {
            "relevant_docs": context_docs,
            "retrieval_exhausted": True,
            "trace": [
                {
                    **trace_base,
                    "skipped": True,
                    "reason": "invalid_query",
                    "next_route_hint": skip_next_route,
                }
            ],
        }

    if query in queries_tried:
        return {
            "relevant_docs": context_docs,
            "retrieval_exhausted": True,
            "trace": [
                {
                    **trace_base,
                    "skipped": True,
                    "reason": "query_already_tried",
                    "query": query,
                    "next_route_hint": skip_next_route,
                }
            ],
        }

    return {
        "queries_tried": [query],
        "pending_queries": [],
        "retrieval_exhausted": False,
        "trace": [{**trace_base, "query": query, "next_route_hint": "retrieve"}],
    }


def generate_node(state: AgentState) -> dict[str, Any]:
    """Generate grounded answer from already-reranked relevant_docs."""
    docs = state.get("relevant_docs") or _deduped(state.get("fused_results", []))
    evidence_context = build_evidence_context(docs)
    result = _generate(_effective_question(state), evidence_context, docs)

    return {
        "answer": result.answer,
        "relevant_docs": docs,
        "trace": [{"node": "generate", "answer_status": result.answer.status}],
    }


def check_answer_node(state: AgentState) -> dict[str, Any]:
    """Pass-through node: log answer status for trace observability."""
    answer = state.get("answer")
    if answer is None:
        return {"trace": [{"node": "check_answer", "skipped": True}]}
    return {"trace": [{"node": "check_answer", "status": answer.status}]}


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------


def route_after_rerank(state: AgentState) -> str:
    if state.get("relevant_docs"):
        return "generate"
    if state.get("step_count", 0) >= _configured_max_steps():
        return "generate"
    return "transform_query"


def route_after_transform(state: AgentState) -> str:
    for t in reversed(state.get("trace", [])):
        if t.get("node") == "transform_query":
            if not t.get("skipped"):
                return "retrieve"
            return "check_answer" if state.get("answer") is not None else "generate"
    return "retrieve"


def route_after_check(state: AgentState) -> str:
    """END if answered; transform if not_found and steps remain."""
    answer = state.get("answer")
    if (
        answer
        and answer.status == "not_found"
        and not state.get("retrieval_exhausted", False)
        and state.get("step_count", 0) < _configured_max_steps()
    ):
        return "transform_query"
    return "end"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _search_via_provider(
    provider: SourceEvidenceProvider,
    query: str,
    document_ids: list[str] | None,
) -> tuple[list[SearchResult], list[SearchResult]]:
    chunks = provider.retrieve(question=query, document_ids=document_ids)
    bm25 = [r for r in chunks if r.retriever == "bm25"]
    dense = [r for r in chunks if r.retriever == "dense"]
    if not bm25 and not dense:
        return chunks, []
    return bm25, dense


def _deduped(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    out: list[SearchResult] = []
    for r in results:
        if r.chunk.chunk_id not in seen:
            seen.add(r.chunk.chunk_id)
            out.append(r)
    return out


def _retrieve_queries_parallel(
    *,
    provider: SourceEvidenceProvider,
    queries: list[str],
    document_ids: list[str] | None,
    worker_count: int,
) -> list[list[SearchResult]]:
    if not queries:
        return []
    if worker_count <= 1 or len(queries) == 1:
        return [_retrieve_query(provider, query, document_ids) for query in queries]

    max_workers = min(worker_count, len(queries))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(
            executor.map(
                lambda query: _retrieve_query(provider, query, document_ids),
                queries,
            )
        )


_HEAVY_METADATA_KEYS = frozenset(
    {
        "pipeline_trace",
        "bm25",
        "dense",
        "rrf",
        "rrf_contributions",
        "preprocessed_query",
        "retrieval_pipeline",
    }
)


def _with_retrieval_query_metadata(
    result: SearchResult,
    query: str,
    query_index: int,
) -> SearchResult:
    # Strip provider-level debug fields — they're large and only needed at retrieval time.
    metadata = {k: v for k, v in result.chunk.metadata.items() if k not in _HEAVY_METADATA_KEYS}
    metadata["agent_retrieval_query"] = query
    metadata["agent_retrieval_query_index"] = query_index
    chunk = result.chunk.model_copy(update={"metadata": metadata})
    return result.model_copy(update={"chunk": chunk})


def _dedup_keep_best_score(results: list[SearchResult]) -> list[SearchResult]:
    """Dedup by chunk_id after per-group merge, preserving group order.

    Keeps the highest-scoring version of each chunk but places it at the position
    of its first occurrence — so context stays grouped: VF3 chunks, then VF5, then VF7.
    """
    best: dict[str, SearchResult] = {}
    for r in results:
        existing = best.get(r.chunk.chunk_id)
        if existing is None or r.score > existing.score:
            best[r.chunk.chunk_id] = r
    seen: set[str] = set()
    ordered: list[SearchResult] = []
    for r in results:
        if r.chunk.chunk_id not in seen:
            ordered.append(best[r.chunk.chunk_id])
            seen.add(r.chunk.chunk_id)
    return ordered


def _group_by_retrieval_query(
    results: list[SearchResult],
) -> dict[str, list[SearchResult]]:
    """Group candidates by the sub-query that retrieved them."""
    groups: dict[str, list[SearchResult]] = {}
    for result in results:
        query = result.chunk.metadata.get("agent_retrieval_query")
        key = query if isinstance(query, str) and query else "__unknown_query__"
        groups.setdefault(key, []).append(result)
    return groups


def _rerank_per_query_groups(
    query_groups: dict[str, list[SearchResult]],
    top_k_per_group: int = 5,
) -> tuple[list[SearchResult], dict[str, Any]]:
    """Rerank each query group with its own sub-query, then merge."""
    merged: list[SearchResult] = []
    group_traces: list[dict[str, Any]] = []

    for query, group_candidates in query_groups.items():
        if query == "__unknown_query__":
            top = sorted(group_candidates, key=lambda r: r.score, reverse=True)[:top_k_per_group]
            group_traces.append(
                {"query": query, "kept": len(top), "used_provider": "score_fallback"}
            )
        else:
            top, meta = _rerank(query, group_candidates, top_k=top_k_per_group)
            group_traces.append({"query": query, "kept": len(top), **meta})
        merged.extend(top)

    deduped = _dedup_keep_best_score(merged)
    renumbered = [
        SearchResult(chunk=r.chunk, score=r.score, rank=rank, retriever=r.retriever)
        for rank, r in enumerate(deduped, start=1)
    ]
    return renumbered, {
        "rerank_strategy": "per_query_group",
        "group_count": len(query_groups),
        "groups": group_traces,
        "merged_before_dedup": len(merged),
        "merged_after_dedup": len(deduped),
    }


def _configured_max_steps() -> int:
    raw = os.getenv(AGENT_MAX_STEPS_ENV)
    if raw is None:
        return _DEFAULT_MAX_STEPS
    try:
        v = int(raw)
        return v if v > 0 else _DEFAULT_MAX_STEPS
    except ValueError:
        return _DEFAULT_MAX_STEPS


def _configured_retrieve_workers() -> int:
    raw = os.getenv(AGENT_RETRIEVE_WORKERS_ENV)
    if raw is None:
        return _DEFAULT_RETRIEVE_WORKERS
    try:
        v = int(raw)
        return v if v > 0 else _DEFAULT_RETRIEVE_WORKERS
    except ValueError:
        return _DEFAULT_RETRIEVE_WORKERS


def _configured_rerank_final_top_k() -> int:
    raw = os.getenv(AGENT_RERANK_FINAL_TOP_K_ENV)
    if raw is None:
        return _DEFAULT_RERANK_FINAL_TOP_K
    try:
        v = int(raw)
        return v if v > 0 else _DEFAULT_RERANK_FINAL_TOP_K
    except ValueError:
        return _DEFAULT_RERANK_FINAL_TOP_K
