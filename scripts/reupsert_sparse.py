"""Rebuild the Qdrant sparse vectors so RETRIEVAL_BM25_AUGMENT_KEYWORDS takes effect.

The BM25 keyword augmentation only changes the *document-side* sparse vector, which
Qdrant stores at ingest time. Toggling ``RETRIEVAL_BM25_AUGMENT_KEYWORDS`` in .env has
NO effect on an existing collection until the sparse vectors are recomputed — that is
what this script does. It scrolls every point, recomputes the sparse vector from
``_bm25_index_text(chunk)`` (which honours the flag's current value), and overwrites
ONLY the ``sparse`` named vector via ``update_vectors``. Dense vectors and payloads are
left untouched (no re-embed, no LLM cost).

Switch augmentation ON for the collection:
    RETRIEVAL_BM25_AUGMENT_KEYWORDS=true uv run python scripts/reupsert_sparse.py

Revert to text-only sparse (baseline):
    RETRIEVAL_BM25_AUGMENT_KEYWORDS=false uv run python scripts/reupsert_sparse.py

Requires VECTOR_STORE_PROVIDER=qdrant. Idempotent — safe to re-run.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    from agentic_rag.retrieval.search import reupsert_qdrant_sparse

    augment = os.getenv("RETRIEVAL_BM25_AUGMENT_KEYWORDS", "false").lower() == "true"
    print(f"RETRIEVAL_BM25_AUGMENT_KEYWORDS={augment} → rebuilding sparse vectors...")
    result = reupsert_qdrant_sparse()
    print(
        f"Done: updated {result['updated_points']} points in collection "
        f"'{result['collection']}' (augment_keywords={result['augment_keywords']})."
    )


if __name__ == "__main__":
    main()
