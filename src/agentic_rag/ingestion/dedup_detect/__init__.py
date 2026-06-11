"""Three-layer duplicate detection for ingestion outputs."""

from agentic_rag.ingestion.dedup_detect.embedding import (
    cosine_similarity,
    embedding_vectors_from_client,
    find_embedding_duplicates,
)
from agentic_rag.ingestion.dedup_detect.exact import find_exact_duplicates, sha256_fingerprint
from agentic_rag.ingestion.dedup_detect.metadata import (
    DEDUP_METADATA_KEY,
    add_duplicate_metadata_to_chunks,
    duplicate_metadata_by_document,
)
from agentic_rag.ingestion.dedup_detect.models import (
    DedupConfig,
    DedupDocument,
    DedupReport,
    DuplicateLayer,
    DuplicateMatch,
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
    "DedupConfig",
    "DedupDocument",
    "DedupReport",
    "DuplicateLayer",
    "DuplicateMatch",
    "add_duplicate_metadata_to_chunks",
    "cosine_similarity",
    "detect_duplicates",
    "documents_from_chunks",
    "duplicate_metadata_by_document",
    "embedding_vectors_from_client",
    "find_embedding_duplicates",
    "find_exact_duplicates",
    "find_simhash_duplicates",
    "hamming_distance",
    "normalize_text",
    "sha256_fingerprint",
    "simhash_fingerprint",
]
