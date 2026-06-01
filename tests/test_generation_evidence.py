from pytest import MonkeyPatch

from agentic_rag.core.contracts import SearchResult
from agentic_rag.generation import evidence
from agentic_rag.testing.fixtures import sample_search_results


class FakeSourceProvider:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results
        self.seen_document_ids: list[str] | None = None

    def retrieve(
        self,
        *,
        question: str,
        document_ids: list[str] | None = None,
        page_size: int | None = None,
    ) -> list[SearchResult]:
        self.seen_document_ids = document_ids
        return self.results


def test_evidence_for_question_uses_local_pdf_provider(monkeypatch: MonkeyPatch) -> None:
    provider = FakeSourceProvider(sample_search_results())
    monkeypatch.setattr(evidence, "source_provider_from_env", lambda: provider)

    chunks, context = evidence.evidence_for_question(
        question="Pin bao hanh bao lau?",
        provider="local_pdf",
        document_ids=["doc-1"],
        use_mock_evidence=False,
    )

    assert chunks == provider.results
    assert provider.seen_document_ids == ["doc-1"]
    assert "chunk_id=" in context
