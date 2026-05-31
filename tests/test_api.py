from pytest import MonkeyPatch

from agentic_rag.api import AnswerRequest, _stream_answer_events, answer_question, health
from agentic_rag.generation.answering import format_evidence_context
from agentic_rag.testing.fixtures import sample_search_results


def test_health_endpoint_shape() -> None:
    assert health() == {"status": "ok"}


def test_answer_endpoint_uses_mock_evidence_by_default(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    answer = answer_question(AnswerRequest(question="Pin bao hanh bao lau?"))

    assert answer.status == "answered"
    assert answer.citations


def test_answer_endpoint_can_disable_mock_evidence() -> None:
    answer = answer_question(
        AnswerRequest(question="Pin bao hanh bao lau?", use_mock_evidence=False)
    )

    assert answer.status == "not_found"
    assert answer.citations == []


def test_stream_answer_events_include_deltas_citations_and_done() -> None:
    evidence_chunks = sample_search_results()
    events = list(
        _stream_answer_events(
            question="Pin bao hanh bao lau?",
            evidence_context=format_evidence_context(evidence_chunks),
            evidence_chunks=evidence_chunks,
        )
    )

    assert events[0].startswith("event: answer_delta\n")
    assert any(event.startswith("event: citation\n") for event in events)
    assert events[-1].startswith("event: done\n")
    assert '"status": "answered"' in events[-1]
