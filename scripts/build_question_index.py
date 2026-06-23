"""Build the auxiliary Qdrant collection of per-question embeddings.

The question-index retriever (``RETRIEVAL_QUESTION_INDEX_ENABLED``) matches the user
query against each chunk's LLM-extracted questions. This script embeds every question
ONCE and stores it in a persistent side collection (``{collection}_questions`` by
default, override with ``QUESTION_INDEX_COLLECTION``), so retrieval queries it directly
instead of rebuilding an in-memory index on every backend restart.

Each point = one question, dense-embedded, with the parent chunk denormalized into the
payload (chunk_id / text / metadata) so a hit reconstructs the parent chunk with no
second lookup. Idempotent — point ids are deterministic, so re-run after re-ingesting.

Run (builds from the existing main collection, no document files needed):
    uv run python scripts/build_question_index.py

Requires VECTOR_STORE_PROVIDER=qdrant. Costs one embedding pass over all questions
(short texts → cheap). After building, set RETRIEVAL_QUESTION_INDEX_ENABLED=true.
"""

from __future__ import annotations

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    from agentic_rag.retrieval.search import upsert_question_index

    print("Embedding chunk questions and upserting the auxiliary collection...")
    result = upsert_question_index()
    print(
        f"Done: indexed {result['indexed_questions']} questions into collection "
        f"'{result['questions_collection']}'."
    )
    if result["indexed_questions"] == 0:
        print(
            "No questions found in any chunk's metadata. Ensure LLM ingestion populated "
            "the 'questions' field before building the question index."
        )


if __name__ == "__main__":
    main()
