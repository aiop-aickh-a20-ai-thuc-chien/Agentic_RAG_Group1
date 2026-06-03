"""Tests for the Self-RAG agent graph — deterministic, no API key required."""

from __future__ import annotations

from typing import cast

from agentic_rag.agent.graph import AgentResult, run_agent
from agentic_rag.core.contracts import Chunk, SearchResult
from agentic_rag.core.ports import SourceEvidenceProvider


def _chunk(chunk_id: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        text="pin xe vinfast duoc bao hanh 8 nam hoac 160000 km",
        metadata={"source": "vinfast.pdf", "page": 1},
    )


def _result(chunk_id: str, score: float = 0.9) -> SearchResult:
    return SearchResult(chunk=_chunk(chunk_id), score=score, rank=1, retriever="bm25")


class _FakeProvider:
    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results
        self.call_count = 0

    def retrieve(
        self,
        *,
        question: str,
        document_ids: list[str] | None = None,
        page_size: int | None = None,
    ) -> list[SearchResult]:
        self.call_count += 1
        return self._results

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


def test_agent_returns_agent_result(monkeypatch: object) -> None:
    import agentic_rag.agent.nodes as m

    monkeypatch.setenv("AGENT_MAX_STEPS", "1")  # type: ignore[attr-defined]
    monkeypatch.setattr(m, "configured_llm_client", lambda: None)  # type: ignore[attr-defined]
    provider = _FakeProvider([_result(f"c{i}") for i in range(3)])
    result = run_agent(
        provider=cast(SourceEvidenceProvider, provider), question="Pin bảo hành bao lâu?"
    )
    assert isinstance(result, AgentResult)
    assert result.answer is not None
    assert provider.call_count == 1
    assert all(step.get("node") != "grade_hallucination" for step in result.steps)


def test_agent_always_returns_answer_with_empty_provider(monkeypatch: object) -> None:
    import agentic_rag.agent.nodes as m

    monkeypatch.setenv("AGENT_MAX_STEPS", "1")  # type: ignore[attr-defined]
    monkeypatch.setattr(m, "configured_llm_client", lambda: None)  # type: ignore[attr-defined]
    result = run_agent(
        provider=cast(SourceEvidenceProvider, _FakeProvider([])),
        question="câu hỏi bất kỳ?",
    )
    assert isinstance(result, AgentResult)
    assert result.answer.status in {"answered", "not_found"}


def test_agent_empty_provider_stops_when_transform_has_no_new_query(monkeypatch: object) -> None:
    import agentic_rag.agent.nodes as m

    monkeypatch.setenv("AGENT_MAX_STEPS", "3")  # type: ignore[attr-defined]
    monkeypatch.setattr(m, "configured_llm_client", lambda: None)  # type: ignore[attr-defined]
    provider = _FakeProvider([])
    result = run_agent(
        provider=cast(SourceEvidenceProvider, provider),
        question="cau hoi khong co trong tai lieu?",
    )
    assert isinstance(result, AgentResult)
    assert result.answer.status in {"answered", "not_found"}
    assert provider.call_count == 1
    assert any(
        step.get("node") == "transform_query" and step.get("skipped")
        for step in result.steps
    )
