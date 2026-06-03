"""Protocol interfaces that keep module implementations stack-neutral."""

from __future__ import annotations

from typing import Any, Protocol

from agentic_rag.core.contracts import Answer, Chunk, SearchResult


class PdfIngestor(Protocol):
    """PDF ingestion and PDF chunking boundary."""

    def load_pdf_chunks(self, path: str) -> list[Chunk]:
        """Read a PDF file and return normalized chunks with page/source metadata."""


class UrlIngestor(Protocol):
    """URL ingestion and chunking boundary."""

    def load_url_chunks(self, url: str) -> list[Chunk]:
        """Fetch a URL and return normalized chunks with URL/section metadata."""


class QueryPreprocessor(Protocol):
    """Query normalization before retrieval."""

    def preprocess_query(self, query: str, llm_client: object = None) -> dict[str, Any]:
        """Normalize a raw user query for downstream retrieval modules."""


class BM25Searcher(Protocol):
    """Keyword-based indexing and retrieval."""

    def build_bm25_index(self, chunks: list[Chunk]) -> None:
        """Build or refresh a BM25 index from normalized chunks."""

    def bm25_search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """Return top-k BM25 results following the shared SearchResult contract."""


class DenseSearcher(Protocol):
    """Embedding-based indexing and retrieval."""

    def build_vector_index(self, chunks: list[Chunk]) -> None:
        """Build or refresh a vector index from normalized chunks."""

    def dense_search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """Return top-k dense retrieval results following the shared contract."""


class HybridFusion(Protocol):
    """Fusion and final evidence ranking."""

    def rrf_fusion(
        self,
        bm25_results: list[SearchResult],
        dense_results: list[SearchResult],
        top_k: int = 10,
    ) -> list[SearchResult]:
        """Fuse sparse and dense results using Reciprocal Rank Fusion or equivalent."""


class SourceDocumentUpload(Protocol):
    """Result returned after a source document is accepted for indexing."""

    @property
    def document_id(self) -> str:
        """Stable document identifier used by follow-up chunk/retrieval calls."""

    @property
    def name(self) -> str:
        """Display name for the uploaded document."""

    @property
    def dataset_id(self) -> str:
        """Provider dataset or namespace identifier."""

    @property
    def parse_started(self) -> bool:
        """Whether ingestion/chunking was started by the provider."""

    @property
    def trace(self) -> dict[str, object] | None:
        """Provider-specific ingestion trace payload."""


class SourceDocumentChunks(Protocol):
    """Chunks for one source document plus its full chunk count."""

    @property
    def chunks(self) -> list[Chunk]:
        """The returned page or collection of normalized chunks."""

    @property
    def total_chunks(self) -> int:
        """Total chunks available for this document before pagination."""


class SourceEvidenceProvider(Protocol):
    """Combined source upload, chunk inspection, and retrieval provider."""

    def upload_document(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        start_parse: bool = True,
    ) -> SourceDocumentUpload:
        """Upload or ingest a source document."""

    def document_chunks(
        self,
        *,
        document_id: str,
        page: int = 1,
        page_size: int | None = None,
        keywords: str | None = None,
    ) -> SourceDocumentChunks:
        """Return chunks for one source document."""

    def retrieve(
        self,
        *,
        question: str,
        document_ids: list[str] | None = None,
        page_size: int | None = None,
    ) -> list[SearchResult]:
        """Retrieve evidence chunks for generation."""


class Reranker(Protocol):
    """Optional reranking over fused candidates."""

    def rerank(
        self,
        query: str,
        candidates: list[SearchResult],
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Return final ranked evidence candidates."""


class EvidenceContextBuilder(Protocol):
    """Evidence formatting for generation."""

    def build_evidence_context(self, evidence_chunks: list[SearchResult]) -> str:
        """Format final evidence chunks into a grounded LLM context string."""


class Generator(Protocol):
    """Generation, citation, guardrails, and UI integration boundary."""

    def generate_answer(
        self,
        question: str,
        evidence_context: str,
        evidence_chunks: list[SearchResult],
    ) -> Answer:
        """Generate a grounded answer with citations or a not_found response."""

    def validate_answer_with_citations(
        self,
        answer: str,
        citations: list[dict[str, object]],
        evidence_chunks: list[SearchResult],
    ) -> bool:
        """Validate that answer citations refer only to provided evidence chunks."""
