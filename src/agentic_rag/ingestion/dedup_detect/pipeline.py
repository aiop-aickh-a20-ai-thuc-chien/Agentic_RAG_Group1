"""Pipeline orchestration for the three deduplication layers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel

from agentic_rag.core.contracts import Chunk
from agentic_rag.core.ports import EmbeddingClient
from agentic_rag.ingestion.dedup_detect.embedding import (
    EmbeddingFallbackCandidate,
    EmbeddingVectorMap,
    EmbeddingVectorResult,
    configured_embedding_candidates,
    embedding_vectors_from_client,
    embedding_vectors_from_first_available_client,
    find_embedding_duplicates,
)
from agentic_rag.ingestion.dedup_detect.exact import find_exact_duplicates
from agentic_rag.ingestion.dedup_detect.llm_review import (
    DuplicatePairReviewer,
    review_blocked_candidates,
)
from agentic_rag.ingestion.dedup_detect.models import (
    DedupConfig,
    DedupDocument,
    DedupReport,
    DuplicateMatch,
)
from agentic_rag.ingestion.dedup_detect.normalization import dedup_text
from agentic_rag.ingestion.dedup_detect.simhash import find_simhash_duplicates


def detect_duplicates(
    documents: Iterable[DedupDocument],
    *,
    config: DedupConfig | None = None,
    embedding_vectors: EmbeddingVectorMap | None = None,
    embedding_client: EmbeddingClient | None = None,
    embedding_fallback_candidates: Sequence[EmbeddingFallbackCandidate] | None = None,
    metadata_reviewer: DuplicatePairReviewer | None = None,
) -> DedupReport:
    """Run exact, SimHash, and optional embedding duplicate detection."""

    # TODO [guide_2/missing implementation.md – ChangeStore not connected]:
    # Before writing chunks to the Vector DB, call `ChangeStore.record()` with
    # the content hash. If it returns False (content unchanged), skip re-ingest.
    # This avoids duplicate Vector DB upserts on unchanged pages.
    # Choose the source provider/collection before wiring to avoid changing
    # general ingestion behaviour for non-VinFast sources.
    # Reference: guide_2/missing implementation.md §Chuưa nối vào production entry point

    resolved_config = config or DedupConfig()
    document_list = list(documents)
    exact_matches = find_exact_duplicates(document_list) if resolved_config.enable_exact else []
    excluded_pairs = _matched_pairs(exact_matches)
    # Chunk-level cascade: chunks already flagged in L1 are skipped entirely by L2/L3.
    excluded_chunk_ids = _duplicate_chunk_ids(exact_matches)

    metadata_reviews = (
        review_blocked_candidates(
            document_list,
            reviewer=metadata_reviewer,
            max_block_size=resolved_config.metadata_block_max_size,
            exclude_pairs=excluded_pairs,
        )
        if resolved_config.enable_metadata_llm
        else []
    )
    metadata_llm_matches = [
        DuplicateMatch(
            layer="metadata_llm",
            document_id=review.document_id,
            duplicate_document_id=review.duplicate_document_id,
            score=review.confidence,
            reason=review.reason,
            metadata={
                "compared_metadata_fields": review.compared_metadata_fields,
                "cited_chunk_ids": review.cited_chunk_ids,
                "evidence_refs": review.evidence_refs,
                "pair_category": review.pair_category,
            },
        )
        for review in metadata_reviews
        if review.classification == "duplicate"
    ]
    excluded_pairs.update(_matched_pairs(metadata_llm_matches))
    excluded_chunk_ids.update(_duplicate_chunk_ids(metadata_llm_matches))

    simhash_matches = (
        find_simhash_duplicates(
            document_list,
            bits=resolved_config.simhash_bits,
            shingle_size=resolved_config.simhash_shingle_size,
            hamming_threshold=resolved_config.simhash_hamming_threshold,
            exclude_pairs=excluded_pairs,
            exclude_chunk_ids=excluded_chunk_ids,
        )
        if resolved_config.enable_simhash
        else []
    )
    excluded_pairs.update(_matched_pairs(simhash_matches))
    excluded_chunk_ids.update(_duplicate_chunk_ids(simhash_matches))

    embedding_matches: list[DuplicateMatch] = []
    if resolved_config.enable_embedding:
        vectors = embedding_vectors
        provider = model = None
        method = resolved_config.embedding_method
        fallback_attempts: tuple[dict[str, str], ...] = ()
        if vectors is None and embedding_client is not None:
            vectors = embedding_vectors_from_client(document_list, embedding_client)
            method = method or "embedding_client"
        elif vectors is None:
            try:
                result = _resolve_embedding_vectors_with_fallback(
                    document_list,
                    candidates=embedding_fallback_candidates,
                )
                vectors = result.vectors
                provider = result.provider
                model = result.model
                method = method or result.method
                fallback_attempts = result.fallback_attempts
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "All embedding providers failed for dedup Layer 3; "
                    "recording embedding_status=\"fallback_without_embedding\" and proceeding. Error: %s",
                    exc
                )
                vectors = {}
        if vectors is None:
            raise ValueError(
                "Embedding dedup is enabled, but no embedding_vectors or "
                "embedding_client was supplied."
            )
        embedding_matches = find_embedding_duplicates(
            document_list,
            vectors=vectors,
            similarity_threshold=resolved_config.embedding_similarity_threshold,
            method=method,
            provider=provider,
            model=model,
            fallback_attempts=fallback_attempts,
            exclude_pairs=excluded_pairs,
            exclude_chunk_ids=excluded_chunk_ids,
        )

    return DedupReport(
        document_count=len(document_list),
        exact_matches=exact_matches,
        metadata_llm_matches=metadata_llm_matches,
        metadata_reviews=metadata_reviews,
        simhash_matches=simhash_matches,
        embedding_matches=embedding_matches,
    )


def documents_from_chunks(chunks: Sequence[Chunk]) -> list[DedupDocument]:
    """Create dedup documents from shared ingestion chunks."""

    # TODO [url/TODO_dedup.md §2 – dedupe_hash for exact blocking]:
    # URL ingestion should populate `chunk.metadata["dedupe_hash"]` with an
    # aggressively normalised hash before this function is called.
    # Verify that the `dedup_text()` path here picks up `dedupe_hash` (via
    # `metadata.dedupe_text`) rather than re-normalising raw chunk text.
    # This avoids redundant parsing and keeps exact blocking deterministic.
    # Reference: url/TODO_dedup.md §2

    documents = [
        DedupDocument(
            document_id=chunk.chunk_id,
            text=chunk.text,
            metadata=_chunk_metadata_dict(chunk),
        )
        for chunk in chunks
    ]
    return [
        document.model_copy(
            update={
                "text": dedup_text(document),
                "metadata": {
                    **document.metadata,
                    "dedup_text_source": _dedup_text_source(document),
                },
            }
        )
        for document in documents
    ]


def _dedup_text_source(document: DedupDocument) -> str:
    if isinstance(document.metadata.get("dedupe_text"), str):
        return "metadata.dedupe_text"
    if isinstance(document.metadata.get("normalized_text"), str):
        return "metadata.normalized_text"
    return "text"


def _chunk_metadata_dict(chunk: Chunk) -> dict[str, Any]:
    metadata = chunk.metadata
    if isinstance(metadata, BaseModel):
        return metadata.model_dump(mode="json", exclude_none=True)
    return dict(metadata)


def _matched_pairs(matches: Iterable[DuplicateMatch]) -> set[tuple[str, str]]:
    return {_pair_key(match.document_id, match.duplicate_document_id) for match in matches}


def _duplicate_chunk_ids(matches: Iterable[DuplicateMatch]) -> set[str]:
    """Return the duplicate-side chunk IDs from a list of matches."""
    return {match.duplicate_document_id for match in matches}


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def _resolve_embedding_vectors_with_fallback(
    documents: Sequence[DedupDocument],
    *,
    candidates: Sequence[EmbeddingFallbackCandidate] | None,
) -> EmbeddingVectorResult:
    return embedding_vectors_from_first_available_client(
        documents,
        candidates=candidates or configured_embedding_candidates(),
    )
