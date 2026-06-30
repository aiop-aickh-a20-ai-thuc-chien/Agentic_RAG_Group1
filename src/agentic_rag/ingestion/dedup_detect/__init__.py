"""Three-layer duplicate detection for ingestion outputs."""

from agentic_rag.ingestion.dedup_detect.blocking import (
    EMPTY_BUCKET,
    blocked_candidate_pairs,
    build_metadata_blocks,
    metadata_block_key,
    normalize_block_value,
)
from agentic_rag.ingestion.dedup_detect.embedding import (
    EmbeddingFallbackCandidate,
    EmbeddingVectorResult,
    configured_embedding_candidates,
    cosine_similarity,
    embedding_vectors_from_client,
    embedding_vectors_from_first_available_client,
    find_embedding_duplicates,
)
from agentic_rag.ingestion.dedup_detect.exact import find_exact_duplicates, sha256_fingerprint
from agentic_rag.ingestion.dedup_detect.llm_review import (
    DuplicatePairReviewer,
    review_blocked_candidates,
)
from agentic_rag.ingestion.dedup_detect.metadata import (
    DEDUP_METADATA_KEY,
    DEDUP_REVIEW_PENDING,
    DEDUP_STATUS_DUPLICATE_CANDIDATE,
    add_duplicate_metadata_to_chunks,
    chunk_metadata_contract_issues,
    chunk_metadata_contract_summary,
    duplicate_metadata_by_document,
    remove_duplicate_metadata_from_chunks,
)
from agentic_rag.ingestion.dedup_detect.models import (
    DedupConfig,
    DedupDocument,
    DedupReport,
    DuplicateLayer,
    DuplicateMatch,
    DuplicateReview,
)
from agentic_rag.ingestion.dedup_detect.normalization import normalize_text
from agentic_rag.ingestion.dedup_detect.pipeline import detect_duplicates, documents_from_chunks
from agentic_rag.ingestion.dedup_detect.simhash import (
    find_simhash_duplicates,
    hamming_distance,
    simhash_fingerprint,
)

__all__ = [
    "DEDUP_METADATA_KEY",
    "DEDUP_REVIEW_PENDING",
    "DEDUP_STATUS_DUPLICATE_CANDIDATE",
    "EMPTY_BUCKET",
    "DedupConfig",
    "DedupDocument",
    "DedupReport",
    "DuplicateLayer",
    "DuplicateMatch",
    "DuplicatePairReviewer",
    "DuplicateReview",
    "EmbeddingFallbackCandidate",
    "EmbeddingVectorResult",
    "add_duplicate_metadata_to_chunks",
    "blocked_candidate_pairs",
    "build_metadata_blocks",
    "chunk_metadata_contract_issues",
    "chunk_metadata_contract_summary",
    "configured_embedding_candidates",
    "cosine_similarity",
    "detect_duplicates",
    "documents_from_chunks",
    "duplicate_metadata_by_document",
    "embedding_vectors_from_client",
    "embedding_vectors_from_first_available_client",
    "find_embedding_duplicates",
    "find_exact_duplicates",
    "find_simhash_duplicates",
    "hamming_distance",
    "metadata_block_key",
    "normalize_block_value",
    "normalize_text",
    "remove_duplicate_metadata_from_chunks",
    "review_blocked_candidates",
    "sha256_fingerprint",
    "simhash_fingerprint",
]
