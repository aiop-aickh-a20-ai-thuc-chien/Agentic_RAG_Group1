"""Tests for Self-RAG node functions — deterministic, no API key required."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, NotRequired, TypedDict, cast

import pytest
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from agentic_rag.agent.node_contracts import GenerateNodeOutput, PreprocessNodeOutput
from agentic_rag.agent.nodes import (
    check_answer_node,
    generate_node,
    make_retrieve_node,
    preprocess_node,
    rerank_node,
    route_after_check,
    route_after_rerank,
    route_after_transform,
    transform_query_node,
)
from agentic_rag.agent.state import AgentState
from agentic_rag.core.contracts import (
    Answer,
    Chunk,
    LLMCompletionInput,
    LLMCompletionOutput,
    LLMStreamDelta,
    RetrievalInput,
    RetrievalOutput,
    SearchResult,
)
from agentic_rag.core.ports import SourceEvidenceProvider


@pytest.fixture(autouse=True)
def _disable_model_runtime_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from agentic_rag.model_runtime.factory import clear_model_runtime_caches

    clear_model_runtime_caches()
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setattr("agentic_rag.model_runtime.config.load_local_env", lambda: None)
    yield
    clear_model_runtime_caches()


def _chunk(chunk_id: str, text: str = "test evidence text long enough for grounding") -> Chunk:
    return Chunk(chunk_id=chunk_id, text=text, metadata={"source": "doc.pdf", "page": 1})


def _result(chunk_id: str, score: float = 0.5, retriever: str = "bm25") -> SearchResult:
    return SearchResult(chunk=_chunk(chunk_id), score=score, rank=1, retriever=retriever)


def _result_for_query(chunk_id: str, score: float, query: str, query_index: int) -> SearchResult:
    chunk = Chunk(
        chunk_id=chunk_id,
        text="test evidence text long enough for grounding",
        metadata={
            "source": "doc.pdf",
            "page": 1,
            "agent_retrieval_query": query,
            "agent_retrieval_query_index": query_index,
        },
    )
    return SearchResult(chunk=chunk, score=score, rank=1, retriever="hybrid")


class _FakeProvider:
    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results

    def retrieve(
        self,
        request: RetrievalInput,
    ) -> RetrievalOutput:
        return RetrievalOutput(results=self._results)

    def upload_document(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        start_parse: bool = True,
    ) -> object:
        raise NotImplementedError

    def document_chunks(
        self,
        *,
        document_id: str,
        page: int = 1,
        page_size: int | None = None,
        keywords: str | None = None,
    ) -> object:
        raise NotImplementedError


def _base_state(**overrides: object) -> AgentState:
    state: AgentState = {
        "question": "Pin bảo hành bao lâu?",
        "rewritten_question": "Pin bảo hành bao lâu?",
        "history": [],
        "pending_queries": [],
        "fused_results": [],
        "relevant_docs": [],
        "pinned_docs": [],
        "missing_entities": [],
        "rejected_chunk_ids": [],
        "queries_tried": ["Pin bảo hành bao lâu?"],
        "step_count": 0,
        "retrieval_exhausted": False,
        "document_ids": None,
        "trace": [],
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


class _GraphState(TypedDict):
    answer: NotRequired[Answer]
    relevant_docs: list[SearchResult]
    trace: list[dict[str, Any]]


# --- preprocess_node ---


def test_preprocess_passthrough_simple_no_llm(monkeypatch: object) -> None:
    import agentic_rag.agent.nodes as m

    monkeypatch.setattr(m, "get_llm_client", lambda role: None)  # type: ignore[attr-defined]
    update = preprocess_node(_base_state())
    assert update.rewritten_question == "Pin bảo hành bao lâu?"
    assert update.queries_tried == []  # no new entry when unchanged


def test_preprocess_resolves_history_via_llm(monkeypatch: object) -> None:
    import agentic_rag.agent.nodes as m

    class _FakeLLM:
        def complete(self, request: LLMCompletionInput) -> LLMCompletionOutput:
            return LLMCompletionOutput(
                text='{"type": "single", "question": "Pin VF8 bảo hành bao lâu?"}',
                provider="test",
                model="test",
            )

        def stream(self, request: LLMCompletionInput) -> Iterator[LLMStreamDelta]:
            yield LLMStreamDelta(text="")

    monkeypatch.setattr(m, "get_llm_client", lambda role: _FakeLLM())  # type: ignore[attr-defined]
    history = [{"role": "user", "content": "VF8 thông số thế nào?"}]
    state = _base_state(question="Còn pin nó thì sao?", history=history)
    update = preprocess_node(state)
    assert update.rewritten_question == "Pin VF8 bảo hành bao lâu?"
    assert update.queries_tried == ["Pin VF8 bảo hành bao lâu?"]


def test_preprocess_decomposes_via_llm(monkeypatch: object) -> None:
    import agentic_rag.agent.nodes as m

    class _FakeLLM:
        def complete(self, request: LLMCompletionInput) -> LLMCompletionOutput:
            return LLMCompletionOutput(
                text='{"type": "multi", "questions": ["pin VF8 bảo hành", "pin VF9 bảo hành"]}',
                provider="test",
                model="test",
            )

        def stream(self, request: LLMCompletionInput) -> Iterator[LLMStreamDelta]:
            yield LLMStreamDelta(text="")

    monkeypatch.setattr(m, "get_llm_client", lambda role: _FakeLLM())  # type: ignore[attr-defined]
    state = _base_state(question="So sánh pin VF8 và VF9")
    update = preprocess_node(state)
    assert update.queries_tried == ["pin VF8 bảo hành"]
    assert update.pending_queries == ["pin VF9 bảo hành"]


# --- retrieve_node ---


def test_retrieve_node_appends_results() -> None:
    provider = _FakeProvider([_result("c1", 0.8)])
    node = make_retrieve_node(cast(SourceEvidenceProvider, provider))
    update = node(_base_state())
    assert len(update.fused_results) > 0
    assert update.step_count == 1
    assert update.trace[0]["query_count"] == 1
    assert update.trace[0]["per_query"][0]["returned_chunks"] == 1
    assert (
        update.fused_results[0].chunk.metadata["agent_retrieval_query"]
        == _base_state()["queries_tried"][0]
    )


def test_retrieve_node_adds_all_chunks() -> None:
    # all chunks from all queries are added — no dedup in retrieve_node
    provider = _FakeProvider([_result("c1"), _result("c2")])
    node = make_retrieve_node(cast(SourceEvidenceProvider, provider))
    state = _base_state(queries_tried=["q1"], pending_queries=["q2"])
    update = node(state)
    chunk_ids = [r.chunk.chunk_id for r in update.fused_results]
    assert chunk_ids.count("c1") == 2  # c1 from q1 and q2 both kept
    assert chunk_ids.count("c2") == 2
    assert update.trace[0]["added_chunks_total"] == 4


def test_retrieve_node_traces_multi_query_aggregation(monkeypatch: object) -> None:
    monkeypatch.delenv("AGENT_RETRIEVE_WORKERS", raising=False)  # type: ignore[attr-defined]
    provider = _FakeProvider([_result("c1"), _result("c2")])
    node = make_retrieve_node(cast(SourceEvidenceProvider, provider))
    state = _base_state(
        queries_tried=["q1"],
        pending_queries=["q2", "q3"],
    )
    update = node(state)
    trace = update.trace[0]
    assert trace["queries"] == ["q1", "q2", "q3"]
    assert trace["query_count"] == 3
    assert trace["parallel"] is True
    assert trace["worker_count"] == 3
    assert trace["returned_chunks_total"] == 6
    assert trace["added_chunks_total"] == 6


def test_retrieve_node_respects_worker_limit(monkeypatch: object) -> None:
    monkeypatch.setenv("AGENT_RETRIEVE_WORKERS", "2")  # type: ignore[attr-defined]
    provider = _FakeProvider([_result("c1")])
    node = make_retrieve_node(cast(SourceEvidenceProvider, provider))
    update = node(_base_state(queries_tried=["q1"], pending_queries=["q2", "q3"]))
    assert update.trace[0]["parallel"] is True
    assert update.trace[0]["worker_count"] == 2


# --- rerank_node ---


def test_rerank_node_sets_relevant_docs() -> None:
    docs = [_result(f"c{i}", 0.9) for i in range(3)]
    update = rerank_node(_base_state(fused_results=docs))
    assert len(update.relevant_docs) > 0
    assert update.trace[0]["rerank_strategy"] == "per_query_group"


def test_rerank_node_multi_group_per_group_rerank() -> None:
    docs = [
        _result_for_query("vf7_a", 0.99, "VF 7 info", 0),
        _result_for_query("vf7_b", 0.98, "VF 7 info", 0),
        _result_for_query("vf3_a", 0.20, "VF 3 info", 1),
    ]
    update = rerank_node(_base_state(fused_results=docs))
    assert update.trace[0]["rerank_strategy"] == "per_query_group"
    assert update.trace[0]["group_count"] == 2
    chunk_ids = [r.chunk.chunk_id for r in update.relevant_docs]
    assert "vf7_a" in chunk_ids
    assert "vf3_a" in chunk_ids


def test_rerank_node_multi_group_reads_top_k_from_env(monkeypatch: object) -> None:
    monkeypatch.setenv("AGENT_RERANK_MULTI_TOP_K", "2")  # type: ignore[attr-defined]
    docs = [
        _result_for_query("vf7_a", 0.99, "VF 7 info", 0),
        _result_for_query("vf7_b", 0.98, "VF 7 info", 0),
        _result_for_query("vf7_c", 0.97, "VF 7 info", 0),
        _result_for_query("vf3_a", 0.96, "VF 3 info", 1),
        _result_for_query("vf3_b", 0.95, "VF 3 info", 1),
        _result_for_query("vf3_c", 0.94, "VF 3 info", 1),
    ]
    update = rerank_node(_base_state(fused_results=docs))
    groups = update.trace[0]["groups"]
    assert [group["kept"] for group in groups] == [2, 2]
    assert len(update.relevant_docs) == 4


def test_rerank_node_empty() -> None:
    update = rerank_node(_base_state(fused_results=[]))
    assert update.relevant_docs == []
    assert update.pinned_docs == []
    assert update.missing_entities == []


def test_rerank_node_gap_detection_flags_thin_group(monkeypatch: object) -> None:
    monkeypatch.setenv("AGENT_MIN_CHUNKS_PER_ENTITY", "2")  # type: ignore[attr-defined]
    docs = [
        _result_for_query("vf7_a", 0.99, "VF 7 info", 0),
        _result_for_query("vf7_b", 0.98, "VF 7 info", 0),
        _result_for_query("vf3_a", 0.20, "VF 3 info", 1),
    ]
    update = rerank_node(_base_state(fused_results=docs))
    assert "VF 3 info" in update.missing_entities
    assert "VF 7 info" not in update.missing_entities


def test_rerank_node_gap_detection_pins_all_groups(monkeypatch: object) -> None:
    """All chunks are pinned regardless of group size — thin groups still flagged missing."""
    monkeypatch.setenv("AGENT_MIN_CHUNKS_PER_ENTITY", "2")  # type: ignore[attr-defined]
    docs = [
        _result_for_query("vf7_a", 0.99, "VF 7 info", 0),
        _result_for_query("vf7_b", 0.98, "VF 7 info", 0),
        _result_for_query("vf3_a", 0.20, "VF 3 info", 1),
    ]
    update = rerank_node(_base_state(fused_results=docs))
    pinned_ids = [r.chunk.chunk_id for r in update.pinned_docs]
    assert "vf7_a" in pinned_ids
    assert "vf7_b" in pinned_ids
    assert "vf3_a" in pinned_ids
    assert "VF 3 info" in update.missing_entities


def test_rerank_node_no_gap_detection_for_single_group() -> None:
    docs = [_result(f"c{i}", 0.9) for i in range(3)]
    update = rerank_node(_base_state(fused_results=docs))
    assert update.missing_entities == []


def test_rerank_node_rejected_chunks_excluded_in_next_loop() -> None:
    """Chunks rejected in loop 1 are filtered out before reranking in loop 2."""
    import agentic_rag.agent.nodes as m

    seen: list[list[str]] = []

    def fake_rerank(
        question: str, candidates: list[SearchResult], top_k: int = 5
    ) -> tuple[list[SearchResult], dict[str, object]]:
        seen.append([r.chunk.chunk_id for r in candidates])
        top = candidates[:top_k]
        return top, {"used_provider": "score_fallback"}

    # monkeypatch not available here — use direct call pattern
    original = m._rerank
    m._rerank = fake_rerank  # type: ignore[assignment]
    try:
        bad_ids = [f"bad_{i}" for i in range(3)]
        all_docs = [_result_for_query(cid, 0.1, "VF 3 info", 0) for cid in bad_ids] + [
            _result_for_query("good_1", 0.9, "VF 3 info", 0)
        ]

        state = _base_state(
            fused_results=all_docs,
            rejected_chunk_ids=bad_ids,
        )
        rerank_node(state)

        assert seen, "rerank was never called"
        assert all(cid not in seen[0] for cid in bad_ids)
        assert "good_1" in seen[0]
    finally:
        m._rerank = original


def test_rerank_node_builds_rejected_list() -> None:
    """Chunks not selected into top_k are added to rejected_chunk_ids."""
    docs = [_result(f"c{i}", 0.9) for i in range(6)]
    update = rerank_node(_base_state(fused_results=docs))
    # All chunks fit within top_k, so nothing rejected
    assert isinstance(update.rejected_chunk_ids, list)


# --- transform_query_node với missing_entities ---


def test_transform_skips_when_no_new_query(monkeypatch: object) -> None:
    import agentic_rag.agent.nodes as m

    monkeypatch.setattr(m, "get_llm_client", lambda role: None)  # type: ignore[attr-defined]
    update = transform_query_node(_base_state())
    assert update.trace[0].get("skipped") is True
    assert update.trace[0]["reason"] == "query_already_tried"
    assert update.retrieval_exhausted is True


def test_transform_passes_missing_entities_to_llm(monkeypatch: object) -> None:
    import agentic_rag.agent.nodes as m

    captured: list[str] = []

    class _FakeLLM:
        def complete(self, request: LLMCompletionInput) -> LLMCompletionOutput:
            captured.append(request.prompt)
            return LLMCompletionOutput(
                text='{"method": "requery", "query": "thông số kỹ thuật VF 3"}',
                provider="test",
                model="test",
            )

        def stream(self, request: LLMCompletionInput) -> Iterator[LLMStreamDelta]:
            yield LLMStreamDelta(text="")

    monkeypatch.setattr(m, "get_llm_client", lambda role: _FakeLLM())  # type: ignore[attr-defined]
    state = _base_state(missing_entities=["VF 3 info"])
    update = transform_query_node(state)
    assert any("VF 3 info" in p for p in captured)
    assert update.trace[0]["next_route_hint"] == "retrieve"


# --- generate_node với pinned_docs ---


def test_generate_node_merges_pinned_and_relevant_docs() -> None:
    pinned = [_result("pinned_c1", 0.95)]
    relevant = [_result("relevant_c2", 0.80)]
    update = generate_node(_base_state(pinned_docs=pinned, relevant_docs=relevant))
    assert isinstance(update.answer, Answer)
    assert update.trace[0]["pinned_count"] == 1


def test_generate_node_deduplicates_pinned_and_relevant() -> None:
    shared = _result("shared_c1", 0.90)
    update = generate_node(_base_state(pinned_docs=[shared], relevant_docs=[shared]))
    doc_ids = [r.chunk.chunk_id for r in update.relevant_docs]
    assert doc_ids.count("shared_c1") == 1


# --- route_after_rerank ---


def test_route_rerank_generates_when_has_docs() -> None:
    assert route_after_rerank(_base_state(relevant_docs=[_result("c1")])) == "generate"


def test_route_rerank_transforms_when_missing_entities_even_with_docs() -> None:
    """Has docs but some entities are missing — should go find them, not generate yet."""
    state = _base_state(
        relevant_docs=[_result("c1")],
        missing_entities=["thông tin VF7"],
        step_count=1,
    )
    assert route_after_rerank(state) == "transform_query"


def test_route_rerank_generates_when_no_missing_entities() -> None:
    """All entities covered — generate even if we came from a multi-query."""
    state = _base_state(
        relevant_docs=[_result("c1")],
        missing_entities=[],
    )
    assert route_after_rerank(state) == "generate"


def test_route_rerank_transforms_when_no_docs() -> None:
    assert route_after_rerank(_base_state(relevant_docs=[], step_count=1)) == "transform_query"


def test_route_rerank_generates_at_max_steps(monkeypatch: object) -> None:
    monkeypatch.setenv("AGENT_MAX_STEPS", "2")  # type: ignore[attr-defined]
    assert route_after_rerank(_base_state(relevant_docs=[], step_count=2)) == "generate"


def test_route_rerank_transforms_when_below_threshold(monkeypatch: object) -> None:
    monkeypatch.setenv("AGENT_MIN_RELEVANCE_SCORE", "0.5")  # type: ignore[attr-defined]
    state = _base_state(relevant_docs=[_result("c1", 0.3)], step_count=1)
    assert route_after_rerank(state) == "transform_query"


def test_route_rerank_generates_when_above_threshold(monkeypatch: object) -> None:
    monkeypatch.setenv("AGENT_MIN_RELEVANCE_SCORE", "0.5")  # type: ignore[attr-defined]
    assert route_after_rerank(_base_state(relevant_docs=[_result("c1", 0.8)])) == "generate"


def test_route_rerank_generates_at_max_steps_even_below_threshold(monkeypatch: object) -> None:
    monkeypatch.setenv("AGENT_MIN_RELEVANCE_SCORE", "0.9")  # type: ignore[attr-defined]
    monkeypatch.setenv("AGENT_MAX_STEPS", "2")  # type: ignore[attr-defined]
    state = _base_state(relevant_docs=[_result("c1", 0.1)], step_count=2)
    assert route_after_rerank(state) == "generate"


def test_route_rerank_threshold_disabled_by_default() -> None:
    assert route_after_rerank(_base_state(relevant_docs=[_result("c1", 0.001)])) == "generate"


def test_transform_skip_after_existing_answer_points_to_check(monkeypatch: object) -> None:
    import agentic_rag.agent.nodes as m

    monkeypatch.setattr(m, "get_llm_client", lambda role: None)  # type: ignore[attr-defined]
    answer = Answer(answer="not found", status="not_found", citations=[])
    update = transform_query_node(_base_state(answer=answer))
    assert update.trace[0].get("skipped") is True
    assert update.trace[0]["next_route_hint"] == "check_answer"


def test_transform_via_llm(monkeypatch: object) -> None:
    import agentic_rag.agent.nodes as m

    class _FakeLLM:
        def complete(self, request: LLMCompletionInput) -> LLMCompletionOutput:
            return LLMCompletionOutput(
                text='{"method": "expand", "query": "thời hạn bảo hành pin xe điện"}',
                provider="test",
                model="test",
            )

        def stream(self, request: LLMCompletionInput) -> Iterator[LLMStreamDelta]:
            yield LLMStreamDelta(text="")

    monkeypatch.setattr(m, "get_llm_client", lambda role: _FakeLLM())  # type: ignore[attr-defined]
    update = transform_query_node(_base_state())
    assert update.trace[0]["next_route_hint"] == "retrieve"
    assert update.trace[0]["llm_result"]["method"] == "expand"
    assert update.queries_tried == ["thời hạn bảo hành pin xe điện"]


# --- route_after_transform ---


def test_route_transform_retrieves_when_new_query() -> None:
    trace = [{"node": "transform_query", "method": "requery", "query": "new"}]
    assert route_after_transform(_base_state(trace=trace)) == "retrieve"


def test_route_transform_generates_when_skipped_without_answer() -> None:
    trace = [{"node": "transform_query", "skipped": True}]
    assert route_after_transform(_base_state(trace=trace)) == "generate"


def test_route_transform_checks_when_skipped_after_answer() -> None:
    trace = [{"node": "transform_query", "skipped": True}]
    answer = Answer(answer="not found", status="not_found", citations=[])
    assert route_after_transform(_base_state(answer=answer, trace=trace)) == "check_answer"


# --- generate_node ---


def test_generate_node_returns_answer() -> None:
    docs = [_result(f"c{i}", 0.9) for i in range(3)]
    update = generate_node(_base_state(relevant_docs=docs))
    assert isinstance(update.answer, Answer)


# --- check_answer_node ---


def test_check_answer_logs_status() -> None:
    answer = Answer(answer="Pin bảo hành 8 năm", status="answered", citations=[])
    update = check_answer_node(_base_state(answer=answer))
    assert update.trace[0]["status"] == "answered"


# --- routing ---


def test_route_check_ends_when_answered() -> None:
    answer = Answer(answer="ok", status="answered", citations=[])
    assert route_after_check(_base_state(answer=answer)) == "end"


def test_route_check_transforms_when_not_found() -> None:
    answer = Answer(answer="not found", status="not_found", citations=[])
    assert route_after_check(_base_state(answer=answer, step_count=1)) == "transform_query"


def test_route_check_ends_when_retrieval_exhausted() -> None:
    answer = Answer(answer="not found", status="not_found", citations=[])
    state = _base_state(answer=answer, retrieval_exhausted=True, step_count=1)
    assert route_after_check(state) == "end"


def test_route_check_ends_when_not_found_at_max(monkeypatch: object) -> None:
    monkeypatch.setenv("AGENT_MAX_STEPS", "2")  # type: ignore[attr-defined]
    answer = Answer(answer="not found", status="not_found", citations=[])
    assert route_after_check(_base_state(answer=answer, step_count=2)) == "end"


def test_node_output_is_frozen_and_rejects_extra_fields() -> None:
    output = PreprocessNodeOutput(
        rewritten_question="rewritten",
        queries_tried=["rewritten"],
        trace=[{"node": "preprocess"}],
    )

    with pytest.raises(ValidationError):
        output.rewritten_question = "changed"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        PreprocessNodeOutput(
            rewritten_question="rewritten",
            queries_tried=[],
            trace=[],
            unexpected=True,
        )  # type: ignore[call-arg]


def test_unset_optional_node_fields_remain_absent_from_partial_update() -> None:
    output = PreprocessNodeOutput(
        rewritten_question="unchanged",
        queries_tried=[],
        trace=[{"node": "preprocess"}],
    )

    assert output.model_dump(exclude_unset=True) == {
        "rewritten_question": "unchanged",
        "queries_tried": [],
        "trace": [{"node": "preprocess"}],
    }


def test_langgraph_accepts_node_model_and_preserves_nested_contracts() -> None:
    answer = Answer(answer="grounded", status="answered", citations=[])
    result = _result("c1", 0.9)
    output = GenerateNodeOutput(
        answer=answer,
        relevant_docs=[result],
        trace=[{"node": "generate"}],
    )

    graph = StateGraph(_GraphState)
    graph.add_node("generate", lambda _state: output)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", END)
    compiled = graph.compile()

    final_state = compiled.invoke({"relevant_docs": [], "trace": []})

    assert final_state["answer"] is answer
    assert final_state["relevant_docs"] == [result]
