"""Shared stack-neutral data contracts for all implementation modules."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AnswerStatus = Literal["answered", "not_found"]
RetrieverName = Literal["bm25", "dense", "hybrid", "rerank"]
KnowledgeQualityFindingKind = Literal["exact_duplicate", "near_duplicate", "conflict"]
KnowledgeQualitySeverity = Literal["info", "warning", "critical"]
KnowledgeQualityStatus = Literal["open", "resolved", "ignored"]
ModelRole = Literal[
    "query_rewrite",
    "query_transform",
    "generation",
    "ingestion",
    "evaluation",
]


class _ContractModel(BaseModel):
    """Base configuration for shared contract models."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Chunk(_ContractModel):
    """A normalized document segment produced by ingestion modules."""

    chunk_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResult(_ContractModel):
    """A ranked retrieval result passed between retrieval, fusion, and generation."""

    chunk: Chunk
    score: float
    rank: int
    retriever: RetrieverName | str


class Citation(_ContractModel):
    """A source reference derived from retrieved evidence metadata."""

    source: str
    chunk_id: str
    page: int | None = None
    section: str | None = None
    url: str | None = None


class Answer(_ContractModel):
    """A grounded generation result returned to UI or evaluation layers."""

    answer: str
    status: AnswerStatus
    citations: list[Citation] = Field(default_factory=list)


class ConversationMessage(_ContractModel):
    """One conversation message passed into the Workflow Module."""

    role: str
    content: str


class WorkflowRunInput(_ContractModel):
    """Validated input for one Workflow run."""

    question: str
    history: list[ConversationMessage] = Field(default_factory=list)
    document_ids: list[str] | None = None


class WorkflowRunOutput(_ContractModel):
    """Answer plus evidence and trace for one Workflow run."""

    answer: Answer
    evidence_chunks: list[SearchResult] = Field(default_factory=list)
    queries_tried: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)


class RetrievalInput(_ContractModel):
    """Validated retrieval request passed to a source evidence provider."""

    question: str
    document_ids: list[str] | None = None
    page_size: int | None = None


class RetrievalOutput(_ContractModel):
    """Normalized retrieval results returned by a source evidence provider."""

    results: list[SearchResult] = Field(default_factory=list)


class EvidenceResolutionInput(_ContractModel):
    """Validated input for resolving evidence before generation."""

    question: str
    evidence_context: str | None = None
    evidence_chunks: list[SearchResult] | None = None
    provider: str | None = None
    document_ids: list[str] | None = None
    use_mock_evidence: bool = False


class EvidenceResolutionOutput(_ContractModel):
    """Resolved evidence chunks and final evidence context."""

    chunks: list[SearchResult] = Field(default_factory=list)
    context: str


class SourceDocumentUpload(_ContractModel):
    """Result returned after a source document is accepted for indexing."""

    document_id: str
    name: str
    dataset_id: str
    parse_started: bool
    trace: dict[str, object] | None = None


class SourceDocumentChunks(_ContractModel):
    """Chunks for one source document plus its full chunk count."""

    chunks: list[Chunk]
    total_chunks: int


class KnowledgeQualityFact(_ContractModel):
    """One normalized fact extracted from a source chunk for quality checks."""

    fact_id: str
    chunk_id: str
    entity: str
    attribute: str
    value: str
    normalized_value: float | str
    unit: str | None = None
    span: str
    start: int | None = None
    end: int | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class KnowledgeQualityFinding(_ContractModel):
    """A duplicate or conflict finding across one or more chunks."""

    finding_id: str
    kind: KnowledgeQualityFindingKind
    severity: KnowledgeQualitySeverity
    status: KnowledgeQualityStatus = "open"
    chunk_ids: list[str]
    fact_ids: list[str] = Field(default_factory=list)
    summary: str
    suggested_action: str
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, object] = Field(default_factory=dict)


class KnowledgeQualityReport(_ContractModel):
    """Facts and findings produced by a knowledge-quality scan."""

    facts: list[KnowledgeQualityFact] = Field(default_factory=list)
    findings: list[KnowledgeQualityFinding] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class LLMCompletionInput(_ContractModel):
    """Typed prompt request for one model completion."""

    prompt: str
    system_message: str
    temperature: float = 0.0


class LLMCompletionOutput(_ContractModel):
    """Normalized text returned from a model completion provider."""

    text: str
    provider: str
    model: str


class LLMStreamDelta(_ContractModel):
    """One normalized text delta from a streaming model call."""

    text: str


class EmbeddingInput(_ContractModel):
    """Typed request for embedding one or more texts."""

    texts: list[str] = Field(min_length=1)


class EmbeddingOutput(_ContractModel):
    """Normalized embedding vectors returned by one embedding provider."""

    vectors: list[list[float]]
    provider: str
    model: str
    dimensions: int


class RerankInput(_ContractModel):
    """Typed reranking request over retrieval candidates."""

    query: str
    candidates: list[SearchResult]
    top_k: int = Field(default=5, ge=0)


class RerankOutput(_ContractModel):
    """Normalized reranking results and trace metadata."""

    results: list[SearchResult]
    metadata: dict[str, object] = Field(default_factory=dict)
