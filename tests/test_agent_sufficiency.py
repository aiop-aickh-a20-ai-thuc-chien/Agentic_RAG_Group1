"""Tests for grading and preprocess functions — no API key required."""

from __future__ import annotations

from collections.abc import Iterator

from agentic_rag.agent.grading import (
    grade_hallucination,
    preprocess_query,
)
from agentic_rag.core.contracts import Answer, Chunk, SearchResult


def _result(chunk_id: str) -> SearchResult:
    return SearchResult(
        chunk=Chunk(chunk_id=chunk_id, text="relevant evidence text", metadata={"source": "doc"}),
        score=0.5,
        rank=1,
        retriever="bm25",
    )


# --- preprocess_query ---


def test_preprocess_passthrough_simple_no_llm() -> None:
    result = preprocess_query("Pin bảo hành bao lâu?", [], llm_client=None)
    assert result == {"type": "single", "question": "Pin bảo hành bao lâu?"}


def test_preprocess_passthrough_no_trigger_signals() -> None:
    result = preprocess_query("Giá VF8 bao nhiêu?", [], llm_client=None)
    assert result["type"] == "single"
    assert result["question"] == "Giá VF8 bao nhiêu?"


def test_preprocess_llm_single() -> None:
    class _FakeLLM:
        def complete(self, prompt: str) -> str:
            return '{"type": "single", "question": "Pin VF8 bảo hành bao lâu?"}'

        def stream_complete(self, prompt: str) -> Iterator[str]:
            yield ""

    history = [{"role": "user", "content": "VF8 là xe gì?"}]
    result = preprocess_query("Còn pin nó thì sao?", history, llm_client=_FakeLLM())
    assert result["type"] == "single"
    assert result["question"] == "Pin VF8 bảo hành bao lâu?"


def test_preprocess_llm_multi() -> None:
    class _FakeLLM:
        def complete(self, prompt: str) -> str:
            return '{"type": "multi", "questions": ["pin VF8 bảo hành", "pin VF9 bảo hành"]}'

        def stream_complete(self, prompt: str) -> Iterator[str]:
            yield ""

    result = preprocess_query("So sánh pin VF8 và VF9", [], llm_client=_FakeLLM())
    assert result["type"] == "multi"
    assert len(result["questions"]) == 2


def test_preprocess_bad_json_falls_back() -> None:
    class _BadLLM:
        def complete(self, prompt: str) -> str:
            return "not json"

        def stream_complete(self, prompt: str) -> Iterator[str]:
            yield ""

    result = preprocess_query("So sánh VF8 và VF9", [], llm_client=_BadLLM())
    assert result["type"] == "single"


# --- grade_hallucination ---


def test_hallucination_not_found_is_always_grounded() -> None:
    answer = Answer(answer="không tìm thấy", status="not_found", citations=[])
    assert grade_hallucination("q", answer, [], llm_client=None) is True


def test_hallucination_no_docs_is_not_grounded() -> None:
    answer = Answer(answer="some claim", status="answered", citations=[])
    assert grade_hallucination("q", answer, [], llm_client=None) is False


def test_hallucination_llm_grounded() -> None:
    class _FakeLLM:
        def complete(self, prompt: str) -> str:
            return '{"grounded": true, "reason": "supported"}'

        def stream_complete(self, prompt: str) -> Iterator[str]:
            yield ""

    answer = Answer(answer="pin bảo hành 8 năm", status="answered", citations=[])
    assert grade_hallucination("q", answer, [_result("c1")], llm_client=_FakeLLM()) is True


def test_hallucination_llm_not_grounded() -> None:
    class _FakeLLM:
        def complete(self, prompt: str) -> str:
            return '{"grounded": false, "reason": "fabricated"}'

        def stream_complete(self, prompt: str) -> Iterator[str]:
            yield ""

    answer = Answer(answer="fabricated", status="answered", citations=[])
    assert grade_hallucination("q", answer, [_result("c1")], llm_client=_FakeLLM()) is False
