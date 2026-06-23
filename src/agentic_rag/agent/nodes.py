"""LangGraph node functions for the Self-RAG pipeline."""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from agentic_rag.agent.clarification import (
    build_clarification_question,
    build_pending_clarification,
    detect_entities,
    detect_intents,
    resolve_clarification_reply,
    should_clarify,
)
from agentic_rag.agent.grading import (
    preprocess_query,
    transform_query,
)
from agentic_rag.agent.node_contracts import (
    CheckAnswerNodeOutput,
    ClarifyQuestionNodeOutput,
    GenerateNodeOutput,
    PreprocessNodeOutput,
    RerankNodeOutput,
    RetrieveNodeOutput,
    TransformQueryNodeOutput,
)
from agentic_rag.agent.state import AgentState
from agentic_rag.core.contracts import Answer, RetrievalInput, SearchResult
from agentic_rag.core.ports import SourceEvidenceProvider
from agentic_rag.generation.answering import generate_answer_with_trace
from agentic_rag.ingestion.metadata import filter_coverage
from agentic_rag.ingestion.metadata.entity_normalizer import detect_in_query
from agentic_rag.language import detect_language
from agentic_rag.model_runtime.factory import get_llm_client
from agentic_rag.retrieval.boosting import apply_metadata_boost
from agentic_rag.retrieval.fusion import (
    build_evidence_context,
    rerank_with_metadata,
    rrf_fusion,
)
from agentic_rag.retrieval.search import _entity_prefilter_for


def _noop_traceable(*, name: str = "", run_type: str = "chain", **_: object) -> Any:
    def _noop(func: Any) -> Any:
        return func

    return _noop


try:
    from langsmith import traceable as _ls_traceable
except ImportError:
    _ls_traceable = _noop_traceable  # type: ignore[assignment]


AGENT_MAX_STEPS_ENV = "AGENT_MAX_STEPS"
AGENT_MIN_RELEVANCE_SCORE_ENV = "AGENT_MIN_RELEVANCE_SCORE"
AGENT_MIN_CHUNKS_PER_ENTITY_ENV = "AGENT_MIN_CHUNKS_PER_ENTITY"
AGENT_RERANK_FINAL_TOP_K_ENV = "AGENT_RERANK_FINAL_TOP_K"
AGENT_RERANK_MULTI_TOP_K_ENV = "AGENT_RERANK_MULTI_TOP_K"
AGENT_RETRIEVE_WORKERS_ENV = "AGENT_RETRIEVE_WORKERS"
_DEFAULT_MAX_STEPS = 3
_DEFAULT_MIN_RELEVANCE_SCORE = 0.0
_DEFAULT_MIN_CHUNKS_PER_ENTITY = 2
_DEFAULT_RERANK_FINAL_TOP_K = 8
_DEFAULT_RERANK_MULTI_TOP_K = 5
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
    exclude_dedup_layers: list[str] | None = None,
    entity_filter: list[str] | None = None,
    boost_query_type: str | None = None,
) -> list[SearchResult]:
    bm25, dense = _search_via_provider(
        provider, query, document_ids, exclude_dedup_layers, entity_filter
    )
    fused = bm25 if not dense else _fuse(bm25, dense)
    return apply_metadata_boost(fused, query_type=boost_query_type)


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
    original_question: str | None = None,
    history: list[dict[str, str]] | None = None,
    lang: str = "vi",
) -> Any:
    return generate_answer_with_trace(
        question=question,
        evidence_context=evidence_context,
        evidence_chunks=evidence_chunks,
        original_question=original_question,
        history=history,
        lang=lang,
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


def preprocess_node(state: AgentState) -> PreprocessNodeOutput:
    """Resolve history context and/or decompose multi-intent queries.

    When the previous bot turn was a clarification question, the rule-based
    resolver in clarification.py is tried first as a cheap fast-path.  The
    LLM-based preprocess_query then handles any remaining rewrites.
    """
    question = state["question"]
    history = state.get("history", [])

    # Detect language once here; all downstream nodes read from state
    lang = detect_language(question, history)

    # Fast-path: rule-based resolution of clarification replies (no LLM → full detect)
    resolved_by_rules = resolve_clarification_reply(question, history, lang=lang)
    if resolved_by_rules is not None:
        extra = [resolved_by_rules] if resolved_by_rules != question else []
        entities = _entity_prefilter_for(resolved_by_rules) or []
        return PreprocessNodeOutput(
            rewritten_question=resolved_by_rules,
            queries_tried=extra,
            detected_language=lang,
            filter_entities=entities,
            filter_entities_map={resolved_by_rules: entities},
            boost_query_type="unknown",
            trace=[
                {
                    "node": "preprocess",
                    "type": "clarification_resolved",
                    "original": question,
                    "resolved": resolved_by_rules,
                    "detected_language": lang,
                }
            ],
        )

    llm_client = get_llm_client("query_rewrite")
    result = preprocess_query(question, history, llm_client)
    boost_query_type = result.get("query_type", "unknown")

    if result["type"] == "multi":
        questions: list[str] = result.get("questions", [question])
        if len(questions) > 1:
            # LLM already extracted per-query entities in preprocess_query.
            # Fall back to dict detect per sub-query if the LLM omitted the field.
            llm_ents: list[list[str]] = result.get("entities") or []
            filter_entities_map = {
                q: (llm_ents[i] if i < len(llm_ents) else detect_in_query(q))
                for i, q in enumerate(questions)
            }
            all_entities = sorted({e for ents in filter_entities_map.values() for e in ents})
            return PreprocessNodeOutput(
                rewritten_question=questions[0],
                queries_tried=[questions[0]],
                pending_queries=questions[1:],
                detected_language=lang,
                filter_entities=all_entities,
                filter_entities_map=filter_entities_map,
                boost_query_type=boost_query_type,
                trace=[
                    {
                        "node": "preprocess",
                        "type": "multi",
                        "questions": questions,
                        "filter_entities_map": filter_entities_map,
                        "detected_language": lang,
                    }
                ],
            )

    rewritten: str = result.get("question", question)
    extra = [rewritten] if rewritten != question else []
    # LLM already extracted entities in the same call; fall back to full detect
    # (dict + optional LLM) if the field was omitted or empty.
    entities = result.get("entities") or _entity_prefilter_for(rewritten) or []
    return PreprocessNodeOutput(
        rewritten_question=rewritten,
        queries_tried=extra,
        detected_language=lang,
        filter_entities=entities,
        filter_entities_map={rewritten: entities},
        boost_query_type=boost_query_type,
        trace=[
            {
                "node": "preprocess",
                "type": "single",
                "question": rewritten,
                "detected_language": lang,
            }
        ],
    )


def make_retrieve_node(
    provider: SourceEvidenceProvider,
) -> Callable[[AgentState], RetrieveNodeOutput]:
    def retrieve_node(state: AgentState) -> RetrieveNodeOutput:
        current_query = state["queries_tried"][-1] if state["queries_tried"] else state["question"]
        pending = state.get("pending_queries", [])
        queries_this_round = [current_query, *pending]

        document_ids = state.get("document_ids")
        exclude_dedup_layers = state.get("exclude_dedup_layers") or None
        # Per-query entity filters from preprocess_node. Decomposed queries each
        # get their own focused filter; fall back to the union list for queries
        # added later by transform_query_node (not in the map).
        filter_map = state.get("filter_entities_map") or {}
        global_filter = state.get("filter_entities") or []
        entity_filters = [filter_map.get(q, global_filter) for q in queries_this_round]

        new_fused: list[SearchResult] = []
        extra_tried: list[str] = []
        per_query: list[dict[str, Any]] = []
        worker_count = min(len(queries_this_round), _configured_retrieve_workers())
        boost_query_type = state.get("boost_query_type")
        query_results = _retrieve_queries_parallel(
            provider=provider,
            queries=queries_this_round,
            document_ids=document_ids,
            worker_count=worker_count,
            exclude_dedup_layers=exclude_dedup_layers,
            entity_filters=entity_filters,
            boost_query_type=boost_query_type,
        )
        for query_index, (query, results, entity_filter) in enumerate(
            zip(queries_this_round, query_results, entity_filters, strict=True)
        ):
            coverage = filter_coverage(entity_filter)
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
                    "entity_filter": entity_filter,
                    "candidate_chunks": coverage,
                    "candidate_chunks_total": sum(coverage.values()),
                    "returned_chunks": len(results),
                    "added_chunks": len(results),
                    "added_chunk_ids": added_chunk_ids,
                }
            )

        # per_query carries the entity_filter used + the resulting chunk count,
        # so the retrieve node trace shows the pre-filter's effect directly.
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

        return RetrieveNodeOutput(
            fused_results=new_fused,
            queries_tried=extra_tried,
            pending_queries=[],
            step_count=state.get("step_count", 0) + 1,
            retrieval_exhausted=False,
            trace=[{"node": "retrieve", **aggregate_trace}],
        )

    return retrieve_node


def rerank_node(state: AgentState) -> RerankNodeOutput:
    """Rerank all accumulated docs via per-group cross-encoder."""
    raw_docs = state.get("fused_results", [])
    if not raw_docs:
        return RerankNodeOutput(
            relevant_docs=[],
            pinned_docs=[],
            missing_entities=[],
            rejected_chunk_ids=[],
            trace=[{"node": "rerank", "total": 0, "kept": 0}],
        )

    rejected = set(state.get("rejected_chunk_ids") or [])
    filtered_docs = [d for d in raw_docs if d.chunk.chunk_id not in rejected]
    if not filtered_docs:
        filtered_docs = raw_docs

    query_groups = _group_by_retrieval_query(filtered_docs)
    is_multi = len(query_groups) > 1
    top_k = _configured_rerank_multi_top_k() if is_multi else _configured_rerank_final_top_k()
    min_chunks = _configured_min_chunks_per_entity()

    reranked, rerank_meta = _rerank_per_query_groups(query_groups, top_k_per_group=top_k)

    pinned: list[SearchResult] = []
    missing_entities: list[str] = []
    if is_multi:
        for group_trace in rerank_meta.get("groups", []):
            query = group_trace.get("query", "")
            kept = group_trace.get("kept", 0)
            if not query or query == "__unknown_query__":
                continue
            group_docs = [
                r for r in reranked if r.chunk.metadata.get("agent_retrieval_query") == query
            ]
            if group_docs:
                pinned.extend(group_docs)
            if kept < min_chunks:
                missing_entities.append(query)

    reranked_ids = {r.chunk.chunk_id for r in reranked}
    new_rejected = [d.chunk.chunk_id for d in filtered_docs if d.chunk.chunk_id not in reranked_ids]

    return RerankNodeOutput(
        relevant_docs=reranked,
        pinned_docs=pinned,
        missing_entities=missing_entities,
        rejected_chunk_ids=new_rejected,
        trace=[
            {
                "node": "rerank",
                "total": len(raw_docs),
                "filtered": len(filtered_docs),
                "kept": len(reranked),
                "rejected_this_round": len(new_rejected),
                "kept_chunk_ids": [r.chunk.chunk_id for r in reranked],
                "missing_entities": missing_entities,
                **rerank_meta,
            }
        ],
    )


def transform_query_node(state: AgentState) -> TransformQueryNodeOutput:
    """Expand or requery — only runs when truly stuck (no chunks or not_found)."""
    llm_client = get_llm_client("query_transform")
    context_docs = state.get("relevant_docs") or _deduped(state.get("fused_results", []))
    effective_question = _effective_question(state)
    queries_tried = state.get("queries_tried", [])
    missing_entities = state.get("missing_entities") or []
    result = transform_query(
        question=effective_question,
        docs=context_docs,
        queries_tried=queries_tried,
        missing_entities=missing_entities,
        llm_client=llm_client,
        lang=state.get("detected_language", "vi"),
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
                return TransformQueryNodeOutput(
                    rewritten_question=fresh[0],
                    queries_tried=[fresh[0]],
                    pending_queries=list(fresh[1:]),
                    retrieval_exhausted=False,
                    trace=[
                        {
                            **trace_base,
                            "queries": queries,
                            "fresh_queries": fresh,
                            "next_route_hint": "retrieve",
                        }
                    ],
                )
            return TransformQueryNodeOutput(
                relevant_docs=context_docs,
                retrieval_exhausted=True,
                trace=[
                    {
                        **trace_base,
                        "skipped": True,
                        "reason": "no_fresh_decomposed_queries",
                        "queries": queries,
                        "next_route_hint": skip_next_route,
                    }
                ],
            )

    query = result.get("query", effective_question)
    if not isinstance(query, str):
        return TransformQueryNodeOutput(
            relevant_docs=context_docs,
            retrieval_exhausted=True,
            trace=[
                {
                    **trace_base,
                    "skipped": True,
                    "reason": "invalid_query",
                    "next_route_hint": skip_next_route,
                }
            ],
        )

    if query in queries_tried:
        return TransformQueryNodeOutput(
            relevant_docs=context_docs,
            retrieval_exhausted=True,
            trace=[
                {
                    **trace_base,
                    "skipped": True,
                    "reason": "query_already_tried",
                    "query": query,
                    "next_route_hint": skip_next_route,
                }
            ],
        )

    return TransformQueryNodeOutput(
        rewritten_question=query,
        queries_tried=[query],
        pending_queries=[],
        retrieval_exhausted=False,
        trace=[{**trace_base, "query": query, "next_route_hint": "retrieve"}],
    )


def generate_node(state: AgentState) -> GenerateNodeOutput:
    """Generate grounded answer from reranked docs + pinned docs from previous loops."""
    relevant = state.get("relevant_docs") or _deduped(state.get("fused_results", []))
    pinned = state.get("pinned_docs") or []

    docs = sorted(
        _dedup_keep_best_score(pinned + relevant),
        key=lambda r: r.score,
        reverse=True,
    )

    evidence_context = build_evidence_context(docs)
    result = _generate(
        _effective_question(state),
        evidence_context,
        docs,
        original_question=state["question"],
        history=state.get("history", []),
        lang=state.get("detected_language", "vi"),
    )

    return GenerateNodeOutput(
        answer=result.answer,
        relevant_docs=docs,
        trace=[
            {
                "node": "generate",
                "answer_status": result.answer.status,
                "pinned_count": len(pinned),
                "docs_used": len(docs),
            }
        ],
    )


def check_answer_node(state: AgentState) -> CheckAnswerNodeOutput:
    """Pass-through node: log answer status for trace observability."""
    answer = state.get("answer")
    if answer is None:
        return CheckAnswerNodeOutput(trace=[{"node": "check_answer", "skipped": True}])
    return CheckAnswerNodeOutput(trace=[{"node": "check_answer", "status": answer.status}])


def clarify_question_node(state: AgentState) -> ClarifyQuestionNodeOutput:
    """Detect underspecified queries and ask for clarification before retrieval.

    Uses the resolved question (after preprocess rewrites) as the signal.
    If the question is clear enough, returns ``needs_clarification=False`` and
    the graph proceeds normally to retrieve.  If not, returns an Answer with
    ``status="clarification_needed"`` and the graph routes to END.
    """
    question = state.get("rewritten_question") or state["question"]
    history = state.get("history", [])
    lang = state.get("detected_language", "vi")

    entities = detect_entities(question)
    intents = detect_intents(question)
    needs_clarification, reason = should_clarify(question, history)

    if not needs_clarification:
        return ClarifyQuestionNodeOutput(
            needs_clarification=False,
            detected_entities=entities,
            detected_intents=intents,
            trace=[
                {
                    "node": "clarify_question",
                    "needs_clarification": False,
                    "entities": entities,
                    "intents": intents,
                }
            ],
        )

    clarification_q = build_clarification_question(reason, entities, intents, lang=lang)
    pending = build_pending_clarification(reason, entities, intents)

    return ClarifyQuestionNodeOutput(
        needs_clarification=True,
        clarification_reason=reason,
        clarification_question=clarification_q,
        detected_entities=entities,
        detected_intents=intents,
        pending_clarification=pending,
        answer=Answer(
            answer=clarification_q,
            status="clarification_needed",
            citations=[],
        ),
        trace=[
            {
                "node": "clarify_question",
                "needs_clarification": True,
                "reason": reason,
                "entities": entities,
                "intents": intents,
                "clarification_question": clarification_q,
            }
        ],
    )


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------


def route_after_clarification(state: AgentState) -> str:
    """Route to END (return clarification question) or continue to retrieve."""
    if state.get("needs_clarification") and not state.get("single_turn"):
        return "end"
    return "retrieve"


def route_after_rerank(state: AgentState) -> str:
    docs = state.get("relevant_docs") or []
    missing = state.get("missing_entities") or []

    if state.get("step_count", 0) >= _configured_max_steps():
        return "generate"

    if missing:
        return "transform_query"

    if docs and _docs_meet_threshold(docs):
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
    exclude_dedup_layers: list[str] | None = None,
    entity_filter: list[str] | None = None,
) -> tuple[list[SearchResult], list[SearchResult]]:
    chunks = provider.retrieve(
        RetrievalInput(
            question=query,
            document_ids=document_ids,
            exclude_dedup_layers=exclude_dedup_layers or [],
            entity_filter=entity_filter or [],
        )
    ).results
    dense = [r for r in chunks if r.retriever == "dense"]
    # Everything that is not dense (bm25, question-index, qdrant "hybrid") goes in
    # the first bucket so it survives fusion — previously results tagged
    # "question"/"hybrid" were silently dropped here, killing the question-index
    # retriever on the agent path.
    non_dense = [r for r in chunks if r.retriever != "dense"]
    if not non_dense and not dense:
        return chunks, []
    return non_dense, dense


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
    exclude_dedup_layers: list[str] | None = None,
    entity_filters: list[list[str]] | None = None,
    boost_query_type: str | None = None,
) -> list[list[SearchResult]]:
    if not queries:
        return []
    _filters: list[list[str]] = entity_filters or [[] for _ in queries]
    if worker_count <= 1 or len(queries) == 1:
        return [
            _retrieve_query(provider, q, document_ids, exclude_dedup_layers, f, boost_query_type)
            for q, f in zip(queries, _filters, strict=True)
        ]

    max_workers = min(worker_count, len(queries))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(
            executor.map(
                lambda qf: _retrieve_query(
                    provider, qf[0], document_ids, exclude_dedup_layers, qf[1], boost_query_type
                ),
                zip(queries, _filters, strict=True),
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


def _docs_meet_threshold(docs: list[SearchResult]) -> bool:
    threshold = _configured_min_relevance_score()
    if threshold <= 0.0:
        return True
    return any(r.score >= threshold for r in docs)


def _configured_max_steps() -> int:
    raw = os.getenv(AGENT_MAX_STEPS_ENV)
    if raw is None:
        return _DEFAULT_MAX_STEPS
    try:
        v = int(raw)
        return v if v > 0 else _DEFAULT_MAX_STEPS
    except ValueError:
        return _DEFAULT_MAX_STEPS


def _configured_min_relevance_score() -> float:
    raw = os.getenv(AGENT_MIN_RELEVANCE_SCORE_ENV)
    if raw is None:
        return _DEFAULT_MIN_RELEVANCE_SCORE
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_MIN_RELEVANCE_SCORE


def _configured_min_chunks_per_entity() -> int:
    raw = os.getenv(AGENT_MIN_CHUNKS_PER_ENTITY_ENV)
    if raw is None:
        return _DEFAULT_MIN_CHUNKS_PER_ENTITY
    try:
        v = int(raw)
        return v if v > 0 else _DEFAULT_MIN_CHUNKS_PER_ENTITY
    except ValueError:
        return _DEFAULT_MIN_CHUNKS_PER_ENTITY


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


def _configured_rerank_multi_top_k() -> int:
    raw = os.getenv(AGENT_RERANK_MULTI_TOP_K_ENV)
    if raw is None:
        return _DEFAULT_RERANK_MULTI_TOP_K
    try:
        v = int(raw)
        return v if v > 0 else _DEFAULT_RERANK_MULTI_TOP_K
    except ValueError:
        return _DEFAULT_RERANK_MULTI_TOP_K
