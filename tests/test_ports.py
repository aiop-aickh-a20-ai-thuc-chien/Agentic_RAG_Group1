from collections.abc import Iterator
from typing import get_type_hints

from agentic_rag.core.contracts import (
    Answer,
    Chunk,
    EmbeddingInput,
    EmbeddingOutput,
    EvidenceResolutionInput,
    EvidenceResolutionOutput,
    LLMCompletionInput,
    LLMCompletionOutput,
    LLMStreamDelta,
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
from agentic_rag.core.ports import (
    BM25Searcher,
    DenseSearcher,
    EmbeddingClient,
    EvidenceContextBuilder,
    EvidenceResolver,
    Generator,
    LLMClient,
    PdfIngestor,
    Reranker,
    SourceEvidenceProvider,
    UrlIngestor,
    WorkflowRunner,
)


def test_pdf_ingestor_protocol_exposes_pdf_signature() -> None:
    hints = get_type_hints(PdfIngestor.load_pdf_chunks)

    assert hints["path"] is str
    assert hints["return"] == list[Chunk]


def test_url_ingestor_protocol_exposes_url_signature() -> None:
    url_hints = get_type_hints(UrlIngestor.load_url_chunks)

    assert url_hints["url"] is str
    assert url_hints["return"] == list[Chunk]


def test_retrieval_protocols_expose_search_signatures() -> None:
    bm25_hints = get_type_hints(BM25Searcher.bm25_search)
    dense_hints = get_type_hints(DenseSearcher.dense_search)

    assert bm25_hints["query"] is str
    assert bm25_hints["top_k"] is int
    assert bm25_hints["return"] == list[SearchResult]
    assert dense_hints["query"] is str
    assert dense_hints["top_k"] is int
    assert dense_hints["return"] == list[SearchResult]


def test_evidence_and_generation_protocols_expose_integration_signatures() -> None:
    evidence_hints = get_type_hints(EvidenceContextBuilder.build_evidence_context)
    generation_hints = get_type_hints(Generator.generate_answer)

    assert evidence_hints["evidence_chunks"] == list[SearchResult]
    assert evidence_hints["return"] is str
    assert generation_hints["question"] is str
    assert generation_hints["evidence_context"] is str
    assert generation_hints["evidence_chunks"] == list[SearchResult]
    assert generation_hints["return"] is Answer


def test_source_provider_protocol_uses_pydantic_source_contracts() -> None:
    upload_hints = get_type_hints(SourceEvidenceProvider.upload_document)
    chunks_hints = get_type_hints(SourceEvidenceProvider.document_chunks)
    retrieve_hints = get_type_hints(SourceEvidenceProvider.retrieve)

    assert upload_hints["return"] is SourceDocumentUpload
    assert chunks_hints["document_id"] is str
    assert chunks_hints["return"] is SourceDocumentChunks
    assert retrieve_hints["request"] is RetrievalInput
    assert retrieve_hints["return"] is RetrievalOutput


def test_workflow_and_evidence_protocols_expose_contracts() -> None:
    workflow_hints = get_type_hints(WorkflowRunner.run)
    resolver_hints = get_type_hints(EvidenceResolver.resolve)

    assert workflow_hints["request"] is WorkflowRunInput
    assert workflow_hints["return"] is WorkflowRunOutput
    assert resolver_hints["request"] is EvidenceResolutionInput
    assert resolver_hints["return"] is EvidenceResolutionOutput


def test_model_runtime_ports_use_contract_objects() -> None:
    llm_complete_hints = get_type_hints(LLMClient.complete)
    llm_stream_hints = get_type_hints(LLMClient.stream)
    embedding_hints = get_type_hints(EmbeddingClient.embed)
    reranker_hints = get_type_hints(Reranker.rerank)

    assert llm_complete_hints["request"] is LLMCompletionInput
    assert llm_complete_hints["return"] is LLMCompletionOutput
    assert llm_stream_hints["request"] is LLMCompletionInput
    assert llm_stream_hints["return"] == Iterator[LLMStreamDelta]
    assert embedding_hints["request"] is EmbeddingInput
    assert embedding_hints["return"] is EmbeddingOutput
    assert reranker_hints["request"] is RerankInput
    assert reranker_hints["return"] is RerankOutput
