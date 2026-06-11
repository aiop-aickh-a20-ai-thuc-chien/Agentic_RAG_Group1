"""Pipeline orchestration for the three deduplication layers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

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
from agentic_rag.ingestion.dedup_detect.models import (
    DedupConfig,
    DedupDocument,
    DedupReport,
    DuplicateMatch,
)
from agentic_rag.ingestion.dedup_detect.simhash import find_simhash_duplicates


def detect_duplicates(
    documents: Iterable[DedupDocument],
    *,
    config: DedupConfig | None = None,
    embedding_vectors: EmbeddingVectorMap | None = None,
    embedding_client: EmbeddingClient | None = None,
    embedding_fallback_candidates: Sequence[EmbeddingFallbackCandidate] | None = None,
) -> DedupReport:
    """Run exact, SimHash, and optional embedding duplicate detection."""

    resolved_config = config or DedupConfig()
    document_list = list(documents)
    exact_matches = find_exact_duplicates(document_list) if resolved_config.enable_exact else []
    excluded_pairs = _matched_pairs(exact_matches)

    simhash_matches = (
        find_simhash_duplicates(
            document_list,
            bits=resolved_config.simhash_bits,
            shingle_size=resolved_config.simhash_shingle_size,
            hamming_threshold=resolved_config.simhash_hamming_threshold,
            exclude_pairs=excluded_pairs,
        )
        if resolved_config.enable_simhash
        else []
    )
    excluded_pairs.update(_matched_pairs(simhash_matches))

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
            result = _resolve_embedding_vectors_with_fallback(
                document_list,
                candidates=embedding_fallback_candidates,
            )
            vectors = result.vectors
            provider = result.provider
            model = result.model
            method = method or result.method
            fallback_attempts = result.fallback_attempts
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
        )

    return DedupReport(
        document_count=len(document_list),
        exact_matches=exact_matches,
        simhash_matches=simhash_matches,
        embedding_matches=embedding_matches,
    )


def documents_from_chunks(chunks: Sequence[Chunk]) -> list[DedupDocument]:
    """Create dedup documents from shared ingestion chunks."""

    return [
        DedupDocument(
            document_id=chunk.chunk_id,
            text=chunk.text,
            metadata=chunk.metadata,
        )
        for chunk in chunks
    ]


def _matched_pairs(matches: Iterable[DuplicateMatch]) -> set[tuple[str, str]]:
    return {_pair_key(match.document_id, match.duplicate_document_id) for match in matches}


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
