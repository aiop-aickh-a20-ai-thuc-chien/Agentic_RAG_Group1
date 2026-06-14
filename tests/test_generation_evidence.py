from pytest import MonkeyPatch

from agentic_rag.core.contracts import (
    EvidenceResolutionInput,
    RetrievalInput,
    RetrievalOutput,
    SearchResult,
)
from agentic_rag.generation import evidence
from agentic_rag.testing.fixtures import sample_search_results


class FakeSourceProvider:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results
        self.seen_document_ids: list[str] | None = None
        self.seen_exclude_dedup_layers: list[str] = []

    def retrieve(
        self,
        request: RetrievalInput,
    ) -> RetrievalOutput:
        self.seen_document_ids = request.document_ids
        self.seen_exclude_dedup_layers = request.exclude_dedup_layers
        return RetrievalOutput(results=self.results)


def test_evidence_for_question_uses_local_pdf_provider(monkeypatch: MonkeyPatch) -> None:
    provider = FakeSourceProvider(sample_search_results())
    monkeypatch.setattr(evidence, "source_provider_from_env", lambda: provider)

    resolved = evidence.evidence_for_question(
        EvidenceResolutionInput(
            question="Pin bao hanh bao lau?",
            provider="local_pdf",
            document_ids=["doc-1"],
            exclude_dedup_layers=["exact_sha256"],
            use_mock_evidence=False,
        )
    )

    assert resolved.chunks == provider.results
    assert provider.seen_document_ids == ["doc-1"]
    assert provider.seen_exclude_dedup_layers == ["exact_sha256"]
    assert "chunk_id=" in resolved.context
