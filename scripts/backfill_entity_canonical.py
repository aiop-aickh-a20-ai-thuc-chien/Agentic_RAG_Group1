"""Backfill the ``entities_canonical`` metadata field across the stores.

PHASE 3 of entity normalization. For every chunk it computes
``entities_canonical`` — the canonical forms of the chunk's filterable entities
(car/ebike model, location) via :func:`normalize_filterable` — and writes it:

  1. into Neon (source of truth), and
  2. into the Qdrant payload (``set_payload``, no re-embed),

then ensures the Qdrant keyword index on ``metadata.entities_canonical`` exists
so the query-time pre-filter is fast.

Non-destructive: the raw ``entities`` field is left untouched, so the canonical
field can always be recomputed if the map changes. Idempotent: a chunk whose
stored ``entities_canonical`` already equals the freshly computed value is
skipped (no Qdrant write).

Run (dry-run — compute + report, write nothing):
    uv run python scripts/backfill_entity_canonical.py --dry-run

Run (full backfill: Neon + Qdrant):
    uv run python scripts/backfill_entity_canonical.py

Run (also mirror enriched chunks back to S3 chunks.jsonl):
    uv run python scripts/backfill_entity_canonical.py --sync-s3
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
from agentic_rag.ingestion.metadata import normalize_filterable
from agentic_rag.integrations.local_pdf.storage import (
    PostgresLocalSourceStore,
    S3LocalSourceStore,
    StoredSourceDocument,
)
from agentic_rag.retrieval.search import ensure_entity_canonical_index, update_qdrant_payload
from agentic_rag.runtime_env import load_local_env

_RETRYABLE = (psycopg.OperationalError, ConnectionError, OSError)


def _with_retry[T](fn: Callable[..., T], *args: object, **kwargs: object) -> T:
    """Call ``fn(*args)``, retrying transient Neon/socket errors (3 attempts)."""
    attempts, backoff = 3, 2.0
    for attempt in range(1, attempts + 1):
        try:
            return fn(*args, **kwargs)
        except _RETRYABLE:
            if attempt == attempts:
                raise
            time.sleep(backoff * attempt)
    raise AssertionError("unreachable")


def _compute_canonical(chunk: Chunk) -> list[str]:
    """Filterable canonical entities for one chunk (sorted for stable comparison)."""
    raw_entities = chunk.metadata.get("entities") or []
    return sorted(normalize_filterable(str(e) for e in raw_entities))


def _apply_canonical(chunks: list[Chunk]) -> int:
    """Set ``entities_canonical`` on each chunk in place. Returns #chunks changed."""
    changed = 0
    for chunk in chunks:
        new_value = _compute_canonical(chunk)
        if chunk.metadata.get("entities_canonical") != new_value:
            chunk.metadata["entities_canonical"] = new_value
            changed += 1
    return changed


def _process_document(
    doc: StoredSourceDocument, *, pg: PostgresLocalSourceStore, args: argparse.Namespace
) -> tuple[str, dict[str, int]]:
    document_id = doc.document_id
    stats: dict[str, int] = {
        "processed_documents": 0,
        "skipped_unchanged": 0,
        "changed_chunks": 0,
        "total_chunks": 0,
        "qdrant_updates": 0,
        "chunks_with_canonical": 0,
    }

    chunks = _with_retry(pg.read_chunks, document_id)
    stats["total_chunks"] = len(chunks)
    if not chunks:
        return "skip (no chunks)", stats

    changed = _apply_canonical(chunks)
    stats["changed_chunks"] = changed
    stats["chunks_with_canonical"] = sum(1 for c in chunks if c.metadata.get("entities_canonical"))

    if changed == 0:
        stats["skipped_unchanged"] = 1
        return "skip (unchanged)", stats

    if args.dry_run:
        stats["processed_documents"] = 1
        return f"would update ({changed}/{len(chunks)} chunks)", stats

    _with_retry(pg.replace_document_chunks, document_id, chunks)
    if not args.no_qdrant:
        _with_retry(update_qdrant_payload, chunks)
        stats["qdrant_updates"] = 1

    stats["processed_documents"] = 1
    return f"done ({changed}/{len(chunks)} chunks)", stats


def _sync_s3_from_neon(
    documents: list[StoredSourceDocument], *, pg: PostgresLocalSourceStore, s3: S3LocalSourceStore
) -> None:
    """Mirror Neon chunks (now carrying entities_canonical) back to S3 chunks.jsonl."""
    total = len(documents)
    synced = 0
    for index, doc in enumerate(documents, start=1):
        try:
            chunks = _with_retry(pg.read_chunks, doc.document_id)
            if not chunks:
                print(f"[{index}/{total}] skip (no chunks): {doc.document_id}")
                continue
            _with_retry(s3.replace_document_chunks, doc.document_id, chunks)
            synced += 1
            print(f"[{index}/{total}] synced -> S3: {doc.document_id} ({len(chunks)} chunks)")
        except Exception as exc:
            print(f"[{index}/{total}] ERROR {doc.document_id}: {exc}")
    print(f"\nS3 sync done: {synced}/{total} documents")


def _build_postgres_store() -> PostgresLocalSourceStore:
    connection = os.getenv("LOCAL_SOURCE_POSTGRES_CONNECTION", "").strip()
    if not connection:
        raise SystemExit("LOCAL_SOURCE_POSTGRES_CONNECTION is not set.")
    table_prefix = os.getenv("LOCAL_SOURCE_POSTGRES_TABLE_PREFIX", "local_rag").strip()
    return PostgresLocalSourceStore(connection=connection, table_prefix=table_prefix)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill entities_canonical into Neon + Qdrant.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Compute + report only; write nothing."
    )
    parser.add_argument("--limit", type=int, default=None, help="Process at most N documents.")
    parser.add_argument(
        "--document-id", action="append", default=None, help="Only this document_id (repeatable)."
    )
    parser.add_argument("--no-qdrant", action="store_true", help="Write Neon only, skip Qdrant.")
    parser.add_argument(
        "--sync-s3", action="store_true", help="After Neon, mirror chunks back to S3 chunks.jsonl."
    )
    parser.add_argument(
        "--concurrency", type=int, default=6, help="Documents processed in parallel."
    )
    args = parser.parse_args()

    load_dotenv()
    load_local_env()

    pg = _build_postgres_store()
    documents = pg.list_documents()
    if args.document_id:
        wanted = set(args.document_id)
        documents = [d for d in documents if d.document_id in wanted]
    if args.limit is not None:
        documents = documents[: args.limit]

    # Ensure the Qdrant index exists before payloads start referencing it.
    if not args.dry_run and not args.no_qdrant:
        try:
            result = ensure_entity_canonical_index()
            print(f"Qdrant index: {result}")
        except Exception as exc:
            print(f"WARNING: could not ensure Qdrant index: {exc}")

    summary = {
        "dry_run": args.dry_run,
        "total_documents": len(documents),
        "processed_documents": 0,
        "skipped_unchanged": 0,
        "changed_chunks": 0,
        "total_chunks": 0,
        "qdrant_updates": 0,
        "chunks_with_canonical": 0,
        "errors": [],
    }
    started = time.perf_counter()
    total = len(documents)
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = {pool.submit(_process_document, d, pg=pg, args=args): d for d in documents}
        for future in as_completed(futures):
            doc = futures[future]
            done += 1
            prefix = f"[{done}/{total}]"
            try:
                message, stats = future.result()
                for key, value in stats.items():
                    summary[key] += value
                print(f"{prefix} {message}: {doc.document_id}")
            except Exception as exc:
                summary["errors"].append({"document_id": doc.document_id, "error": str(exc)})
                print(f"{prefix} ERROR {doc.document_id}: {exc}")

    if args.sync_s3 and not args.dry_run:
        print("\nSyncing S3 from Neon ...")
        s3 = S3LocalSourceStore.from_env()
        _sync_s3_from_neon(documents, pg=pg, s3=s3)

    summary["latency_seconds"] = round(time.perf_counter() - started, 1)
    pg.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
