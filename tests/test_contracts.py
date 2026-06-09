from typing import get_args

import pytest
from pydantic import BaseModel, ValidationError

from agentic_rag.core.contracts import (
    Answer,
    Chunk,
    Citation,
    ConversationMessage,
    EmbeddingInput,
    EmbeddingOutput,
    EvidenceResolutionInput,
    EvidenceResolutionOutput,
    LLMCompletionInput,
    LLMCompletionOutput,
    LLMStreamDelta,
    ModelRole,
    RerankInput,
    RerankOutput,
    RetrievalInput,
    RetrievalOutput,
    SearchResult,
    SourceDocumentChunks,
    SourceDocumentUpload,
    WorkflowRunInput,
    WorkflowRunOutput,
)
from agentic_rag.testing.fixtures import sample_search_results


def test_chunk_keeps_stack_neutral_metadata() -> None:
    chunk = Chunk(
        chunk_id="pdf_001_p12_c01",
        text="Pin cao ap duoc bao hanh 8 nam.",
        metadata={
            "source": "vinfast_warranty.pdf",
            "source_type": "pdf",
            "file_name": "vinfast_warranty.pdf",
            "url": None,
            "page": 12,
            "section": None,
        },
    )

    assert chunk.chunk_id == "pdf_001_p12_c01"
    assert chunk.metadata["source_type"] == "pdf"
    assert chunk.metadata["page"] == 12


def test_search_result_references_chunk_and_rank() -> None:
    chunk = Chunk(chunk_id="url_001_smain_c01", text="Noi dung chinh.", metadata={})
    result = SearchResult(chunk=chunk, score=0.91, rank=1, retriever="dense")

    assert result.chunk is chunk
    assert result.retriever == "dense"
    assert result.rank == 1


def test_answer_supports_found_and_not_found_statuses() -> None:
    citation = Citation(source="vinfast_warranty.pdf", chunk_id="pdf_001_p12_c01", page=12)
    answered = Answer(answer="Pin duoc bao hanh 8 nam.", citations=[citation], status="answered")
    not_found = Answer(
        answer="Mình chưa tìm thấy thông tin này trong tài liệu được cung cấp.",
        citations=[],
        status="not_found",
    )

    assert answered.citations == [citation]
    assert not_found.status == "not_found"


def test_answer_converts_nested_citation_dicts() -> None:
    answer = Answer(
        answer="Pin duoc bao hanh 8 nam.",
        status="answered",
        citations=[{"source": "vinfast_warranty.pdf", "chunk_id": "pdf_001_p12_c01"}],
    )

    assert answer.citations == [Citation(source="vinfast_warranty.pdf", chunk_id="pdf_001_p12_c01")]
    assert answer.model_dump()["citations"][0]["chunk_id"] == "pdf_001_p12_c01"


def test_answer_rejects_invalid_citation_list_items() -> None:
    with pytest.raises(ValidationError):
        Answer(answer="Invalid citation.", status="answered", citations=["not-a-citation"])


def test_search_result_converts_nested_chunk_dict() -> None:
    result = SearchResult(
        chunk={
            "chunk_id": "url_001_smain_c01",
            "text": "Noi dung tu website.",
            "metadata": {"source_type": "url"},
        },
        score=0.7,
        rank=2,
        retriever="bm25",
    )

    assert result.chunk == Chunk(
        chunk_id="url_001_smain_c01",
        text="Noi dung tu website.",
        metadata={"source_type": "url"},
    )


def test_contracts_reject_extra_top_level_fields() -> None:
    payload: dict[str, object] = {
        "chunk_id": "bad",
        "text": "Bad chunk.",
        "metadata": {},
        "unexpected": True,
    }

    with pytest.raises(ValidationError):
        Chunk.model_validate(payload)


def test_answer_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        Answer(answer="Invalid status.", status="done")


def test_contract_models_are_frozen() -> None:
    chunk = Chunk(chunk_id="immutable", text="Cannot mutate this.", metadata={})
    field_name = "text"

    with pytest.raises(ValidationError):
        setattr(chunk, field_name, "Mutated")


def test_source_document_upload_is_frozen_and_strict() -> None:
    upload = SourceDocumentUpload(
        document_id="doc-1",
        name="warranty.pdf",
        dataset_id="local_pdf",
        parse_started=True,
        trace={"parser": "docling"},
    )

    assert upload.document_id == "doc-1"
    assert upload.trace == {"parser": "docling"}

    with pytest.raises(ValidationError):
        SourceDocumentUpload.model_validate(
            {
                "document_id": "doc-1",
                "name": "warranty.pdf",
                "dataset_id": "local_pdf",
                "parse_started": True,
                "unexpected": True,
            }
        )

    field_name = "name"

    with pytest.raises(ValidationError):
        setattr(upload, field_name, "changed.pdf")


def test_source_document_chunks_validates_nested_chunk_dicts() -> None:
    chunk_dict = {
        "chunk_id": "chunk-1",
        "text": "Pin cao ap duoc bao hanh 8 nam.",
        "metadata": {"source_type": "pdf"},
    }

    page = SourceDocumentChunks(chunks=[chunk_dict], total_chunks=1)

    assert page.chunks == [
        Chunk(
            chunk_id="chunk-1",
            text="Pin cao ap duoc bao hanh 8 nam.",
            metadata={"source_type": "pdf"},
        )
    ]
    assert page.total_chunks == 1


def test_workflow_and_retrieval_contracts_are_strict_and_nested() -> None:
    workflow = WorkflowRunInput(
        question="Pin bao hanh bao lau?",
        history=[{"role": "user", "content": "Hoi ve VF8"}],
        document_ids=["doc-1"],
    )
    retrieval = RetrievalOutput(
        results=[
            {
                "chunk": {"chunk_id": "c1", "text": "Noi dung", "metadata": {}},
                "score": 0.8,
                "rank": 1,
                "retriever": "bm25",
            }
        ]
    )
    resolved = EvidenceResolutionOutput(chunks=retrieval.results, context="context")
    run = WorkflowRunOutput(
        answer=Answer(answer="Duoc bao hanh 8 nam.", status="answered"),
        evidence_chunks=retrieval.results,
        queries_tried=["Pin bao hanh bao lau?"],
        steps=[{"node": "generate"}],
    )

    assert workflow.history == [ConversationMessage(role="user", content="Hoi ve VF8")]
    assert retrieval.results[0].chunk.chunk_id == "c1"
    assert resolved.context == "context"
    assert run.answer.status == "answered"

    with pytest.raises(ValidationError):
        WorkflowRunInput.model_validate({"question": "q", "unexpected": True})

    with pytest.raises(ValidationError):
        RetrievalInput.model_validate({"question": "q", "page_size": "bad"})

    with pytest.raises(ValidationError):
        EvidenceResolutionInput.model_validate({"question": "q", "unknown": True})


def test_model_runtime_contracts_are_strict_and_frozen() -> None:
    request = LLMCompletionInput(prompt="Question", system_message="System")
    output = LLMCompletionOutput(text="Answer", provider="openai", model="gpt-4o-mini")
    delta = LLMStreamDelta(text="chunk")

    assert isinstance(request, BaseModel)
    assert output.provider == "openai"
    assert delta.text == "chunk"

    with pytest.raises(ValidationError):
        LLMCompletionInput.model_validate(
            {"prompt": "Question", "system_message": "System", "unexpected": True}
        )

    field_name = "prompt"

    with pytest.raises(ValidationError):
        setattr(request, field_name, "changed")


def test_embedding_contract_rejects_empty_texts() -> None:
    with pytest.raises(ValidationError):
        EmbeddingInput(texts=[])

    output = EmbeddingOutput(
        vectors=[[0.1, 0.2], [0.3, 0.4]],
        provider="huggingface",
        model="sentence-transformers/test",
        dimensions=2,
    )

    assert output.dimensions == 2


def test_rerank_contract_validates_nested_search_results_and_top_k() -> None:
    candidates = [result.model_dump() for result in sample_search_results()]

    request = RerankInput(
        query="Pin bao hanh bao lau?",
        candidates=candidates,
        top_k=1,
    )
    output = RerankOutput(results=candidates[:1], metadata={"used_provider": "score"})

    assert isinstance(request.candidates[0], SearchResult)
    assert output.results[0].chunk.chunk_id == request.candidates[0].chunk.chunk_id

    with pytest.raises(ValidationError):
        RerankInput(query="q", candidates=[], top_k=-1)


def test_model_role_values_are_exact() -> None:
    assert get_args(ModelRole) == (
        "query_rewrite",
        "query_transform",
        "generation",
        "ingestion",
        "evaluation",
    )
