"""Backfill LLM-extracted [L] metadata for already-ingested source documents.

One-shot migration + enrichment for documents ingested BEFORE the LLM Extract
stage existed. For each document currently stored in S3 it:

  1. reads the chunks (rule-based [P] metadata only) from the S3 source store,
  2. calls the configured ``ingestion`` LLM once per chunk to fill the six [L]
     fields (summary, keywords, questions, entities, document_type, language),
  3. writes the enriched chunks straight into the Postgres (Neon) source store,
  4. upserts the chunks into Qdrant so the payload carries [P] + [L].

It re-parses NOTHING and re-chunks NOTHING: ``chunk_id`` and ``text`` stay
byte-identical, so eval ground-truth references remain valid. Raw/markdown blobs
on S3 are never touched (we write to the Postgres store directly, bypassing the
hybrid wrapper that would re-upload blobs).

Idempotent: a document whose Neon chunks already carry ``summary`` is skipped,
so re-running only processes what is still missing.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg
from dotenv import load_dotenv

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.metadata import (
    apply_extracted_metadata,
    extract_chunk_metadata,
)
from agentic_rag.integrations.local_pdf.storage import (
    PostgresLocalSourceStore,
    S3LocalSourceStore,
)
from agentic_rag.retrieval.search import update_qdrant_payload
from agentic_rag.runtime_env import load_local_env

# Transient connection failures worth retrying (Neon idle-drop, SSL timeout,
# forcibly-closed socket). The pool's check+keepalives prevent most of these;
# this is the in-flight safety net.
_RETRYABLE = (psycopg.OperationalError, ConnectionError, OSError)


def _with_retry[T](fn: Callable[..., T], *args: object, **kwargs: object) -> T:
    """Call ``fn(*args, **kwargs)``, retrying transient connection errors.

    Args are passed through (rather than via a closure) so call sites inside
    loops don't capture loop variables — avoids the late-binding footgun.
    """
    attempts, backoff = 3, 2.0
    for attempt in range(1, attempts + 1):
        try:
            return fn(*args, **kwargs)
        except _RETRYABLE:
            if attempt == attempts:
                raise
            time.sleep(backoff * attempt)
    raise AssertionError("unreachable")


def _chunks_already_enriched(chunks: list[Chunk]) -> bool:
    """True when every chunk already carries an LLM summary (nothing to do)."""
    return bool(chunks) and all(chunk.metadata.get("summary") for chunk in chunks)


def _enrich_chunks(chunks: list[Chunk]) -> int:
    """Fill [L] fields in place. Returns the number of chunks actually enriched."""
    enriched = 0
    for chunk in chunks:
        extracted = extract_chunk_metadata(chunk)
        if extracted is not None:
            apply_extracted_metadata(chunk.metadata, extracted)
            enriched += 1
    return enriched


def _process_document(doc, *, s3, pg, args) -> tuple[str, dict]:
    """Migrate + enrich one document.

    Returns ``(log_message, stats)`` where ``stats`` are this document's deltas
    (aggregated by the caller — keeps workers free of shared mutable state so the
    run can be parallelised without locks). Raises on failure so the caller
    records it per-document and keeps going.
    """
    document_id = doc.document_id
    stats = {
        "skipped_already_enriched": 0,
        "processed_documents": 0,
        "enriched_chunks": 0,
        "total_chunks": 0,
        "qdrant_upserts": 0,
    }

    # Idempotency: check what is already in Neon, not in S3 (S3 is never enriched).
    if pg is not None:
        existing = _with_retry(pg.read_chunks, document_id)
        if _chunks_already_enriched(existing):
            stats["skipped_already_enriched"] = 1
            return "skip (done)", stats

    chunks = s3.read_chunks(document_id)
    stats["total_chunks"] = len(chunks)
    if not chunks:
        return "skip (no chunks)", stats

    if args.dry_run:
        stats["processed_documents"] = 1
        return f"would process ({len(chunks)} chunks)", stats

    enriched = _enrich_chunks(chunks)
    stats["enriched_chunks"] = enriched

    _with_retry(
        pg.write_document,
        document_id=document_id,
        dataset_id=doc.dataset_id,
        name=doc.name,
        source_type=doc.source_type,
        source=doc.source,
        raw_path=None,
        markdown_path=None,
        metadata=doc.metadata,
        chunks=chunks,
    )

    if not args.no_qdrant:
        _with_retry(update_qdrant_payload, chunks)
        stats["qdrant_upserts"] = 1

    stats["processed_documents"] = 1
    return f"done ({enriched}/{len(chunks)} chunks enriched)", stats


def _sync_s3_from_neon(documents, *, s3) -> None:
    """Copy enriched chunks from Neon back into each S3 chunks.jsonl.

    Hybrid mode treats Neon as the chunk source of truth, so after the backfill
    the S3 chunks.jsonl files are stale ([P] only). This rewrites them with the
    [P]+[L] chunks from Neon (via S3.replace_document_chunks — raw/markdown blobs
    are untouched). No LLM, no Qdrant. Idempotent: overwrites each chunks file.
    """
    pg = _build_postgres_store()
    summary = {
        "mode": "sync_s3",
        "total_documents": len(documents),
        "synced_documents": 0,
        "skipped_empty": 0,
        "errors": [],
    }
    started_at = time.perf_counter()
    total = len(documents)
    for index, doc in enumerate(documents, start=1):
        document_id = doc.document_id
        prefix = f"[{index}/{total}]"
        try:
            # Neon is the source of truth — mirror whatever it holds to S3.
            # (Don't gate on "all chunks enriched": docs with a short sub-40-char
            # chunk legitimately lack [L] on that one chunk but must still sync.)
            chunks = _with_retry(pg.read_chunks, document_id)
            if not chunks:
                summary["skipped_empty"] += 1
                print(f"{prefix} skip (no chunks in Neon): {document_id}")
                continue
            _with_retry(s3.replace_document_chunks, document_id, chunks)
            summary["synced_documents"] += 1
            print(f"{prefix} synced -> S3: {document_id} ({len(chunks)} chunks)")
        except Exception as exc:
            summary["errors"].append({"document_id": document_id, "error": str(exc)})
            print(f"{prefix} ERROR {document_id}: {exc}")

    summary["latency_seconds"] = round(time.perf_counter() - started_at, 1)
    pg.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def _build_postgres_store() -> PostgresLocalSourceStore:
    connection = os.getenv("LOCAL_SOURCE_POSTGRES_CONNECTION", "").strip()
    if not connection:
        raise SystemExit(
            "LOCAL_SOURCE_POSTGRES_CONNECTION is not set. "
            "Point it at the Neon connection used for the source store."
        )
    table_prefix = os.getenv("LOCAL_SOURCE_POSTGRES_TABLE_PREFIX", "local_rag").strip()
    return PostgresLocalSourceStore(connection=connection, table_prefix=table_prefix)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=("Migrate S3 source documents into Neon and backfill LLM [L] metadata."),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be processed without calling the LLM or writing anything.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N documents (useful for a small trial run).",
    )
    parser.add_argument(
        "--document-id",
        action="append",
        default=None,
        help="Only process the given document_id (repeatable).",
    )
    parser.add_argument(
        "--no-qdrant",
        action="store_true",
        help="Skip the Qdrant upsert (write only to Neon).",
    )
    parser.add_argument(
        "--sync-s3",
        action="store_true",
        help=(
            "Sync mode: copy already-enriched chunks from Neon back into the S3 "
            "chunks.jsonl (no LLM, no Qdrant). Run this AFTER the Neon backfill is clean."
        ),
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=6,
        help=(
            "Number of documents to process in parallel (LLM calls are I/O-bound; "
            "OpenAI rate limits are far higher than this). Default 6."
        ),
    )
    args = parser.parse_args()

    load_dotenv()
    load_local_env()

    s3 = S3LocalSourceStore.from_env()
    documents = s3.list_documents()
    if args.document_id:
        wanted = set(args.document_id)
        documents = [doc for doc in documents if doc.document_id in wanted]
    if args.limit is not None:
        documents = documents[: args.limit]

    if args.sync_s3:
        _sync_s3_from_neon(documents, s3=s3)
        return

    pg = None if args.dry_run else _build_postgres_store()

    summary = {
        "dry_run": args.dry_run,
        "total_documents": len(documents),
        "skipped_already_enriched": 0,
        "processed_documents": 0,
        "enriched_chunks": 0,
        "total_chunks": 0,
        "qdrant_upserts": 0,
        "errors": [],
    }
    started_at = time.perf_counter()

    total = len(documents)
    workers = max(1, args.concurrency)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_process_document, doc, s3=s3, pg=pg, args=args): doc for doc in documents
        }
        for future in as_completed(futures):
            doc = futures[future]
            done += 1
            prefix = f"[{done}/{total}]"
            try:
                message, stats = future.result()
                for key, value in stats.items():
                    summary[key] += value
                print(f"{prefix} {message}: {doc.document_id}")
            except Exception as exc:  # keep going; one bad doc must not abort the run
                summary["errors"].append({"document_id": doc.document_id, "error": str(exc)})
                print(f"{prefix} ERROR {doc.document_id}: {exc}")

    summary["latency_seconds"] = round(time.perf_counter() - started_at, 1)
    summary["concurrency"] = workers
    if pg is not None:
        pg.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
